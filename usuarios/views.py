from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect, render

from .forms import CadastroForm


def cadastro(request):
    """
    Realiza o cadastro de novos alunos.
    """

    # Se o usuário já estiver logado,
    # não precisa acessar o cadastro novamente.
    if request.user.is_authenticated:

        return redirect(
            'home'
        )

    # Verifica se o formulário foi enviado.
    if request.method == 'POST':

        # Cria o formulário com os dados enviados.
        form = CadastroForm(
            request.POST
        )

        # Verifica se os dados são válidos.
        if form.is_valid():

            # Cria o usuário e o perfil.
            usuario = form.save()

            # Faz login automaticamente.
            login(
                request,
                usuario
            )

            # Mostra mensagem de sucesso.
            messages.success(
                request,
                'Cadastro realizado com sucesso!'
            )

            # Vai para a página inicial.
            return redirect(
                'home'
            )

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


class LoginUsuarioView(LoginView):
    """
    Realiza o login dos usuários.
    """

    # Template utilizado na tela de login.
    template_name = 'usuarios/login.html'

    # Se já estiver logado, não mostra
    # novamente a tela de login.
    redirect_authenticated_user = True


class LogoutUsuarioView(LogoutView):
    """
    Realiza o logout do usuário.
    """

    # Depois de sair, volta para a página inicial.
    next_page = 'home'


@login_required
def perfil(request):
    """
    Mostra o perfil do usuário logado.
    """

    return render(
        request,
        'usuarios/perfil.html'
    )