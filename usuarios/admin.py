from django.contrib import admin

from .models import Perfil


@admin.register(Perfil)
class PerfilAdmin(admin.ModelAdmin):
    list_display = (
        'usuario',
        'tipo',
        'idade',
        'escolaridade',
        'objetivo',
        'data_criacao',
    )

    list_filter = (
        'tipo',
        'escolaridade',
        'objetivo',
    )

    search_fields = (
        'usuario__username',
        'usuario__email',
    )