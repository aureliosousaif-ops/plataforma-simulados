# ============================================================
# FILTROS DE TEXTO EXTRAÍDO DAS PROVAS
# ============================================================

import re

from django import template


register = template.Library()


# Marcadores que iniciam itens, alternativas ou listas.
_MARCADOR_LISTA = re.compile(
    r'^(?:'
    r'[IVXLCDM]+\s*[\-.)]'
    r'|\d+\s*[\-.)]'
    r'|[a-z]\s*[\-.)]'
    r'|[-•*–—]'
    r')\s+',
    re.IGNORECASE,
)

# Abreviações que podem terminar uma linha sem encerrar o parágrafo.
_ABREVIACOES = re.compile(
    r'(?:\b[A-Z]\.|'
    r'\b(?:Sr|Sra|Dr|Dra|Prof|Profa|Eng|Exmo|Exma|etc)\.)$'
)

# Pontuação que encerra uma frase.
_FIM_DE_FRASE = ('.', '!', '?', '…')


def _juntar_linhas(anterior, proxima):
    """Junta duas linhas removendo o espaço quando a pontuação exige."""
    if not anterior:
        return proxima

    if not proxima:
        return anterior

    # Palavra quebrada no fim da linha: "guarda-\nchuva".
    if (
        anterior.endswith('-')
        and not anterior.endswith('--')
        and proxima[:1].islower()
    ):
        return anterior[:-1] + proxima

    # Não insere espaço antes de pontuação de fechamento.
    if proxima[:1] in ',.;:!?)]}»”':
        return anterior + proxima

    # Não insere espaço depois de abertura de parêntese ou aspas.
    if anterior[-1:] in '([{«“':
        return anterior + proxima

    return f'{anterior} {proxima}'


def _eh_titulo(linha):
    """Reconhece títulos curtos em caixa alta, como "TEXTO I"."""
    if len(linha) > 60:
        return False

    letras = [caractere for caractere in linha if caractere.isalpha()]

    if not letras:
        return False

    return all(caractere.isupper() for caractere in letras)


def _inicia_novo_paragrafo(anterior, proxima):
    """Decide se a linha seguinte começa um novo parágrafo."""
    if _MARCADOR_LISTA.match(proxima):
        return True

    if _eh_titulo(anterior):
        return True

    # "Acesso em: ..." continua a referência iniciada na linha anterior.
    if (
        proxima[:9].lower().startswith(('acesso em', 'acesso:'))
        and 'dispon' in anterior.lower()
    ):
        return False

    if proxima[:1].isupper() or proxima[:1] in '¿¡«“"\'(': 
        if anterior.endswith(_FIM_DE_FRASE) and len(anterior) >= 30:
            if not _ABREVIACOES.search(anterior):
                return True

    return False


@register.filter(name='normalizar_enunciado')
def normalizar_enunciado(texto):
    """
    Reorganiza o texto extraído do PDF para leitura na tela.

    O extrator mantém as quebras de linha da coluna original do PDF.
    Ao exibir esse texto com ``linebreaks``, cada quebra virava um
    ``<br>`` e o conteúdo ocupava apenas a largura da coluna do PDF.

    Este filtro junta as linhas que pertencem ao mesmo parágrafo,
    preservando apenas as separações realmente significativas.
    """
    if not texto:
        return ''

    texto = texto.replace('\r\n', '\n').replace('\r', '\n')
    linhas = [
        re.sub(r'[ \t]+', ' ', linha).strip()
        for linha in texto.split('\n')
    ]

    paragrafos = []
    atual = ''

    for linha in linhas:
        if not linha:
            # Linhas vazias de largura fixa são artefatos da extração.
            # O fim do parágrafo é decidido pela pontuação do texto.
            continue

        if not atual:
            atual = linha
            continue

        if _inicia_novo_paragrafo(atual, linha):
            paragrafos.append(atual)
            atual = linha
        else:
            atual = _juntar_linhas(atual, linha)

    if atual:
        paragrafos.append(atual)

    return '\n\n'.join(paragrafos)
