# Importa as configurações de arquivos de mídia.
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path, re_path
# Importa o painel administrativo do Django.
from django.contrib import admin

# Permite renderizar páginas.
from django.shortcuts import render

# Entrega arquivos de mídia também fora do modo de desenvolvimento.
from django.views.static import serve

# Rotas protegidas do login com Google.
from usuarios import views as usuarios

def home(request):
    """
    Exibe a página inicial da plataforma.

    Para usuários logados, apresenta informações
    resumidas sobre os simulados realizados.
    """

    # Dados padrão para usuários não logados
    # ou que ainda não realizaram simulados.
    contexto = {
        'total_simulados': 0,
        'media_desempenho': 0,
        'ultimo_simulado': None,
    }

    # Verifica se existe um usuário logado.
    if request.user.is_authenticated:

        # Importa o modelo de simulado.
        from simulados.models import Simulado

        # Busca somente simulados finalizados.
        #
        # O modelo atual não possui o campo "finalizado".
        # A finalização é identificada pelo campo "status".
        simulados = Simulado.objects.filter(
            usuario=request.user,
            status='finalizado'
        ).order_by('-finalizado_em')

        # Conta quantos simulados foram finalizados.
        contexto['total_simulados'] = simulados.count()

        # Verifica se existe algum simulado.
        if simulados.exists():

            # Obtém o simulado mais recente.
            contexto['ultimo_simulado'] = simulados.first()

            # Soma os percentuais dos simulados.
            soma_percentuais = sum(
                simulado.percentual
                for simulado in simulados
            )

            # Calcula a média de desempenho.
            contexto['media_desempenho'] = round(
                soma_percentuais / simulados.count(),
                2
            )

    # Renderiza a página inicial.
    return render(
        request,
        'home.html',
        contexto
    )


urlpatterns = [

    # Painel administrativo do Django.
    path(
        'admin/',
        admin.site.urls
    ),

    # Página inicial.
    path(
        '',
        home,
        name='home'
    ),

    # Área de usuários.
    path(
        'usuarios/',
        include('usuarios.urls')
    ),

    # Área de provas.
    path(
        'provas/',
        include('provas.urls')
    ),

    # Área de simulados.
    path(
        'simulados/',
        include('simulados.urls')
    ),

    # Área de desempenho.
    path(
        'desempenho/',
        include('desempenho.urls')
    ),
    # Login com Google: rotas específicas antes do include do
    # allauth. Sem credenciais OAuth no ambiente, devolvem o
    # visitante para o login com um aviso em vez de erro interno;
    # com credenciais, delegam ao fluxo padrão do allauth.
    path(
        'accounts/google/login/',
        usuarios.google_login
    ),
    path(
        'accounts/google/login/callback/',
        usuarios.google_callback
    ),

    # URLs do sistema de autenticação do django-allauth.
    path('accounts/', include('allauth.urls')),
    
    
]


# Disponibiliza arquivos de mídia durante o desenvolvimento.
if settings.DEBUG:

    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )

# Em produção o DEBUG fica desligado, mas as imagens e os PDFs
# enviados para a pasta de mídia continuam precisando ser servidos.
else:

    urlpatterns += [
        re_path(
            r'^media/(?P<path>.*)$',
            serve,
            {'document_root': settings.MEDIA_ROOT},
        ),
    ]
