# Importa o sistema de URLs do Django.
from django.urls import path

# Importa as views da aplicação.
from . import views


# Define o namespace da aplicação.
app_name = 'provas'


# Define as URLs da aplicação.
urlpatterns = [

    # Lista as provas.
    path(
        '',
        views.lista_provas,
        name='lista'
    ),

    # Cria uma prova.
    path(
        'criar/',
        views.criar_prova,
        name='criar'
    ),

    # Edita uma prova.
    path(
        '<int:prova_id>/editar/',
        views.editar_prova,
        name='editar'
    ),

    # Exclui uma prova.
    path(
        '<int:prova_id>/excluir/',
        views.excluir_prova,
        name='excluir'
    ),

    # Lista as disciplinas.
    path(
        'disciplinas/',
        views.lista_disciplinas,
        name='disciplinas'
    ),

    # Cria uma disciplina.
    path(
        'disciplinas/criar/',
        views.criar_disciplina,
        name='criar_disciplina'
    ),

    # Edita uma disciplina.
    path(
        'disciplinas/<int:disciplina_id>/editar/',
        views.editar_disciplina,
        name='editar_disciplina'
    ),

    # Exclui uma disciplina.
    path(
        'disciplinas/<int:disciplina_id>/excluir/',
        views.excluir_disciplina,
        name='excluir_disciplina'
    ),

    # Lista as questões.
    path(
        'questoes/',
        views.lista_questoes,
        name='questoes'
    ),

    # Cria uma questão.
    path(
        'questoes/criar/',
        views.criar_questao,
        name='criar_questao'
    ),

    # Lista as alternativas de uma questão.
    path(
        'questoes/<int:questao_id>/alternativas/',
        views.lista_alternativas,
        name='alternativas'
    ),

    # Cria as cinco alternativas de uma vez.
    path(
        'questoes/<int:questao_id>/alternativas/criar/',
        views.criar_alternativas,
        name='criar_alternativas'
    ),

    # Cria uma alternativa individual.
    path(
        'questoes/<int:questao_id>/alternativas/individual/',
        views.criar_alternativa,
        name='criar_alternativa'
    ),
]