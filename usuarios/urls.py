from django.urls import path

from .views import (
    LoginUsuarioView,
    LogoutUsuarioView,
    cadastro,
    perfil,
)


app_name = 'usuarios'


urlpatterns = [

    # Cadastro.
    path(
        'cadastro/',
        cadastro,
        name='cadastro'
    ),

    # Login.
    path(
        'login/',
        LoginUsuarioView.as_view(),
        name='login'
    ),

    # Logout.
    path(
        'logout/',
        LogoutUsuarioView.as_view(),
        name='logout'
    ),

    # Perfil.
    path(
        'perfil/',
        perfil,
        name='perfil'
    ),
]