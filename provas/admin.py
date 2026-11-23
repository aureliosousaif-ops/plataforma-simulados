from django.contrib import admin

# Importa os modelos que serão administrados pelo Django Admin.
from .models import (
    Alternativa,
    Disciplina,
    ImagemProva,
    ImagemQuestao,
    ImportacaoItem,
    ImportacaoLote,
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
        'chave_oficial',
        'tipo',
        'ano',
        'modalidade',
        'dia',
        'caderno',
        'acessibilidade',
        'origem',
        'status_importacao',
        'ativa',
    )

    # Filtros disponíveis no Admin.
    list_filter = (
        'tipo',
        'ano',
        'modalidade',
        'dia',
        'acessibilidade',
        'origem',
        'status_importacao',
        'ativa',
    )

    # Campos que podem ser pesquisados.
    search_fields = (
        'nome',
        'descricao',
        'chave_oficial',
    )

    # Dados vindos do catálogo oficial: o Admin serve para consulta,
    # a atualização desses campos é responsabilidade do comando de
    # importação.
    readonly_fields = (
        'chave_oficial',
        'origem',
        'fonte_url',
        'url_prova',
        'url_gabarito',
        'url_prova_espanhol',
        'url_gabarito_espanhol',
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

    # Permite localizar a imagem sem carregar todas as opções no select.
    autocomplete_fields = (
        'imagem',
    )


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


# Mostra os itens processados dentro da página do lote.
class ImportacaoItemInline(admin.TabularInline):

    # Modelo utilizado pelo formulário.
    model = ImportacaoItem

    # Nenhum item extra: o lote só mostra o que o comando registrou.
    extra = 0

    # Itens são gerenciados pelo comando; aqui é apenas consulta.
    can_delete = False

    # Campos exibidos e somente leitura.
    fields = (
        'chave_oficial',
        'status',
        'etapa',
        'tentativas',
        'mensagem',
    )
    readonly_fields = fields

    # Mensagens de erro podem ser longas.
    def has_add_permission(self, request):
        return False


# Configuração da consulta dos lotes de importação.
@admin.register(ImportacaoLote)
class ImportacaoLoteAdmin(admin.ModelAdmin):

    # Campos mostrados na lista de lotes.
    list_display = (
        'identificador',
        'ano',
        'modalidade',
        'status',
        'criado_em',
        'atualizado_em',
    )

    # Filtros disponíveis.
    list_filter = (
        'status',
        'ano',
        'modalidade',
    )

    # Permite pesquisar pelo identificador.
    search_fields = (
        'identificador',
    )

    # Mostra os itens dentro da página do lote.
    inlines = (
        ImportacaoItemInline,
    )

    # O lote é criado e encerrado pelo comando; aqui é apenas consulta.
    readonly_fields = (
        'identificador',
        'ano',
        'modalidade',
        'status',
        'resumo',
        'criado_em',
        'atualizado_em',
    )

    # Não faz sentido criar lote pela mão.
    def has_add_permission(self, request):
        return False


# Resumo da mensagem para a listagem de itens.
@admin.display(description='Mensagem')
def mensagem_resumida(item):
    texto = item.mensagem or ''
    if len(texto) > 80:
        return f'{texto[:80]}…'
    return texto


# Configuração da consulta dos itens de importação.
@admin.register(ImportacaoItem)
class ImportacaoItemAdmin(admin.ModelAdmin):

    # Campos mostrados na lista de itens.
    list_display = (
        'chave_oficial',
        'lote',
        'status',
        'etapa',
        'tentativas',
        mensagem_resumida,
        'atualizado_em',
    )

    # Filtros disponíveis: o filtro por status dá acesso direto aos
    # erros de importação.
    list_filter = (
        'status',
        'etapa',
    )

    # Permite pesquisar pela chave ou pelo texto do erro.
    search_fields = (
        'chave_oficial',
        'mensagem',
    )

    # O item é escrito pelo comando de importação; aqui é apenas
    # consulta, inclusive dos detalhes estruturados do erro.
    readonly_fields = (
        'lote',
        'chave_oficial',
        'prova',
        'status',
        'etapa',
        'tentativas',
        'mensagem',
        'detalhes',
        'criado_em',
        'atualizado_em',
    )

    # Não faz sentido criar item pela mão.
    def has_add_permission(self, request):
        return False
