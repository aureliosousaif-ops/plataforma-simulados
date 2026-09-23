from django.urls import path

from .views import (
    LoginUsuarioView,
    LogoutUsuarioView,
    cadastro,
    perfil,
)


app_name = 'usuarios'


urlpatterns = [
    path('cadastro/', cadastro, name='cadastro'),
    path('login/', LoginUsuarioView.as_view(), name='login'),
    path('logout/', LogoutUsuarioView.as_view(), name='logout'),
    path('perfil/', perfil, name='perfil'),
]