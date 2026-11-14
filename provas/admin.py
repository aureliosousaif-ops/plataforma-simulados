from django.contrib import admin

# Importa os modelos que serão administrados pelo Django Admin.
from .models import (
    Alternativa,
    Disciplina,
    ImagemProva,
    ImagemQuestao,
    Prova,
    Questao,
    QuestaoTextoBase,
    TextoBase,
)


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


# Permite associar textos-base dentro da questão.
class QuestaoTextoBaseInline(admin.TabularInline):

    # Modelo utilizado pelo formulário.
    model = QuestaoTextoBase

    # Quantidade de linhas extras exibidas.
    extra = 0


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
        QuestaoTextoBaseInline,
    ]


# Configuração do cadastro de imagens extraídas.
@admin.register(ImagemProva)
class ImagemProvaAdmin(admin.ModelAdmin):

    # Campos mostrados na lista.
    list_display = (
        'prova',
        'pagina',
        'indice_pagina',
        'largura',
        'altura',
        'exibida',
        'ignorada',
    )

    # Filtros disponíveis.
    list_filter = (
        'prova',
        'exibida',
        'ignorada',
    )

    # Permite pesquisar pelo hash ou nome original.
    search_fields = (
        'hash_sha256',
        'nome_original',
    )


# Configuração do cadastro de associações imagem/questão.
@admin.register(ImagemQuestao)
class ImagemQuestaoAdmin(admin.ModelAdmin):

    # Campos mostrados na lista.
    list_display = (
        'imagem',
        'questao',
        'confirmada',
        'origem',
        'ordem',
    )

    # Filtros disponíveis.
    list_filter = (
        'confirmada',
        'origem',
        'imagem__prova',
    )

    # Permite pesquisar pela prova/questão relacionada.
    search_fields = (
        'questao__enunciado',
        'imagem__nome_original',
    )


# Configuração do cadastro de textos-base compartilhados.
@admin.register(TextoBase)
class TextoBaseAdmin(admin.ModelAdmin):

    # Campos mostrados na lista.
    list_display = (
        'prova',
        'titulo',
        'identificador',
        'ordem',
    )

    # Filtros disponíveis.
    list_filter = (
        'prova',
    )

    # Permite pesquisar pelo título, cabeçalho ou conteúdo.
    search_fields = (
        'titulo',
        'identificador',
        'texto',
    )


# Configuração do cadastro de vínculos texto-base/questão.
@admin.register(QuestaoTextoBase)
class QuestaoTextoBaseAdmin(admin.ModelAdmin):

    # Campos mostrados na lista.
    list_display = (
        'texto_base',
        'questao',
        'ordem',
    )

    # Filtros disponíveis.
    list_filter = (
        'texto_base__prova',
    )

    # Permite pesquisar pela questão relacionada.
    search_fields = (
        'questao__enunciado',
        'texto_base__texto',
    )
