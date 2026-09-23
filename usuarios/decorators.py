from django.contrib import messages
from django.shortcuts import redirect


def desenvolvedor_required(view_func):
    """
    Permite acesso somente para usuários
    que possuem perfil de desenvolvedor.
    """

    def wrapper(request, *args, **kwargs):

        # Verifica se o usuário está autenticado.
        if not request.user.is_authenticated:

            return redirect('usuarios:login')

        # Tenta obter o perfil do usuário.
        try:

            perfil = request.user.perfil

        except Exception:

            messages.error(
                request,
                'Seu perfil não foi encontrado.'
            )

            return redirect('home')

        # Verifica o tipo de usuário.
        if perfil.tipo != 'desenvolvedor':

            messages.error(
                request,
                'Você não possui permissão para acessar esta área.'
            )

            return redirect('home')

        # Usuário autorizado.
        return view_func(
            request,
            *args,
            **kwargs
        )

    return wrapper