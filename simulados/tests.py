from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse

from provas.models import Alternativa, Disciplina, Prova, Questao

from usuarios.models import Perfil

from .models import RespostaSimulado, Simulado


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
