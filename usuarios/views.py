from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect, render

from .forms import CadastroForm


def cadastro(request):
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        form = CadastroForm(request.POST)

        if form.is_valid():
            usuario = form.save()
            login(request, usuario)

            messages.success(
                request,
                'Cadastro realizado com sucesso!'
            )

            return redirect('home')
    else:
        form = CadastroForm()

    return render(
        request,
        'usuarios/cadastro.html',
        {'form': form}
    )


class LoginUsuarioView(LoginView):
    template_name = 'usuarios/login.html'
    redirect_authenticated_user = True


class LogoutUsuarioView(LogoutView):
    next_page = 'home'


@login_required
def perfil(request):
    return render(
        request,
        'usuarios/perfil.html'
    )