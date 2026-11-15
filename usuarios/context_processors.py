from django.conf import settings


def usuario_info(request):
    """
    Disponibiliza informações do usuário
    para todos os templates da plataforma.
    """

    # Por padrão, ninguém é desenvolvedor.
    is_desenvolvedor = False

    # Verifica se existe usuário logado.
    if request.user.is_authenticated:

        try:
            # Verifica o tipo de perfil do usuário.
            is_desenvolvedor = (
                request.user.perfil.tipo
                == 'desenvolvedor'
            )

        except Exception:
            # Se o usuário não possuir perfil,
            # continua sendo tratado como aluno.
            is_desenvolvedor = False

    # O botão do Google só aparece quando as credenciais OAuth
    # estão configuradas no ambiente; caso contrário, o clique
    # levaria a um erro.
    return {
        'is_desenvolvedor': is_desenvolvedor,
        'login_google_disponivel': getattr(
            settings, 'GOOGLE_OAUTH_CONFIGURADO', False
        ),
    }