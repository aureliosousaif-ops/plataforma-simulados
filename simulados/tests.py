import hashlib
import tempfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from provas.models import (
    Alternativa,
    Disciplina,
    ImagemProva,
    ImagemQuestao,
    Prova,
    Questao,
    QuestaoTextoBase,
    TextoBase,
)

from usuarios.models import Perfil

from .models import RespostaSimulado, Simulado


class ExibicaoImagensSimuladoTestCase(TestCase):
    """
    Verifica a exibição das imagens confirmadas no simulado e no resultado.
    """

    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)

        self.configuracao = override_settings(
            MEDIA_ROOT=self.pasta.name
        )
        self.configuracao.enable()
        self.addCleanup(self.configuracao.disable)

        self.usuario = User.objects.create_user(
            username='aluno_imagens',
            password='SenhaTeste123!',
        )
        Perfil.objects.get_or_create(usuario=self.usuario)

        self.disciplina = Disciplina.objects.create(
            nome='Não classificada'
        )
        self.prova = Prova.objects.create(
            nome='Prova com imagens',
            tipo='enem',
            ano=2024,
            status_importacao='processada',
        )
        self.questao = Questao.objects.create(
            prova=self.prova,
            disciplina=self.disciplina,
            numero=1,
            enunciado='Enunciado com imagem.',
        )

        for letra in 'ABCDE':
            Alternativa.objects.create(
                questao=self.questao,
                letra=letra,
                texto=f'Alternativa {letra}.',
                correta=letra == 'A',
            )

        self.simulado = Simulado.objects.create(
            usuario=self.usuario,
            prova=self.prova,
        )
        RespostaSimulado.objects.create(
            simulado=self.simulado,
            questao=self.questao,
        )

        self.client.login(
            username='aluno_imagens',
            password='SenhaTeste123!',
        )

        def criar_imagem(pagina=1, cor=(30, 90, 180)):
            buffer = BytesIO()
            Image.new('RGB', (120, 60), cor).save(buffer, 'PNG')
            conteudo = buffer.getvalue()

            return ImagemProva.objects.create(
                prova=self.prova,
                arquivo=SimpleUploadedFile(
                    f'imagem-{pagina}.png',
                    conteudo,
                    content_type='image/png',
                ),
                hash_sha256=hashlib.sha256(conteudo).hexdigest(),
                pagina=pagina,
                indice_pagina=0,
                largura=120,
                altura=60,
                exibida=True,
                x=50,
                y=500,
            )

        self.criar_imagem = criar_imagem

        self.responder_url = reverse(
            'simulados:responder',
            kwargs={'simulado_id': self.simulado.id},
        )
        self.resultado_url = reverse(
            'simulados:resultado',
            kwargs={'simulado_id': self.simulado.id},
        )

    def test_responder_exibe_imagem_confirmada(self):
        imagem = self.criar_imagem()
        ImagemQuestao.objects.create(
            imagem=imagem,
            questao=self.questao,
            confirmada=True,
            origem='manual',
        )

        response = self.client.get(self.responder_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, imagem.arquivo.url)

    def test_responder_nao_exibe_imagem_nao_confirmada(self):
        imagem = self.criar_imagem()
        ImagemQuestao.objects.create(
            imagem=imagem,
            questao=self.questao,
            confirmada=False,
            origem='automatica',
        )

        response = self.client.get(self.responder_url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, imagem.arquivo.url)

    def test_responder_exibe_imagem_legada(self):
        caminho = (
            Path(self.pasta.name)
            / 'questoes'
            / 'legado.png'
        )
        caminho.parent.mkdir(parents=True, exist_ok=True)

        Image.new('RGB', (40, 40), (10, 20, 30)).save(caminho, 'PNG')

        self.questao.imagem = 'questoes/legado.png'
        self.questao.save(update_fields=['imagem'])

        response = self.client.get(self.responder_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '/media/questoes/legado.png')

    def test_resultado_exibe_imagem_confirmada(self):
        imagem = self.criar_imagem()
        ImagemQuestao.objects.create(
            imagem=imagem,
            questao=self.questao,
            confirmada=True,
            origem='manual',
        )

        self.simulado.status = 'finalizado'
        self.simulado.save(update_fields=['status'])

        response = self.client.get(self.resultado_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, imagem.arquivo.url)



class ImagensQuestaoSimuladoTestCase(TestCase):
    """
    Verifica que o responder exibe somente as imagens da questão,
    nunca a página inteira do PDF.
    """

    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)

        self.configuracao = override_settings(MEDIA_ROOT=self.pasta.name)
        self.configuracao.enable()
        self.addCleanup(self.configuracao.disable)

        self.usuario = User.objects.create_user(
            username='aluno_imagens',
            password='SenhaTeste123!',
        )
        Perfil.objects.get_or_create(usuario=self.usuario)

        self.disciplina = Disciplina.objects.create(
            nome='Não classificada'
        )

        self.prova = Prova.objects.create(
            nome='Prova com imagens da questão',
            tipo='enem',
            ano=2024,
            status_importacao='processada',
        )

        self.questao = Questao.objects.create(
            prova=self.prova,
            disciplina=self.disciplina,
            numero=1,
            enunciado='Enunciado com uma imagem própria.',
        )

        for letra in 'ABCDE':
            Alternativa.objects.create(
                questao=self.questao,
                letra=letra,
                texto=f'Alternativa {letra}.',
                correta=letra == 'A',
            )

        self.imagem = ImagemProva.objects.create(
            prova=self.prova,
            arquivo=SimpleUploadedFile(
                'imagem-questao.png',
                BytesIO(self._png()).getvalue(),
                content_type='image/png',
            ),
            hash_sha256=hashlib.sha256(self._png()).hexdigest(),
            pagina=1,
            indice_pagina=0,
            largura=120,
            altura=60,
            exibida=True,
            x=50,
            y=500,
            largura_exibicao=120,
            altura_exibicao=60,
        )
        self.associacao = ImagemQuestao.objects.create(
            imagem=self.imagem,
            questao=self.questao,
            confirmada=True,
            origem='automatica',
        )

        self.simulado = Simulado.objects.create(
            usuario=self.usuario,
            prova=self.prova,
        )
        RespostaSimulado.objects.create(
            simulado=self.simulado,
            questao=self.questao,
        )

        self.responder_url = reverse(
            'simulados:responder',
            kwargs={'simulado_id': self.simulado.id},
        )

        self.client.login(
            username='aluno_imagens',
            password='SenhaTeste123!',
        )

    @staticmethod
    def _png():
        buffer = BytesIO()
        Image.new('RGB', (120, 60), (30, 90, 180)).save(buffer, 'PNG')
        return buffer.getvalue()

    def test_responder_exibe_apenas_imagem_da_questao(self):
        response = self.client.get(self.responder_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.imagem.arquivo.url)
        self.assertContains(response, 'examix-question-images')

        # A página inteira do PDF não deve ser exibida.
        self.assertNotContains(response, 'examix-original-page')
        self.assertNotContains(response, 'Página original da prova')
        self.assertNotContains(response, '/pagina/')

    def test_responder_sem_imagem_mostra_texto_e_alternativas(self):
        self.associacao.delete()

        response = self.client.get(self.responder_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Enunciado com uma imagem própria.')
        self.assertContains(response, 'Alternativa A.')
        self.assertNotContains(response, 'examix-question-images')
        self.assertNotContains(response, self.imagem.arquivo.url)

    def test_associacao_automatica_insegura_nao_e_exibida(self):
        self.prova.arquivo_pdf = 'provas/prova.pdf'
        self.prova.save(update_fields=['arquivo_pdf'])

        marcadores = [
            {
                'pagina': 1,
                'numero': 1,
                'idioma': None,
                'x': 50,
                'y': 200,
                'altura_pagina': 842,
                'ordem': 0,
            }
        ]

        with patch(
            'provas.imagens.mapear_marcadores_pdf',
            return_value=marcadores,
        ):
            response = self.client.get(self.responder_url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.imagem.arquivo.url)
        self.assertNotContains(response, 'examix-question-images')


class ResponderViewTestCase(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_user(
            username='aluno_teste',
            password='SenhaTeste123!',
        )
        Perfil.objects.get_or_create(
            usuario=self.usuario,
        )
        disciplina = Disciplina.objects.create(nome='Não classificada')
        prova = Prova.objects.create(
            nome='Prova de teste',
            tipo='enem',
            ano=2024,
            status_importacao='processada',
        )
        questao = Questao.objects.create(
            prova=prova,
            disciplina=disciplina,
            numero=1,
            enunciado='Enunciado de teste.',
        )
        alternativas = [
            Alternativa.objects.create(
                questao=questao,
                letra=letra,
                texto=f'Alternativa {letra}.',
                correta=letra == 'A',
            )
            for letra in 'ABCDE'
        ]
        self.simulado = Simulado.objects.create(
            usuario=self.usuario,
            prova=prova,
        )
        self.resposta = RespostaSimulado.objects.create(
            simulado=self.simulado,
            questao=questao,
        )
        self.alternativa_correta = alternativas[0]
        self.url = reverse(
            'simulados:responder',
            kwargs={'simulado_id': self.simulado.id},
        )
        self.client.login(
            username='aluno_teste',
            password='SenhaTeste123!',
        )

    def test_nao_avanca_sem_alternativa(self):
        response = self.client.post(
            self.url,
            {'acao': 'proxima'},
        )

        self.assertRedirects(response, f'{self.url}?questao=1')
        self.resposta.refresh_from_db()
        self.assertFalse(self.resposta.respondida)
        self.assertIsNone(self.resposta.alternativa_id)

    def test_salva_alternativa_selecionada(self):
        response = self.client.post(
            self.url,
            {
                'acao': 'proxima',
                'alternativa': self.alternativa_correta.id,
            },
        )

        self.assertRedirects(response, f'{self.url}?questao=1')
        self.resposta.refresh_from_db()
        self.assertTrue(self.resposta.respondida)
        self.assertEqual(
            self.resposta.alternativa_id,
            self.alternativa_correta.id,
        )
        self.assertTrue(self.resposta.correta)


class IniciarSimuladoTestCase(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_user(
            username='aluno_bilingue',
            password='SenhaTeste123!',
        )
        Perfil.objects.get_or_create(
            usuario=self.usuario,
        )
        self.prova = Prova.objects.create(
            nome='ENEM bilíngue',
            tipo='enem',
            ano=2024,
            status_importacao='processada',
        )
        disciplina_ingles, _ = Disciplina.objects.get_or_create(
            nome='Inglês'
        )
        disciplina_espanhol, _ = Disciplina.objects.get_or_create(
            nome='Espanhol'
        )
        disciplina_geral, _ = Disciplina.objects.get_or_create(
            nome='Não classificada'
        )

        for numero in range(1, 6):
            for idioma, disciplina in (
                ('Inglês', disciplina_ingles),
                ('Espanhol', disciplina_espanhol),
            ):
                questao = Questao.objects.create(
                    prova=self.prova,
                    disciplina=disciplina,
                    numero=numero,
                    idioma=idioma,
                    enunciado=f'Enunciado {numero} ({idioma}).',
                )
                self._criar_alternativas(questao)

        for numero in range(6, 8):
            questao = Questao.objects.create(
                prova=self.prova,
                disciplina=disciplina_geral,
                numero=numero,
                enunciado=f'Enunciado {numero}.',
            )
            self._criar_alternativas(questao)

        self.client.login(
            username='aluno_bilingue',
            password='SenhaTeste123!',
        )
        self.url = reverse(
            'simulados:iniciar',
            kwargs={'prova_id': self.prova.id},
        )

    def _criar_alternativas(self, questao):
        for letra in 'ABCDE':
            Alternativa.objects.create(
                questao=questao,
                letra=letra,
                texto=f'Alternativa {letra}.',
                correta=letra == 'A',
            )

    def test_iniciar_cria_respostas_apenas_do_idioma_escolhido(self):
        response = self.client.post(
            self.url,
            {'idioma': 'Espanhol'},
        )

        simulado = Simulado.objects.get()
        self.assertRedirects(
            response,
            reverse(
                'simulados:responder',
                kwargs={'simulado_id': simulado.id},
            ),
        )

        respostas = list(
            simulado.respostas.select_related('questao')
        )

        self.assertEqual(len(respostas), 7)
        self.assertEqual(
            {resposta.questao.idioma for resposta in respostas},
            {'Espanhol', None},
        )

    def test_iniciar_sem_idioma_usa_ingles_por_padrao(self):
        self.client.post(self.url)

        simulado = Simulado.objects.get()
        respostas = list(
            simulado.respostas.select_related('questao')
        )

        self.assertEqual(len(respostas), 7)
        self.assertEqual(
            {resposta.questao.idioma for resposta in respostas},
            {'Inglês', None},
        )

    def test_iniciar_prova_sem_questoes_nao_cria_simulado(self):
        prova_vazia = Prova.objects.create(
            nome='ENEM sem questões',
            tipo='enem',
            ano=2024,
            status_importacao='processada',
        )
        url_vazia = reverse(
            'simulados:iniciar',
            kwargs={'prova_id': prova_vazia.id},
        )

        response = self.client.post(url_vazia, follow=True)

        self.assertContains(
            response,
            'não possui questões ativas',
        )
        self.assertFalse(
            Simulado.objects.filter(prova=prova_vazia).exists()
        )

    def test_lista_exibe_total_real_e_seletor_de_idioma(self):
        response = self.client.get(
            reverse('simulados:lista')
        )
        prova = response.context['provas'][0]

        self.assertEqual(prova.total_questoes, 7)
        self.assertEqual(
            prova.idiomas_disponiveis,
            ['Inglês', 'Espanhol'],
        )
        self.assertContains(response, 'name="idioma"')

    def test_lista_nao_exibe_seletor_com_um_unico_idioma(self):
        self.prova.questoes.filter(
            idioma='Espanhol'
        ).delete()

        response = self.client.get(
            reverse('simulados:lista')
        )
        prova = response.context['provas'][0]

        self.assertEqual(prova.total_questoes, 7)
        self.assertEqual(
            prova.idiomas_disponiveis,
            ['Inglês'],
        )
        self.assertNotContains(response, 'name="idioma"')


class ExibicaoTextoBaseSimuladoTestCase(TestCase):
    """Verifica a exibição de textos-base no simulado e no resultado."""

    def setUp(self):
        self.usuario = User.objects.create_user(
            username='aluno_texto_base',
            password='SenhaTeste123!',
        )
        Perfil.objects.get_or_create(usuario=self.usuario)

        disciplina = Disciplina.objects.create(
            nome='Não classificada'
        )
        self.prova = Prova.objects.create(
            nome='Prova com texto-base',
            tipo='enem',
            ano=2025,
            status_importacao='processada',
        )

        self.questoes = []

        for numero in (1, 2, 3):
            questao = Questao.objects.create(
                prova=self.prova,
                disciplina=disciplina,
                numero=numero,
                enunciado=f'Enunciado da questão {numero}.',
            )

            for letra in 'ABCDE':
                Alternativa.objects.create(
                    questao=questao,
                    letra=letra,
                    texto=f'Alternativa {letra}.',
                    correta=letra == 'A',
                )

            self.questoes.append(questao)

        self.texto_base = TextoBase.objects.create(
            prova=self.prova,
            chave='a' * 64,
            identificador='Texto para as Questões de 01 a 02.',
            titulo='De próprio punho',
            texto='Conteúdo compartilhado do texto-base.',
            ordem=0,
        )

        for questao in self.questoes[:2]:
            QuestaoTextoBase.objects.create(
                texto_base=self.texto_base,
                questao=questao,
                ordem=0,
            )

        self.simulado = Simulado.objects.create(
            usuario=self.usuario,
            prova=self.prova,
        )

        for questao in self.questoes:
            RespostaSimulado.objects.create(
                simulado=self.simulado,
                questao=questao,
            )

        self.client.login(
            username='aluno_texto_base',
            password='SenhaTeste123!',
        )

        self.responder_url = reverse(
            'simulados:responder',
            kwargs={'simulado_id': self.simulado.id},
        )
        self.resultado_url = reverse(
            'simulados:resultado',
            kwargs={'simulado_id': self.simulado.id},
        )

    def test_responder_exibe_texto_base_antes_do_enunciado(self):
        response = self.client.get(self.responder_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Texto para as Questões de 01 a 02.')
        self.assertContains(response, 'De próprio punho')
        self.assertContains(
            response,
            'Conteúdo compartilhado do texto-base.',
        )

        html = response.content.decode()
        self.assertLess(
            html.index('De próprio punho'),
            html.index('Enunciado da questão 1.'),
        )

    def test_responder_mostra_texto_base_em_cada_questao_do_grupo(self):
        response = self.client.get(
            f'{self.responder_url}?questao=2'
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'De próprio punho')
        self.assertContains(response, 'Enunciado da questão 2.')

    def test_questao_fora_do_grupo_nao_exibe_texto_base(self):
        response = self.client.get(
            f'{self.responder_url}?questao=3'
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'De próprio punho')
        self.assertContains(response, 'Enunciado da questão 3.')

    def test_resultado_exibe_o_texto_base_uma_unica_vez(self):
        self.simulado.status = 'finalizado'
        self.simulado.finalizado_em = timezone.now()
        self.simulado.save(update_fields=[
            'status',
            'finalizado_em',
        ])

        response = self.client.get(self.resultado_url)

        self.assertEqual(response.status_code, 200)

        html = response.content.decode()
        self.assertEqual(html.count('De próprio punho'), 1)
        self.assertContains(
            response,
            'Conteúdo compartilhado do texto-base.',
        )
