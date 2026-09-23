# Importa o path do Django.
from django.urls import path

# Importa as views da aplicação.
from . import views


# Define o namespace da aplicação.
app_name = 'provas'


urlpatterns = [

    # Lista todas as provas.
    path(
        '',
        views.lista,
        name='lista'
    ),

    # Cria uma nova prova.
    path(
        'criar/',
        views.criar,
        name='criar'
    ),

    # Mostra os detalhes de uma prova.
    path(
        '<int:prova_id>/',
        views.detalhe,
        name='detalhe'
    ),

    # Processa automaticamente uma prova.
    path(
        '<int:prova_id>/processar/',
        views.processar,
        name='processar'
    ),
]