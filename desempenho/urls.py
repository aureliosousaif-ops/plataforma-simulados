from django.urls import path

from . import views


app_name = 'desempenho'


urlpatterns = [

    # Página principal do desempenho.
    path(
        '',
        views.dashboard,
        name='dashboard'
    ),

]