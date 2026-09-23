# Importa as configurações do projeto.
from django.conf import settings

# Permite servir arquivos de mídia durante o desenvolvimento.
from django.conf.urls.static import static

from django.contrib import admin
from django.shortcuts import render
from django.urls import include, path


# Página inicial do sistema.
def home(request):
    return render(request, 'home.html')


# URLs principais do projeto.
urlpatterns = [

    # Área administrativa do Django.
    path('admin/', admin.site.urls),

    # Página inicial.
    path('', home, name='home'),

    # URLs relacionadas aos usuários.
    path(
        'usuarios/',
        include('usuarios.urls')
    ),

    # URLs relacionadas às provas.
    path(
        'provas/',
        include('provas.urls')
    ),
]


# Disponibiliza arquivos enviados durante o desenvolvimento.
if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )