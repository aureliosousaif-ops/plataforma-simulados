from unittest import mock

from django.contrib.auth.models import User
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from .forms import CadastroForm, USERNAME_EM_USO
from .models import Perfil


class CadastroUsuarioTestCase(TestCase):
    """
    Testa o cadastro de usuários, incluindo nomes duplicados.
    """

    def setUp(self):

        self.dados = {
            'username': 'aluno_novo',
            'email': 'aluno_novo@example.com',
            'password1': 'SenhaForte!2026',
            'password2': 'SenhaForte!2026',
            'idade': 18,
            'escolaridade': 'medio',
            'objetivo': 'enem',
        }

        self.url = reverse('usuarios:cadastro')

    def test_cadastro_valido_cria_usuario_perfil_e_loga(self):
        """
        O cadastro correto continua funcionando como antes.
        """

        resposta = self.client.post(self.url, self.dados)

        self.assertRedirects(resposta, reverse('home'))

        usuario = User.objects.get(username='aluno_novo')

        self.assertEqual(usuario.email, 'aluno_novo@example.com')

        perfil = Perfil.objects.get(usuario=usuario)

        self.assertEqual(perfil.tipo, 'aluno')
        self.assertEqual(perfil.idade, 18)
        self.assertEqual(perfil.escolaridade, 'medio')
        self.assertEqual(perfil.objetivo, 'enem')

        # O usuário entra automaticamente após o cadastro.
        self.assertEqual(
            int(self.client.session['_auth_user_id']),
            usuario.pk
        )

    def test_form_rejeita_username_ja_cadastrado(self):
        """
        O formulário aponta o erro antes de tentar salvar.
        """

        User.objects.create_user(
            username='aluno_novo',
            password='SenhaForte!2026'
        )

        form = CadastroForm(data=self.dados)

        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors['username'],
            [USERNAME_EM_USO]
        )

    def test_cadastro_rejeita_username_duplicado(self):
        """
        A view mostra a mensagem amigável e não cria outro usuário.
        """

        User.objects.create_user(
            username='aluno_novo',
            password='SenhaForte!2026'
        )

        resposta = self.client.post(self.url, self.dados)

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, USERNAME_EM_USO)

        self.assertEqual(
            User.objects.filter(username__iexact='aluno_novo').count(),
            1
        )

    def test_cadastro_rejeita_username_duplicado_com_outra_caixa(self):
        """
        Nomes que diferem apenas em maiúsculas/minúsculas também
        são considerados repetidos.
        """

        User.objects.create_user(
            username='Aluno_Novo',
            password='SenhaForte!2026'
        )

        resposta = self.client.post(self.url, self.dados)

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, USERNAME_EM_USO)

        self.assertEqual(
            User.objects.filter(username__iexact='aluno_novo').count(),
            1
        )

    def test_cadastro_nao_quebra_quando_username_e_gravado_na_corrida(self):
        """
        Se o nome for cadastrado entre a validação e a gravação,
        a view devolve o formulário com erro em vez de IntegrityError.
        """

        with mock.patch.object(
            CadastroForm,
            'save',
            side_effect=IntegrityError('UNIQUE constraint failed'),
        ):

            resposta = self.client.post(self.url, self.dados)

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, USERNAME_EM_USO)

        self.assertFalse(
            User.objects.filter(username='aluno_novo').exists()
        )
