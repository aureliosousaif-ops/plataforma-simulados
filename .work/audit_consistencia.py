"""Auditoria de consistência, órfãos e substituição de PDF (somente leitura).

Executa cenários que a suíte funcional não cobre, registrando o
comportamento real do código sem alterar produção.
"""

import hashlib
import tempfile
from io import BytesIO
from pathlib import Path

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from provas.imagens import (
    associar_imagem,
    capturar_confirmacoes,
    extrair_e_registrar_imagens,
    restaurar_confirmacoes,
)
from provas.models import (
    Alternativa,
    Disciplina,
    ImagemProva,
    ImagemQuestao,
    Prova,
    Questao,
)
from usuarios.models import Perfil


def gerar_pdf(cores, tamanho=(200, 300)):
    """Gera um PDF de várias páginas, uma imagem por página."""
    imagens = [Image.new('RGB', tamanho, cor) for cor in cores]
    buffer = BytesIO()
    imagens[0].save(
        buffer,
        'PDF',
        save_all=True,
        append_images=imagens[1:],
        resolution=72,
    )
    return buffer.getvalue()


class BaseConsistencia(TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.config = override_settings(MEDIA_ROOT=self.pasta.name)
        self.config.enable()
        self.addCleanup(self.config.disable)

        self.dev = User.objects.create_user(
            username='consistencia_dev',
            password='SenhaTeste123!',
        )
        Perfil.objects.update_or_create(
            usuario=self.dev,
            defaults={'tipo': 'desenvolvedor'},
        )
        self.client.force_login(self.dev)

        self.disciplina = Disciplina.objects.create(nome='Auditoria')
        self.prova = Prova.objects.create(
            nome='Prova A',
            tipo='enem',
            ano=2024,
        )
        self.questao = Questao.objects.create(
            prova=self.prova,
            disciplina=self.disciplina,
            numero=1,
            enunciado='Questão 1.',
        )
        for letra in 'ABCDE':
            Alternativa.objects.create(
                questao=self.questao,
                letra=letra,
                texto=f'Alternativa {letra}.',
                correta=letra == 'A',
            )

        self.revisar_url = reverse(
            'provas:revisar_imagens',
            kwargs={'prova_id': self.prova.id},
        )
        self.acao_url = reverse(
            'provas:acao_imagem',
            kwargs={'prova_id': self.prova.id},
        )
        self.imprimir_url = reverse(
            'provas:imprimir',
            kwargs={'prova_id': self.prova.id},
        )

    def criar_imagem(self, ignorada=False, pagina=1, cor=(20, 40, 60)):
        buffer = BytesIO()
        Image.new('RGB', (120, 60), cor).save(buffer, 'PNG')
        conteudo = buffer.getvalue()
        return ImagemProva.objects.create(
            prova=self.prova,
            arquivo=SimpleUploadedFile(
                f'consistencia-{pagina}-{cor[0]}.png',
                conteudo,
                content_type='image/png',
            ),
            hash_sha256=hashlib.sha256(conteudo).hexdigest(),
            pagina=pagina,
            indice_pagina=0,
            nome_original='consistencia.png',
            largura=120,
            altura=60,
            exibida=True,
            ignorada=ignorada,
        )


class ImagemIgnoradaTestCase(BaseConsistencia):
    """Imagem marcada como ignorada ainda pode ser confirmada."""

    def test_associar_imagem_ignorada_pela_view(self):
        imagem = self.criar_imagem(ignorada=True)

        resposta = self.client.post(
            self.acao_url,
            {
                'acao': 'associar',
                'imagem_id': imagem.id,
                'questao_id': self.questao.id,
            },
        )
        self.assertEqual(resposta.status_code, 302)
        associacao = ImagemQuestao.objects.get(imagem=imagem)
        self.assertTrue(associacao.confirmada)
        print(
            '[achado] associar via view confirmou imagem ignorada: '
            f'associacao={associacao.id} confirmada={associacao.confirmada}'
        )

        resposta = self.client.get(self.imprimir_url)
        self.assertContains(resposta, imagem.arquivo.url)
        print('[achado] imagem ignorada apareceu na impressão/simulado')

    def test_confirmar_associacao_de_imagem_ignorada_pelo_orm(self):
        imagem = self.criar_imagem(ignorada=True)
        associacao = ImagemQuestao.objects.create(
            imagem=imagem,
            questao=self.questao,
            confirmada=False,
            origem='automatica',
        )

        self.client.post(
            self.acao_url,
            {'acao': 'confirmar', 'associacao_id': associacao.id},
        )
        associacao.refresh_from_db()
        self.assertTrue(associacao.confirmada)
        self.questao.refresh_from_db()
        self.assertEqual(
            [arquivo.name for arquivo in self.questao.imagens_exibicao],
            [imagem.arquivo.name],
        )
        print('[achado] confirmar sugestão também aceita imagem ignorada')


class OrfaosTestCase(BaseConsistencia):
    """Exclusões de banco não removem arquivos físicos."""

    def test_excluir_imagemprova_mantem_arquivo(self):
        imagem = self.criar_imagem()
        caminho = Path(imagem.arquivo.path)
        self.assertTrue(caminho.exists())

        self.questao.imagem.name = imagem.arquivo.name
        self.questao.save(update_fields=['imagem'])

        imagem.delete()

        self.assertTrue(caminho.exists())
        self.assertFalse(ImagemProva.objects.exists())

        self.questao.refresh_from_db()
        self.assertEqual(self.questao.imagem.name, imagem.arquivo.name)
        self.assertTrue(Path(self.questao.imagem.path).exists())
        print(
            '[achado] excluir ImagemProva manteve o arquivo físico órfão '
            'e deixou Questao.imagem apontando para arquivo sem registro'
        )

    def test_excluir_prova_mantem_arquivos(self):
        imagem = self.criar_imagem()
        caminho_imagem = Path(imagem.arquivo.path)

        self.prova.arquivo_pdf = SimpleUploadedFile(
            'prova.pdf',
            gerar_pdf([(1, 2, 3)]),
            content_type='application/pdf',
        )
        self.prova.save(update_fields=['arquivo_pdf'])
        caminho_pdf = Path(self.prova.arquivo_pdf.path)
        self.assertTrue(caminho_pdf.exists())

        self.prova.delete()

        self.assertTrue(caminho_imagem.exists())
        self.assertTrue(caminho_pdf.exists())
        print(
            '[achado] excluir Prova manteve PDF e imagem em MEDIA_ROOT '
            '(arquivos órfãos)'
        )


class AssociacaoCruzadaTestCase(BaseConsistencia):
    """O ORM/Admin não impede associar imagem e questão de provas diferentes."""

    def test_associacao_cruzada_via_orm(self):
        outra_prova = Prova.objects.create(
            nome='Prova B',
            tipo='enem',
            ano=2024,
        )
        outra_questao = Questao.objects.create(
            prova=outra_prova,
            disciplina=self.disciplina,
            numero=1,
            enunciado='Questão da prova B.',
        )
        imagem = self.criar_imagem()

        associacao = associar_imagem(imagem, outra_questao)
        self.assertTrue(associacao.confirmada)

        outra_questao.refresh_from_db()
        self.assertEqual(
            [arquivo.name for arquivo in outra_questao.imagens_exibicao],
            [imagem.arquivo.name],
        )
        print(
            '[achado] ORM permitiu associar imagem da prova A à questão '
            'da prova B e sincronizou Questao.imagem'
        )


class SubstituicaoPdfTestCase(BaseConsistencia):
    """Reprocessar/substituir PDF preserva imagens e confirmações antigas."""

    def _anexar_pdf(self, cores):
        self.prova.arquivo_pdf = SimpleUploadedFile(
            'prova.pdf',
            gerar_pdf(cores),
            content_type='application/pdf',
        )
        self.prova.save(update_fields=['arquivo_pdf'])

    def test_substituir_pdf_mantem_imagens_antigas(self):
        self._anexar_pdf([(200, 10, 10), (10, 200, 10)])
        primeiro = extrair_e_registrar_imagens(self.prova)
        self.assertEqual(primeiro['criadas'], 2)
        antigas = list(ImagemProva.objects.order_by('id'))
        caminhos_antigos = [Path(item.arquivo.path) for item in antigas]
        self.assertTrue(all(caminho.exists() for caminho in caminhos_antigos))

        # Substitui por um PDF com imagens diferentes.
        self._anexar_pdf([(10, 10, 200), (200, 200, 10)])
        segundo = extrair_e_registrar_imagens(self.prova)

        self.assertEqual(segundo['criadas'], 2)
        self.assertEqual(ImagemProva.objects.count(), 4)
        self.assertTrue(
            all(caminho.exists() for caminho in caminhos_antigos)
        )
        print(
            '[achado] troca de PDF manteve as 2 imagens antigas no banco '
            'e no disco; total passou a 4 imagens'
        )

    def test_restauracao_reaplica_confirmacao_em_questao_nova(self):
        self._anexar_pdf([(200, 10, 10), (10, 200, 10)])
        extrair_e_registrar_imagens(self.prova)
        imagem_antiga = ImagemProva.objects.order_by('id').first()
        associar_imagem(imagem_antiga, self.questao)

        confirmacoes = capturar_confirmacoes(self.prova)
        self.assertEqual(len(confirmacoes), 1)

        # Simula o que importar_questoes_no_banco faz no processamento.
        Questao.objects.filter(prova=self.prova).delete()
        nova_questao = Questao.objects.create(
            prova=self.prova,
            disciplina=self.disciplina,
            numero=1,
            enunciado='Questão recriada.',
        )

        # Mesmo trocando o PDF, a confirmação antiga é reaplicada.
        self._anexar_pdf([(10, 10, 200), (200, 200, 10)])
        extrair_e_registrar_imagens(self.prova)
        restauradas = restaurar_confirmacoes(self.prova, confirmacoes)

        self.assertEqual(restauradas, 1)
        nova_questao.refresh_from_db()
        self.assertEqual(
            [arquivo.name for arquivo in nova_questao.imagens_exibicao],
            [imagem_antiga.arquivo.name],
        )
        print(
            '[achado] confirmação antiga foi restaurada para a questão '
            'recriada mesmo após trocar o PDF (imagem do PDF anterior)'
        )


class ArquivoAusenteTestCase(BaseConsistencia):
    """Arquivo removido do storage continua referenciado no banco."""

    def test_arquivo_removido_mantem_referencia(self):
        imagem = self.criar_imagem()
        associar_imagem(imagem, self.questao)
        Path(imagem.arquivo.path).unlink()

        self.questao.refresh_from_db()
        self.assertEqual(len(self.questao.imagens_exibicao), 1)

        resposta = self.client.get(self.imprimir_url)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, imagem.arquivo.url)
        print(
            '[achado] Questao.imagens_exibicao e a impressão continuam '
            'apontando para arquivo removido do disco (link quebrado)'
        )
