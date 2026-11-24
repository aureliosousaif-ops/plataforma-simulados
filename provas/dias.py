# ==========================================
# REGRAS DE IDENTIFICAÇÃO DO DIA DA PROVA
# ==========================================
"""
Regras compartilhadas para descobrir em qual dia o ENEM foi aplicado.

O modelo ``Prova`` já possui o campo ``dia`` (1 ou 2). Este módulo existe
para preencher provas antigas que ficaram com o campo vazio e para evitar
duplicar a lógica entre a migração de dados, o comando de manutenção, os
formulários e a página de simulados.

Ordem de confiabilidade (da mais para a menos confiável):

1. o próprio campo ``dia``, quando já preenchido;
2. a chave oficial do catálogo (``-d1-`` / ``-d2-``);
3. os nomes dos PDFs e URLs oficiais (``_D1_CD1`` / ``_D2_CD5``);
4. a faixa de numeração das questões (1–90 no 1º dia, 91–180 no 2º dia);
5. somente como último recurso, nome e descrição da prova.

Assim, uma prova cadastrada com informação confiável no banco nunca é
reclassificada apenas por causa do nome.
"""

import re


# Categorias usadas tanto na página pública quanto nos filtros.
CATEGORIAS_DIA = (
    {
        'numero': 1,
        'slug': '1',
        'titulo': '1º Dia',
        'descricao': 'Linguagens, Códigos e Ciências Humanas.',
        'icone': '📚',
    },
    {
        'numero': 2,
        'slug': '2',
        'titulo': '2º Dia',
        'descricao': 'Ciências da Natureza e Matemática.',
        'icone': '🧮',
    },
)


# Identifica d1/d2 em chaves como "enem-2025-regular-d2-cd5" ou
# "2024_D1_CD1", sem confundir com o "d1" dentro de "caderno".
_PADRAO_CHAVE = re.compile(
    r'(?<![A-Za-z0-9])d([12])(?![0-9])',
    re.IGNORECASE,
)

# Identifica D1/D2 em nomes de arquivos oficiais do INEP.
_PADRAO_ARQUIVO = re.compile(
    r'(?<![A-Za-z0-9])D([12])(?!\d)',
    re.IGNORECASE,
)

# "1º dia", "2o dia", "1° Dia" etc.
_PADRAO_DIA_ORDINAL = re.compile(
    r'\b([12])\s*(?:º|°|o)?\s*dia\b',
    re.IGNORECASE,
)

# "dia 1", "dia 2".
_PADRAO_DIA_PREFIXADO = re.compile(
    r'\bdia\s*([12])\b',
    re.IGNORECASE,
)


def obter_categoria(numero):
    """Retorna os dados da categoria de um dia (1 ou 2), se existir."""

    for categoria in CATEGORIAS_DIA:
        if categoria['numero'] == numero:
            return categoria

    return None


def normalizar_dia(valor):
    """
    Converte o valor recebido na URL em 1, 2 ou ``None``.

    Aceita os formatos usados internamente (``1``/``2``) e os aliases
    públicos (``d1``/``d2``). Qualquer outro valor significa "sem filtro".
    """

    if valor in (1, '1', 'd1', 'D1', 'primeiro', 'primeiro-dia'):
        return 1

    if valor in (2, '2', 'd2', 'D2', 'segundo', 'segundo-dia'):
        return 2

    return None


def _dia_em_texto(texto):
    """Retorna o dia citado em um texto, ou ``None`` quando ambíguo."""

    if not texto:
        return None

    encontrados = set()

    for padrao in (_PADRAO_DIA_ORDINAL, _PADRAO_DIA_PREFIXADO):
        encontrados.update(
            int(resultado.group(1))
            for resultado in padrao.finditer(str(texto))
        )

    if len(encontrados) == 1:
        return encontrados.pop()

    return None


def _dia_por_numeros(numeros_questoes):
    """
    Usa a faixa oficial de numeração: 1–90 (1º dia) e 91–180 (2º dia).

    Questões acima de 90 só existem no 2º dia. Quando todas estão dentro
    da faixa do 1º dia, a prova é do 1º dia.
    """

    numeros = [
        int(numero)
        for numero in (numeros_questoes or ())
        if numero is not None
    ]

    if not numeros:
        return None

    if any(numero > 90 for numero in numeros):
        return 2

    return 1


def _nome_arquivo(campo):
    """Extrai o nome de um FileField/URLField com segurança."""

    if not campo:
        return ''

    return str(
        getattr(campo, 'name', campo) or ''
    )


def inferir_dia(prova, numeros_questoes=None):
    """
    Infere o dia de uma prova sem alterar nenhum dado.

    ``numeros_questoes`` pode ser informado pelo chamador (migrações e
    comandos usam os números do banco). Quando omitido, a relação de
    questões do próprio modelo é consultada, se existir.
    """

    # 1) O campo do banco é sempre a fonte mais confiável.
    dia = getattr(prova, 'dia', None)

    if dia in (1, 2):
        return int(dia)

    # 2) Chave oficial do catálogo.
    dia = _dia_em_padrao(
        _PADRAO_CHAVE,
        getattr(prova, 'chave_oficial', ''),
    )
    if dia:
        return dia

    # 3) Nomes de arquivos e URLs oficiais.
    fontes_arquivo = (
        getattr(prova, 'arquivo_pdf', None),
        getattr(prova, 'arquivo_gabarito', None),
        getattr(prova, 'arquivo_pdf_espanhol', None),
        getattr(prova, 'arquivo_gabarito_espanhol', None),
        getattr(prova, 'url_prova', ''),
        getattr(prova, 'url_gabarito', ''),
        getattr(prova, 'url_prova_espanhol', ''),
        getattr(prova, 'url_gabarito_espanhol', ''),
        getattr(prova, 'fonte_url', ''),
    )

    for fonte in fontes_arquivo:
        dia = _dia_em_padrao(
            _PADRAO_ARQUIVO,
            _nome_arquivo(fonte),
        )
        if dia:
            return dia

    # 4) Faixa de numeração das questões cadastradas no banco.
    if numeros_questoes is None:
        try:
            numeros_questoes = list(
                prova.questoes.values_list('numero', flat=True)
            )
        except Exception:
            # Modelos históricos usados em migrações não expõem o
            # related_name. Nesse caso o chamador deve passar os números.
            numeros_questoes = ()

    dia = _dia_por_numeros(numeros_questoes)
    if dia:
        return dia

    # 5) Último recurso: textos descritivos da própria prova.
    for campo in (
        getattr(prova, 'nome', ''),
        getattr(prova, 'descricao', ''),
    ):
        dia = _dia_em_texto(campo)
        if dia:
            return dia

    return None


def _dia_em_padrao(padrao, texto):
    """Retorna o único dia encontrado por um regex, se houver."""

    if not texto:
        return None

    encontrados = {
        int(resultado.group(1))
        for resultado in padrao.finditer(str(texto))
    }

    if len(encontrados) == 1:
        return encontrados.pop()

    return None
