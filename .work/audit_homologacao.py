"""Testes de homologação (somente auditoria) do leitor de imagens.

Não altera código de produção. Executado com um settings temporário e
banco de teste em memória.
"""

import tempfile
from io import BytesIO

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from PIL import Image

from provas.models import (
    Alternativa,
    Disciplina,
    ImagemProva,
    ImagemQuestao,
    Prova,
    Questao,
)
from provas.imagens import associar_imagem
from usuarios.models import Perfil


class BaseHomologacao(TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.config = override_settings(MEDIA_ROOT=self.pasta.name)
        self.config.enable()
        self.addCleanup(self.config.disable)

        self.dev = User.objects.create_user(
            username='homolog_dev',
            password='SenhaTeste123!',
        )
        Perfil.objects.update_or_create(
            usuario=self.dev,
            defaults={'tipo': 'desenvolvedor'},
        )
        self.aluno = User.objects.create_user(
            username='homolog_aluno',
            password='SenhaTeste123!',
        )
        Perfil.objects.update_or_create(
            usuario=self.aluno,
            defaults={'tipo': 'aluno'},
        )

        self.disciplina = Disciplina.objects.create(
            nome='Não classificada'
        )
        self.prova = Prova.objects.create(
            nome='Prova de homologação',
            tipo='enem',
            ano=2024,
            status_importacao='processada',
        )
        self.questao = Questao.objects.create(
            prova=self.prova,
            disciplina=self.disciplina,
            numero=1,
            enunciado='Enunciado de homologação.',
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
        self.extrair_url = reverse(
            'provas:extrair_imagens',
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

    def criar_imagem(self, pagina=1, cor=(20, 40, 60), ignorada=False):
        buffer = BytesIO()
        Image.new('RGB', (120, 60), cor).save(buffer, 'PNG')
        conteudo = buffer.getvalue()

        import hashlib

        return ImagemProva.objects.create(
            prova=self.prova,
            arquivo=SimpleUploadedFile(
                f'homolog-{pagina}-{cor[0]}.png',
                conteudo,
                content_type='image/png',
            ),
            hash_sha256=hashlib.sha256(conteudo).hexdigest(),
            pagina=pagina,
            indice_pagina=0,
            nome_original='homolog.png',
            largura=120,
            altura=60,
            exibida=True,
            x=50,
            y=500,
            ignorada=ignorada,
        )


class AcessoViewsImagensTestCase(BaseHomologacao):
    """Ponto 4/5: autenticação, autorização e escopo das views."""

    def test_anonimo_nao_acessa_nenhuma_view(self):
        for url, metodo in (
            (self.revisar_url, 'get'),
            (self.imprimir_url, 'get'),
            (self.extrair_url, 'post'),
            (self.acao_url, 'post'),
        ):
            resposta = getattr(self.client, metodo)(url)
            self.assertEqual(
                resposta.status_code,
                302,
                msg=f'{metodo} {url}',
            )
            self.assertEqual(
                resposta.url,
                reverse('usuarios:login'),
                msg=f'{metodo} {url}',
            )

    def test_aluno_autenticado_recebe_redirect_e_nao_altera_dados(self):
        self.client.force_login(self.aluno)
        imagem = self.criar_imagem()

        for url, metodo in (
            (self.revisar_url, 'get'),
            (self.imprimir_url, 'get'),
        ):
            resposta = getattr(self.client, metodo)(url)
            self.assertEqual(resposta.status_code, 302)
            self.assertEqual(resposta.url, reverse('home'))

        resposta = self.client.post(
            self.acao_url,
            {
                'acao': 'associar',
                'imagem_id': imagem.id,
                'questao_id': self.questao.id,
            },
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta.url, reverse('home'))
        self.assertFalse(ImagemQuestao.objects.exists())

        resposta = self.client.post(self.extrair_url)
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta.url, reverse('home'))

    def test_desenvolvedor_acessa_revisao_e_impressao(self):
        self.client.force_login(self.dev)
        imagem = self.criar_imagem()
        associar_imagem(imagem, self.questao)

        resposta = self.client.get(self.revisar_url)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Revisar imagens')

        resposta = self.client.get(self.imprimir_url)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Enunciado de homologação.')
        self.assertContains(resposta, imagem.arquivo.url)

    def test_acoes_de_escrita_recusam_get(self):
        self.client.force_login(self.dev)

        resposta = self.client.get(self.extrair_url)
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(
            resposta.url,
            reverse(
                'provas:detalhe',
                kwargs={'prova_id': self.prova.id},
            ),
        )

        resposta = self.client.get(self.acao_url)
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta.url, self.revisar_url)

    def test_escopo_impede_imagem_ou_questao_de_outra_prova(self):
        self.client.force_login(self.dev)

        outra_prova = Prova.objects.create(
            nome='Outra prova',
            tipo='enem',
            ano=2024,
        )
        outra_questao = Questao.objects.create(
            prova=outra_prova,
            disciplina=self.disciplina,
            numero=1,
            enunciado='Outra questão.',
        )
        imagem_local = self.criar_imagem()

        # Questão de outra prova não pode ser associada.
        resposta = self.client.post(
            self.acao_url,
            {
                'acao': 'associar',
                'imagem_id': imagem_local.id,
                'questao_id': outra_questao.id,
            },
        )
        self.assertEqual(resposta.status_code, 404)
        self.assertFalse(ImagemQuestao.objects.exists())

        # Imagem de outra prova não pode ser usada pela URL desta prova.
        buffer = BytesIO()
        Image.new('RGB', (10, 10), (1, 2, 3)).save(buffer, 'PNG')
        conteudo = buffer.getvalue()
        imagem_externa = ImagemProva.objects.create(
            prova=outra_prova,
            arquivo=SimpleUploadedFile(
                'externa.png',
                conteudo,
                content_type='image/png',
            ),
            hash_sha256='0' * 64,
            pagina=1,
            indice_pagina=0,
        )
        resposta = self.client.post(
            self.acao_url,
            {
                'acao': 'associar',
                'imagem_id': imagem_externa.id,
                'questao_id': self.questao.id,
            },
        )
        self.assertEqual(resposta.status_code, 404)

        # Associação de outra prova não pode ser confirmada/removida.
        associacao_externa = ImagemQuestao.objects.create(
            imagem=imagem_externa,
            questao=outra_questao,
            confirmada=False,
            origem='manual',
        )
        for acao in ('confirmar', 'remover'):
            resposta = self.client.post(
                self.acao_url,
                {
                    'acao': acao,
                    'associacao_id': associacao_externa.id,
                },
            )
            self.assertEqual(resposta.status_code, 404)

    def test_csrf_obrigatorio_nas_acoes_post(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.dev)
        imagem = self.criar_imagem()

        resposta = cliente.post(
            self.acao_url,
            {
                'acao': 'associar',
                'imagem_id': imagem.id,
                'questao_id': self.questao.id,
            },
        )
        self.assertEqual(resposta.status_code, 403)
        self.assertFalse(ImagemQuestao.objects.exists())

        # Recarrega a tela para obter o cookie/token e repete com CSRF.
        resposta = cliente.get(self.revisar_url)
        self.assertEqual(resposta.status_code, 200)
        token = cliente.cookies['csrftoken'].value

        resposta = cliente.post(
            self.acao_url,
            {
                'csrfmiddlewaretoken': token,
                'acao': 'associar',
                'imagem_id': imagem.id,
                'questao_id': self.questao.id,
            },
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(
            ImagemQuestao.objects.filter(
                imagem=imagem,
                confirmada=True,
            ).exists()
        )

    def test_acao_desconhecida_nao_altera_dados(self):
        self.client.force_login(self.dev)
        self.criar_imagem()

        resposta = self.client.post(
            self.acao_url,
            {'acao': 'acao-inexistente'},
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(ImagemQuestao.objects.exists())

    def test_ignorar_confirmada_e_bloqueado(self):
        self.client.force_login(self.dev)
        imagem = self.criar_imagem()
        associar_imagem(imagem, self.questao)

        resposta = self.client.post(
            self.acao_url,
            {'acao': 'ignorar', 'imagem_id': imagem.id},
        )
        self.assertEqual(resposta.status_code, 302)
        imagem.refresh_from_db()
        self.assertFalse(imagem.ignorada)


class RenderizacaoImpressaoMiniaturasTestCase(BaseHomologacao):
    """Ponto 9: impressão e miniaturas."""

    def test_miniatura_usa_arquivo_original_e_classe_de_revisao(self):
        self.client.force_login(self.dev)
        imagem = self.criar_imagem()

        resposta = self.client.get(self.revisar_url)

        self.assertContains(resposta, imagem.arquivo.url)
        self.assertContains(resposta, 'examix-review-image')
        self.assertContains(resposta, 'Página 1')
        self.assertContains(resposta, '120 × 60 px')

    def test_impressao_tem_css_de_print_e_imagem_confirmada(self):
        self.client.force_login(self.dev)
        imagem = self.criar_imagem()
        associar_imagem(imagem, self.questao)

        resposta = self.client.get(self.imprimir_url)
        html = resposta.content.decode('utf-8')

        self.assertContains(resposta, 'window.print()')
        self.assertContains(resposta, '@media print')
        self.assertContains(resposta, 'examix-print-question')
        self.assertContains(resposta, imagem.arquivo.url)
        self.assertContains(resposta, 'Alternativa A.')
        self.assertEqual(html.count(imagem.arquivo.url), 1)

    def test_imagem_confirmada_nao_duplica_fallback_legado(self):
        self.client.force_login(self.dev)
        imagem = self.criar_imagem()
        associar_imagem(imagem, self.questao)
        self.questao.refresh_from_db()

        self.assertEqual(
            [arquivo.name for arquivo in self.questao.imagens_exibicao],
            [imagem.arquivo.name],
        )

    def test_sugestao_nao_confirmada_nao_aparece_na_impressao(self):
        self.client.force_login(self.dev)
        imagem = self.criar_imagem()
        ImagemQuestao.objects.create(
            imagem=imagem,
            questao=self.questao,
            confirmada=False,
            origem='automatica',
        )

        resposta = self.client.get(self.imprimir_url)
        self.assertNotContains(resposta, imagem.arquivo.url)


class ContagemConsultasTestCase(BaseHomologacao):
    """Ponto 10: consultas constantes nas telas com muitas imagens."""

    def test_revisao_e_impressao_nao_geram_n_mais_1(self):
        self.client.force_login(self.dev)

        for indice in range(20):
            questao = Questao.objects.create(
                prova=self.prova,
                disciplina=self.disciplina,
                numero=indice + 2,
                enunciado=f'Enunciado {indice + 2}.',
            )
            imagem = self.criar_imagem(
                pagina=indice + 1,
                cor=(indice, 10, 20),
            )
            imagens = [imagem]

            if indice > 0:
                # Mantém duas imagens por questão em parte dos casos.
                imagens.append(
                    self.criar_imagem(
                        pagina=indice + 1,
                        cor=(indice, 200, 20),
                    )
                )

            for item in imagens:
                ImagemQuestao.objects.create(
                    imagem=item,
                    questao=questao,
                    confirmada=True,
                    origem='manual',
                )

        for url, limite in (
            (self.revisar_url, 30),
            (self.imprimir_url, 30),
        ):
            with CaptureQueriesContext(connection) as consultas:
                resposta = self.client.get(url)
            self.assertEqual(resposta.status_code, 200)
            self.assertLessEqual(
                len(consultas),
                limite,
                msg=f'{url} executou {len(consultas)} consultas',
            )
            print(f'[queries] {url} -> {len(consultas)}')
