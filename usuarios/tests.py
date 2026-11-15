from unittest import mock
from urllib.parse import parse_qs, urlsplit, urlparse

from django.contrib.auth.models import User
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.urls import reverse

from allauth.socialaccount.models import SocialAccount
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter

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


# =========================================================
# LOGIN TRADICIONAL (usuário e senha)
# =========================================================

class LoginUsuarioTestCase(TestCase):
    """
    Testa o login tradicional na tela própria da plataforma.
    """

    def setUp(self):

        self.usuario = User.objects.create_user(
            username='aluno_login',
            email='aluno_login@example.com',
            password='SenhaForte!2026',
        )

        self.url = reverse('usuarios:login')

    def test_login_valido_entrar_e_redireciona_para_home(self):
        """
        Usuário e senha corretos entram na plataforma.
        """

        resposta = self.client.post(
            self.url,
            {
                'username': 'aluno_login',
                'password': 'SenhaForte!2026',
            }
        )

        self.assertRedirects(resposta, reverse('home'))

        self.assertEqual(
            int(self.client.session['_auth_user_id']),
            self.usuario.pk
        )

    def test_login_senha_errada_nao_autentica(self):
        """
        Senha incorreta devolve o formulário com erro,
        sem criar sessão.
        """

        resposta = self.client.post(
            self.url,
            {
                'username': 'aluno_login',
                'password': 'SenhaErrada!999',
            }
        )

        self.assertEqual(resposta.status_code, 200)

        self.assertNotIn('_auth_user_id', self.client.session)

    def test_login_usuario_inexistente_nao_autentica(self):
        """
        Nome de usuário que não existe também devolve o formulário.
        """

        resposta = self.client.post(
            self.url,
            {
                'username': 'ninguem_aqui',
                'password': 'SenhaForte!2026',
            }
        )

        self.assertEqual(resposta.status_code, 200)

        self.assertNotIn('_auth_user_id', self.client.session)

    def test_usuario_logado_e_redirecionado_da_tela_de_login(self):
        """
        Quem já entrou não precisa ver a tela de login de novo.
        """

        self.client.force_login(self.usuario)

        resposta = self.client.get(self.url)

        self.assertRedirects(resposta, reverse('home'))

    def test_perfil_exige_autenticacao(self):
        """
        Página protegida manda o visitante anônimo para o login.
        """

        resposta = self.client.get(reverse('usuarios:perfil'))

        self.assertEqual(resposta.status_code, 302)

        self.assertIn('next=/usuarios/perfil/', resposta['Location'])


# =========================================================
# LOGIN COM GOOGLE
# =========================================================

# Configuração simulada do Google, injetada nas configurações
# durante os testes (as credenciais não existem no ambiente
# local de desenvolvimento).
CONFIGURACAO_GOOGLE_TESTE = {
    'google': {
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
        'APPS': [
            {
                'client_id': 'client-id-de-teste.apps.googleusercontent.com',
                'secret': 'segredo-de-teste-nao-real',
                'key': '',
            },
        ],
    },
}

# Simula o cabeçalho enviado pelo proxy do Render, para que o
# Django construa URLs https mesmo durante os testes.
CABECALHOS_HTTPS = {
    'x-forwarded-proto': 'https',
}

# Produção exige HTTPS, mas os testes usam o servidor de testes
# em http; desativa só o redirecionamento forçado e ativa o
# cabeçalho de proxy para as URLs saírem em https.
SOBRESCREVER_SSL = override_settings(
    SECURE_SSL_REDIRECT=False,
    SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'),
)


@override_settings(
    GOOGLE_OAUTH_CONFIGURADO=True,
    SOCIALACCOUNT_PROVIDERS=CONFIGURACAO_GOOGLE_TESTE,
)
@SOBRESCREVER_SSL
class LoginGoogleTestCase(TestCase):
    """
    Testa o fluxo completo do login social com o Google,
    com as respostas do provedor simuladas (sem rede).
    """

    def _iniciar_fluxo_google(self):
        """
        Clica no botão do Google (POST na tela intermediária)
        e devolve o parâmetro state do redirecionamento.
        """

        resposta = self.client.post(
            reverse('google_login'),
            headers=CABECALHOS_HTTPS,
        )

        self.assertEqual(resposta.status_code, 302)

        local = resposta['Location']

        # O primeiro passo do OAuth envia o usuário ao Google.
        self.assertIn('https://accounts.google.com', local)

        parametros = parse_qs(urlparse(local).query)

        self.assertEqual(
            parametros['client_id'],
            ['client-id-de-teste.apps.googleusercontent.com'],
        )

        # O callback precisa apontar exatamente para a URL
        # autorizada no Google Cloud. A porta não entra na
        # comparação porque o cliente de teste reconstrói o
        # host pelo servidor de teste (testserver:80), enquanto
        # o Render entrega o domínio direto no cabeçalho Host.
        callback = urlsplit(parametros['redirect_uri'][0])

        self.assertEqual(callback.scheme, 'https')

        self.assertEqual(callback.hostname, 'testserver')

        self.assertEqual(
            callback.path,
            '/accounts/google/login/callback/',
        )

        return parametros['state'][0]

    def _simular_google(self, email, uid='123456789012345678', nome='Usuario Google'):
        """
        Substitui as chamadas de rede do OAuth2 por dados fixos:
        o troca de código por token e a resposta do perfil
        vêm daqui, não do Google.
        """

        resposta_google = {
            'sub': uid,
            'email': email,
            'email_verified': True,
            'name': nome,
            'given_name': nome,
        }

        def complete_login_falso(adapter_self, request, app, token, **kwargs):

            provider = adapter_self.get_provider()

            return provider.sociallogin_from_response(
                request,
                resposta_google
            )

        simulacoes = [
            mock.patch.object(
                GoogleOAuth2Adapter,
                'get_access_token_data',
                return_value={'access_token': 'token-de-teste'},
            ),
            mock.patch.object(
                GoogleOAuth2Adapter,
                'complete_login',
                complete_login_falso,
            ),
        ]

        for simulacao in simulacoes:
            simulacao.start()

        self.addCleanup(
            lambda: [
                simulacao.stop() for simulacao in simulacoes
            ]
        )

    def _completar_fluxo_google(self, email, uid='123456789012345678', nome='Usuario Google'):
        """
        Executa o fluxo inteiro: início, callback com o código
        e retorno do perfil simulado do Google.
        """

        state = self._iniciar_fluxo_google()

        self._simular_google(email=email, uid=uid, nome=nome)

        return self.client.get(
            reverse('google_callback'),
            {
                'code': 'codigo-de-teste',
                'state': state,
            },
            headers=CABECALHOS_HTTPS,
        )

    def test_fluxo_completo_cria_usuario_novo_com_perfil(self):
        """
        Primeiro acesso pelo Google cria a conta automaticamente
        a partir do e-mail verificado e cria o Perfil.
        """

        resposta = self._completar_fluxo_google(
            'novo.usuario@gmail.com'
        )

        self.assertEqual(resposta.status_code, 302)

        usuario = User.objects.get(
            email='novo.usuario@gmail.com'
        )

        self.assertEqual(usuario.first_name, 'Usuario Google')

        # O signal de post_save criou o Perfil.
        self.assertTrue(
            Perfil.objects.filter(usuario=usuario).exists()
        )

        # O usuário entrou na sessão.
        self.assertEqual(
            int(self.client.session['_auth_user_id']),
            usuario.pk
        )

        # A identidade do Google ficou vinculada à conta.
        self.assertTrue(
            SocialAccount.objects.filter(
                provider='google',
                uid='123456789012345678',
                user=usuario,
            ).exists()
        )

    def test_email_ja_cadastrado_entrar_na_mesma_conta(self):
        """
        E-mail do Google que já tem conta local entra nela,
        sem criar usuário duplicado.
        """

        existente = User.objects.create_user(
            username='aluna_existente',
            email='existente@gmail.com',
            password='SenhaForte!2026',
        )

        resposta = self._completar_fluxo_google(
            'existente@gmail.com'
        )

        self.assertEqual(resposta.status_code, 302)

        # Nenhuma conta extra foi criada.
        self.assertEqual(
            User.objects.filter(email__iexact='existente@gmail.com').count(),
            1
        )

        self.assertEqual(
            int(self.client.session['_auth_user_id']),
            existente.pk
        )

        # A identidade Google passou a estar vinculada à conta local.
        self.assertTrue(
            SocialAccount.objects.filter(
                provider='google',
                user=existente,
            ).exists()
        )

    def test_callback_sem_codigo_nao_quebra_nao_loga(self):
        """
        O Google devolveu o redirect sem o código de autorização:
        a página de erro aparece, ninguém entra e ninguém é criado.
        """

        state = self._iniciar_fluxo_google()

        resposta = self.client.get(
            reverse('google_callback'),
            {'state': state},
            headers=CABECALHOS_HTTPS,
        )

        self.assertNotEqual(resposta.status_code, 500)

        self.assertNotIn('_auth_user_id', self.client.session)

        self.assertEqual(User.objects.count(), 0)

    def test_callback_com_erro_do_google_nao_quebra_nao_loga(self):
        """
        O Google devolveu erro (o usuário cancelou, por exemplo):
        a página de erro aparece, ninguém entra e ninguém é criado.
        """

        state = self._iniciar_fluxo_google()

        resposta = self.client.get(
            reverse('google_callback'),
            {
                'error': 'access_denied',
                'state': state,
            },
            headers=CABECALHOS_HTTPS,
        )

        self.assertNotEqual(resposta.status_code, 500)

        self.assertNotIn('_auth_user_id', self.client.session)

        self.assertEqual(User.objects.count(), 0)

    def test_callback_sem_state_valido_nao_loga(self):
        """
        Callback sem o state do fluxo iniciado (forjado ou
        simplesmente perdido) não autentica ninguém.
        """

        self._simular_google(email='sem.state@gmail.com')

        resposta = self.client.get(
            reverse('google_callback'),
            {'code': 'codigo-de-teste'},
            headers=CABECALHOS_HTTPS,
        )

        self.assertNotEqual(resposta.status_code, 500)

        self.assertNotIn('_auth_user_id', self.client.session)

        self.assertFalse(
            User.objects.filter(email='sem.state@gmail.com').exists()
        )

    def test_state_diferente_nao_loga(self):
        """
        Callback com um state que não corresponde ao iniciado
        também é rejeitado.
        """

        self._iniciar_fluxo_google()

        self._simular_google(email='state.errado@gmail.com')

        resposta = self.client.get(
            reverse('google_callback'),
            {
                'code': 'codigo-de-teste',
                'state': 'state-fabricado-por-terceiros',
            },
            headers=CABECALHOS_HTTPS,
        )

        self.assertNotEqual(resposta.status_code, 500)

        self.assertNotIn('_auth_user_id', self.client.session)

        self.assertFalse(
            User.objects.filter(email='state.errado@gmail.com').exists()
        )


# =========================================================
# BOTÃO DO GOOGLE NAS TELAS
# =========================================================

class BotaoGoogleTestCase(TestCase):
    """
    O botão do Google só aparece quando as credenciais OAuth
    estão configuradas no ambiente.
    """

    def test_botao_oculto_sem_credenciais(self):
        """
        Sem GOOGLE_CLIENT_ID/SECRET no ambiente, as telas de
        login e cadastro não mostram o botão.
        """

        for url in (
            reverse('usuarios:login'),
            reverse('usuarios:cadastro'),
            reverse('account_login'),
        ):
            resposta = self.client.get(url)

            self.assertEqual(resposta.status_code, 200)

            self.assertNotIn(
                'Continuar com Google',
                resposta.content.decode()
            )

    def test_url_do_google_sem_credenciais_redireciona_sem_erro(self):
        """
        Acessar o fluxo do Google direto pela URL, sem credenciais
        configuradas, leva à tela de login com aviso em vez de erro 500.
        """

        with override_settings(SECURE_SSL_REDIRECT=False):
            resposta = self.client.get('/accounts/google/login/')

            self.assertEqual(resposta.status_code, 302)

            resposta = self.client.get(
                '/accounts/google/login/callback/?error=access_denied'
            )

            self.assertEqual(resposta.status_code, 302)

    def test_botao_visivel_com_credenciais(self):
        """
        Com as credenciais configuradas, o botão aparece e aponta
        para o fluxo do allauth.
        """

        with override_settings(
            GOOGLE_OAUTH_CONFIGURADO=True,
            SOCIALACCOUNT_PROVIDERS=CONFIGURACAO_GOOGLE_TESTE,
        ):
            for url in (
                reverse('usuarios:login'),
                reverse('usuarios:cadastro'),
                reverse('account_login'),
            ):
                resposta = self.client.get(url)

                self.assertEqual(resposta.status_code, 200)

                self.assertIn(
                    'Continuar com Google',
                    resposta.content.decode()
                )

                self.assertIn(
                    '/accounts/google/login/',
                    resposta.content.decode()
                )
