# =========================================================
# IMPORTAÇÕES
# =========================================================

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render

from allauth.socialaccount.providers.google.views import (
    GoogleOAuth2Adapter,
    OAuth2CallbackView,
    OAuth2LoginView,
)

from .forms import CadastroForm, USERNAME_EM_USO


# =========================================================
# SEÇÃO 1 — CADASTRO
# =========================================================

def cadastro(request):
    """
    Realiza o cadastro de novos alunos.
    """

    # Se o usuário já estiver logado,
    # não precisa acessar o cadastro novamente.
    if request.user.is_authenticated:
        return redirect('home')

    # Verifica se o formulário foi enviado.
    if request.method == 'POST':

        # Cria o formulário com os dados enviados.
        form = CadastroForm(request.POST)

        # Verifica se os dados são válidos.
        if form.is_valid():

            try:

                # Garante que usuário e perfil sejam gravados juntos.
                #
                # O bloco atômico também protege contra dois envios
                # simultâneos do mesmo nome de usuário: a validação do
                # formulário pode passar nos dois, mas só um grava.
                with transaction.atomic():

                    # Cria o usuário e o perfil.
                    usuario = form.save()

            except IntegrityError:

                # Alguém cadastrou o mesmo nome entre a validação e a
                # gravação. Mostra o erro no formulário em vez de 500.
                form.add_error('username', USERNAME_EM_USO)

            else:

                # Faz login automaticamente após o cadastro.
                #
                # O backend precisa ser informado porque o projeto
                # usa dois backends de autenticação (allauth e Django).
                login(
                    request,
                    usuario,
                    backend='django.contrib.auth.backends.ModelBackend'
                )

                # Mostra mensagem de sucesso.
                messages.success(
                    request,
                    'Cadastro realizado com sucesso!'
                )

                # Vai para a página inicial.
                return redirect('home')

    else:

        # Cria um formulário vazio.
        form = CadastroForm()

    # Mostra a página de cadastro.
    return render(
        request,
        'usuarios/cadastro.html',
        {
            'form': form
        }
    )


# =========================================================
# SEÇÃO 2 — LOGIN
# =========================================================

class LoginUsuarioView(LoginView):
    """
    Realiza o login dos usuários da plataforma.
    """

    # Template utilizado pelo login tradicional.
    template_name = 'usuarios/login.html'

    # Se o usuário já estiver logado,
    # não mostra novamente a tela de login.
    redirect_authenticated_user = True

    # Depois do login, vai para a página inicial.
    next_page = 'home'


# =========================================================
# SEÇÃO 3 — LOGOUT
# =========================================================

class LogoutUsuarioView(LogoutView):
    """
    Realiza o logout do usuário.
    """

    # Depois de sair, volta para a página inicial.
    next_page = 'home'


# =========================================================
# SEÇÃO 4 — PERFIL
# =========================================================

@login_required
def perfil(request):
    """
    Mostra o perfil do usuário logado.
    """

    return render(
        request,
        'usuarios/perfil.html'
    )


# =========================================================
# SEÇÃO 5 - LOGIN COM GOOGLE
# =========================================================

def _google_indisponivel(request):
    """
    Encaminha o usuário para a tela de login com um aviso
    quando as credenciais OAuth do Google não estão no ambiente.
    """

    messages.warning(
        request,
        'O login com Google não está disponível no momento. '
        'Use seu usuário e senha.'
    )

    return redirect('usuarios:login')


def google_login(request):
    """
    Porta de entrada do login com Google.

    Sem credenciais OAuth no ambiente, o allauth quebraria com
    SocialApp.DoesNotExist; aqui o visitante recebe a tela de
    login com um aviso em vez de um erro interno.
    """

    if not getattr(settings, 'GOOGLE_OAUTH_CONFIGURADO', False):
        return _google_indisponivel(request)

    return OAuth2LoginView.adapter_view(GoogleOAuth2Adapter)(request)


def google_callback(request):
    """
    Retorno do Google com o código de autorização.

    Segue a mesma proteção da tela de entrada: sem credenciais,
    devolve o usuário para o login com aviso em vez de erro.
    """

    if not getattr(settings, 'GOOGLE_OAUTH_CONFIGURADO', False):
        return _google_indisponivel(request)

    return OAuth2CallbackView.adapter_view(GoogleOAuth2Adapter)(request)