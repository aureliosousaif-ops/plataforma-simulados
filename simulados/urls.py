from django.urls import path

from . import views


app_name = 'simulados'


urlpatterns = [

    # Lista de provas disponíveis.
    path(
        '',
        views.lista,
        name='lista'
    ),

    # Histórico dos simulados do aluno.
    path(
        'historico/',
        views.historico,
        name='historico'
    ),

    # Inicia um novo simulado.
    path(
        'iniciar/<int:prova_id>/',
        views.iniciar,
        name='iniciar'
    ),

    # Responde às questões.
    path(
        '<int:simulado_id>/responder/',
        views.responder,
        name='responder'
    ),

    # Finaliza o simulado.
    path(
        '<int:simulado_id>/finalizar/',
        views.finalizar,
        name='finalizar'
    ),

    # Mostra o resultado.
    path(
        '<int:simulado_id>/resultado/',
        views.resultado,
        name='resultado'
    ),
]