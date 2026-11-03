from django.contrib import admin

# Importa os modelos que serão administrados pelo Django Admin.
from .models import Alternativa, Disciplina, Prova, Questao


# Configuração do cadastro de provas.
@admin.register(Prova)
class ProvaAdmin(admin.ModelAdmin):

    # Campos mostrados na lista de provas.
    list_display = (
        'nome',
        'tipo',
        'ano',
        'ativa',
        'data_criacao',
    )

    # Filtros disponíveis no Admin.
    list_filter = (
        'tipo',
        'ano',
        'ativa',
    )

    # Campos que podem ser pesquisados.
    search_fields = (
        'nome',
        'descricao',
    )


# Configuração do cadastro de disciplinas.
@admin.register(Disciplina)
class DisciplinaAdmin(admin.ModelAdmin):

    # Mostra o nome da disciplina na lista.
    list_display = (
        'nome',
    )

    # Permite pesquisar pelo nome.
    search_fields = (
        'nome',
    )


# Permite cadastrar alternativas dentro da questão.
class AlternativaInline(admin.TabularInline):

    # Modelo utilizado pelo formulário.
    model = Alternativa

    # Cria cinco campos de alternativas automaticamente.
    extra = 5

    # Limita a quantidade máxima para cinco.
    max_num = 5


# Configuração do cadastro de questões.
@admin.register(Questao)
class QuestaoAdmin(admin.ModelAdmin):

    # Campos mostrados na lista de questões.
    list_display = (
        'numero',
        'idioma',
        'prova',
        'disciplina',
        'dificuldade',
        'ativa',
    )

    # Filtros disponíveis.
    list_filter = (
        'prova',
        'idioma',
        'disciplina',
        'dificuldade',
        'ativa',
    )

    # Permite pesquisar pelo enunciado.
    search_fields = (
        'enunciado',
    )

    # Mostra as alternativas dentro da questão.
    inlines = [
        AlternativaInline,
    ]
