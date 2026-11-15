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

    # Edita uma prova existente.
    path(
        '<int:prova_id>/editar/',
        views.editar,
        name='editar'
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

    # Mostra a revisão das imagens extraídas.
    path(
        '<int:prova_id>/imagens/',
        views.revisar_imagens,
        name='revisar_imagens'
    ),

    # Extrai/reprocessa as imagens de uma prova já importada.
    path(
        '<int:prova_id>/imagens/extrair/',
        views.extrair_imagens,
        name='extrair_imagens'
    ),

    # Executa as ações POST da revisão de imagens.
    path(
        '<int:prova_id>/imagens/acao/',
        views.acao_imagem,
        name='acao_imagem'
    ),

    # Exibe a prova preparada para impressão.
    path(
        '<int:prova_id>/imprimir/',
        views.imprimir,
        name='imprimir'
    ),

    # Oculta a prova para os usuários comuns (POST).
    path(
        '<int:prova_id>/ocultar/',
        views.ocultar,
        name='ocultar'
    ),

    # Reexibe uma prova ocultada (POST).
    path(
        '<int:prova_id>/reexibir/',
        views.reexibir,
        name='reexibir'
    ),

    # Confirmação e execução da exclusão definitiva.
    path(
        '<int:prova_id>/excluir/',
        views.excluir,
        name='excluir'
    ),
]