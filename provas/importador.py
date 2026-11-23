# ============================================================
# IMPORTADOR DE PROVAS EM PDF
# ============================================================

import hashlib
import re
import unicodedata

from django.db import transaction
from pypdf import PdfReader


# ============================================================
# LIMPEZA DO TEXTO EXTRAÍDO
# ============================================================


def limpar_linhas_de_impressao(texto):
    """Remove somente linhas inteiras reconhecidas como artefatos."""
    if not texto:
        return ''

    resultado = []
    for linha in texto.splitlines():
        linha_normalizada = linha.strip()
        eh_codigo = re.fullmatch(
            r'\*?\d{6}[A-Z]{2}\d+\*?',
            linha_normalizada,
            flags=re.IGNORECASE,
        )
        eh_identificacao = re.fullmatch(
            r'ENEM\s*\d{4}',
            linha_normalizada,
            flags=re.IGNORECASE,
        )
        if not (eh_codigo or eh_identificacao):
            resultado.append(linha)
    return '\n'.join(resultado)


def _remover_cauda_rodape_repetida(texto):
    """Remove uma cauda iniciada por duas ocorrências contíguas de ENEM+ano."""
    if not texto:
        return ''

    repeticao = re.search(
        r'(?:ENEM\s*\d{4}\s*){2,}',
        texto,
        flags=re.IGNORECASE,
    )
    if repeticao:
        return texto[:repeticao.start()].rstrip()
    return texto


def limpar_texto(texto):
    if not texto:
        return ''

    texto = limpar_linhas_de_impressao(texto)
    texto = texto.replace('\r\n', '\n').replace('\r', '\n')
    texto = re.sub(r'[ \t]+', ' ', texto)
    texto = re.sub(r'\n{3,}', '\n\n', texto)
    return texto.strip()


def limpar_conteudo_questao(texto):
    if not texto:
        return ''

    texto = limpar_linhas_de_impressao(texto)
    texto = _remover_cauda_rodape_repetida(texto)
    texto = texto.strip()
    texto = re.sub(r'[ \t]+', ' ', texto)
    texto = re.sub(r'\n{3,}', '\n\n', texto)
    return texto.strip()


def extrair_texto_pdf(caminho_pdf):
    reader = PdfReader(caminho_pdf)
    paginas = []
    for pagina in reader.pages:
        paginas.append(pagina.extract_text() or '')

    texto = limpar_texto('\n'.join(paginas))

    if not texto:
        raise ValueError(
            'Nenhum texto extraível foi encontrado no PDF. '
            'O arquivo pode ser uma imagem digitalizada; '
            'é necessário aplicar OCR antes de importar.'
        )

    return texto


# ============================================================
# MARCADORES E BLOCOS DE QUESTÕES
# ============================================================


def _normalizar_busca(linha):
    normalizada = unicodedata.normalize('NFKD', linha.upper())
    normalizada = ''.join(
        caractere for caractere in normalizada
        if not unicodedata.combining(caractere)
    )
    normalizada = normalizada.replace('QUESTˆO', 'QUESTAO')
    normalizada = normalizada.replace('QUESTÃƒO', 'QUESTAO')
    normalizada = re.sub(r'\s+', ' ', normalizada).strip()
    return normalizada


# Marcadores como "QUESTÃO 01" chegam do PDF de várias formas:
# "Questão 19", "QU EST ãO 20" ou ainda "QU" em uma linha e "ESTãO 01"
# na seguinte. O texto é compactado (sem espaços) antes da comparação
# para reconhecer todas essas variações.
# Os cadernos digitais trazem o cabeçalho completo na mesma linha, como
# "Questão 91 - Ciências da Natureza e suas Tecnologias". Por isso, o
# padrão aceita um separador e o texto da área depois do número.
_PADRAO_MARCADOR_QUESTAO = re.compile(
    r'^(?:QUESTION|PREGUNTA|(?:QU)?ESTAO)0*(\d{1,3})(?:[-–—:].*)?$'
)

# Prefixos que podem ficar sozinhos em uma linha, com o restante do
# marcador na linha seguinte.
_PREFIXOS_MARCADOR_QUEBRADO = {
    'QU',
    'QUE',
    'QUES',
    'QUEST',
    'QUESTA',
    'QUESTION',
    'PREGUNTA',
}


def _compactar_busca(linha):
    """Normaliza a linha e remove todos os espaços, inclusive internos."""
    return re.sub(r'\s+', '', _normalizar_busca(linha))


def encontrar_marcadores_questoes(texto):
    linhas = texto.splitlines()
    marcadores = []
    indice = 0

    while indice < len(linhas):
        linha_busca = _compactar_busca(linhas[indice])
        resultado = _PADRAO_MARCADOR_QUESTAO.match(linha_busca)

        if resultado:
            marcadores.append({
                'numero': int(resultado.group(1)),
                'linha': indice,
            })
            indice += 1
            continue

        # Junta o prefixo quebrado ("QU") com a linha seguinte ("ESTãO 01").
        if (
            linha_busca in _PREFIXOS_MARCADOR_QUEBRADO
            and indice + 1 < len(linhas)
        ):
            combinada = linha_busca + _compactar_busca(linhas[indice + 1])
            resultado = _PADRAO_MARCADOR_QUESTAO.match(combinada)
            if resultado:
                marcadores.append({
                    'numero': int(resultado.group(1)),
                    'linha': indice + 1,
                })
                indice += 2
                continue

        indice += 1

    return marcadores


def _dividir_blocos(marcadores):
    if not marcadores:
        return []

    blocos = []
    atual = [marcadores[0]]
    for marcador in marcadores[1:]:
        if marcador['numero'] == atual[-1]['numero'] + 1:
            atual.append(marcador)
        else:
            blocos.append(atual)
            atual = [marcador]
    blocos.append(atual)
    return blocos


def selecionar_bloco_principal(marcadores):
    blocos = _dividir_blocos(marcadores)
    if not blocos:
        return []

    if len(blocos) >= 2:
        primeiro = [item['numero'] for item in blocos[0]]
        segundo = [item['numero'] for item in blocos[1]]
        if primeiro == [1, 2, 3, 4, 5] and segundo and segundo[0] == 1 and 6 in segundo:
            return blocos[0] + [item for item in blocos[1] if item['numero'] >= 6]

    return max(blocos, key=len)


def selecionar_blocos_enem(marcadores):
    blocos = _dividir_blocos(marcadores)
    if len(blocos) >= 2:
        primeiro = [item['numero'] for item in blocos[0]]
        segundo = [item['numero'] for item in blocos[1]]
        if primeiro == [1, 2, 3, 4, 5] and segundo and segundo[0] == 1 and 6 in segundo:
            return blocos[0] + blocos[1]
    return selecionar_bloco_principal(marcadores)


# ============================================================
# TEXTOS-BASE COMPARTILHADOS
# ============================================================

# Cabeçalhos que delimitam um texto usado por várias questões.
# O PDF do ENEM usa, por exemplo:
#   "Texto para as Questões de 06 a 10."
_PADRAO_TEXTO_BASE = re.compile(
    r'^(?:'
    r'TEXTO'
    r'|LEIA\s+O\s+TEXTO'
    r'|LEIA\s+OS\s+TEXTOS'
    r'|READ\s+THE\s+TEXT'
    r'|READ\s+THE\s+TEXTS'
    r'|LEE\s+EL\s+TEXTO'
    r'|LEE\s+LOS\s+TEXTOS'
    r')\s+PARA\s+(?:RESPONDER\s+)?(?:AS\s+)?QUESTOES?\s+'
    r'(?:DE\s+)?0*(\d{1,3})\s+A\s+0*(\d{1,3})\b'
)

# Linhas de rodapé que podem aparecer no meio de um texto que
# continua na página seguinte.
_ARTEFATO_RODAPE_REPETIDO = re.compile(
    r'^(?:EN\w{2}\s*\d{4}\s*){2,}$',
    flags=re.IGNORECASE,
)
_ARTEFATO_ARQUIVO_IMPRESSO = re.compile(
    r'\.indb\b',
    flags=re.IGNORECASE,
)
_ARTEFATO_CABECALHO_PAGINA = re.compile(
    r'\bCADERNO\s+\d+\b.*\bAZUL\s*\d*$',
    flags=re.IGNORECASE,
)


def _eh_artefato_de_pagina(linha):
    """Reconhece rodapés, cabeçalhos e marcas de impressão do PDF."""
    linha_limpa = linha.strip()

    if not linha_limpa:
        return False

    if _ARTEFATO_RODAPE_REPETIDO.match(linha_limpa):
        return True

    if _ARTEFATO_ARQUIVO_IMPRESSO.search(linha_limpa):
        return True

    normalizada = _normalizar_busca(linha_limpa)

    if _ARTEFATO_CABECALHO_PAGINA.search(normalizada):
        return True

    return False


def _remover_numeracao_de_linhas(linhas):
    """
    Remove a coluna de números de linha do PDF.

    O ENEM imprime a numeração dos versos em uma coluna separada. O
    extrator entrega essa coluna como uma sequência de linhas contendo
    apenas números. Somente sequências realmente consecutivas (com ao
    menos três itens) são removidas, para não apagar números que fazem
    parte do texto.
    """
    resultado = []
    indice = 0
    total = len(linhas)

    while indice < total:
        if re.fullmatch(r'\d{1,3}', linhas[indice].strip()):
            fim = indice
            numeros = []

            while fim < total and re.fullmatch(
                r'\d{1,3}',
                linhas[fim].strip(),
            ):
                numeros.append(int(linhas[fim].strip()))
                fim += 1

            if (
                len(numeros) >= 3
                and numeros == list(
                    range(numeros[0], numeros[0] + len(numeros))
                )
            ):
                indice = fim
                continue

        resultado.append(linhas[indice])
        indice += 1

    return resultado


def limpar_conteudo_texto_base(linhas):
    """Limpa um texto-base sem cortar continuações em outras páginas."""
    filtradas = [
        linha
        for linha in linhas
        if not _eh_artefato_de_pagina(linha)
    ]
    filtradas = _remover_numeracao_de_linhas(filtradas)

    texto = '\n'.join(filtradas)
    texto = texto.replace('\r\n', '\n').replace('\r', '\n')
    texto = re.sub(r'[ \t]+', ' ', texto)
    texto = re.sub(r'\n{3,}', '\n\n', texto)
    return texto.strip()


def _extrair_titulo_texto_base(linhas):
    """Usa a primeira linha curta como título do texto-base."""
    for linha in linhas:
        limpo = linha.strip()

        if not limpo or _eh_artefato_de_pagina(linha):
            continue

        if re.fullmatch(r'\d{1,3}', limpo):
            continue

        if (
            len(limpo) <= 70
            and not re.search(r'[.!?;:]$', limpo)
        ):
            return limpo

        return ''

    return ''


def encontrar_textos_base(texto, marcadores=None):
    """
    Localiza textos-base compartilhados e o intervalo de questões.

    O trecho começa no cabeçalho e termina imediatamente antes da
    primeira questão do intervalo. Rodapés e cabeçalhos de página
    intermediários são removidos, mas o conteúdo posterior a eles é
    preservado, permitindo unir textos que continuam em outra página.
    """
    linhas = texto.splitlines()

    if marcadores is None:
        marcadores = encontrar_marcadores_questoes(texto)

    textos = []

    for indice, linha in enumerate(linhas):
        normalizada = _normalizar_busca(linha)
        resultado = _PADRAO_TEXTO_BASE.match(normalizada)

        if not resultado:
            continue

        inicio = int(resultado.group(1))
        fim = int(resultado.group(2))

        if inicio > fim:
            inicio, fim = fim, inicio

        # O texto-base termina antes da primeira questão do intervalo.
        marcador_inicio = next(
            (
                marcador
                for marcador in marcadores
                if (
                    marcador['linha'] > indice
                    and marcador['numero'] == inicio
                )
            ),
            None,
        )

        if marcador_inicio is None:
            marcador_inicio = next(
                (
                    marcador
                    for marcador in marcadores
                    if marcador['linha'] > indice
                ),
                None,
            )

        linha_fim = (
            marcador_inicio['linha']
            if marcador_inicio
            else len(linhas)
        )

        linhas_conteudo = linhas[indice + 1:linha_fim]
        titulo = _extrair_titulo_texto_base(linhas_conteudo)
        linhas_texto = linhas_conteudo

        # O título é exibido separadamente; não deve aparecer repetido
        # no início do corpo do texto.
        if titulo:
            for posicao, linha_conteudo in enumerate(linhas_conteudo):
                if linha_conteudo.strip() == titulo:
                    linhas_texto = (
                        linhas_conteudo[:posicao]
                        + linhas_conteudo[posicao + 1:]
                    )
                    break

        conteudo = limpar_conteudo_texto_base(linhas_texto)

        if not conteudo:
            continue

        idioma = None

        # Só faz sentido falar em idioma quando o intervalo é das
        # questões 1 a 5, que existem em Inglês e Espanhol.
        if inicio in range(1, 6) and fim in range(1, 6):
            idioma = detectar_idioma_secao(linhas, indice)

        textos.append({
            'chave': hashlib.sha256(
                conteudo.encode('utf-8')
            ).hexdigest(),
            'identificador': linha.strip(),
            'titulo': titulo,
            'texto': conteudo,
            'inicio': inicio,
            'fim': fim,
            'idioma': idioma,
            'linha_cabecalho': indice,
            'linha_fim': linha_fim,
            'ordem': len(textos),
        })

    return textos


def _associar_textos_base(questoes, textos_base):
    """Vincula cada texto-base às questões do intervalo declarado."""
    for questao in questoes:
        questao['textos_base'] = []

    for texto_base in textos_base:
        for questao in questoes:
            if not (
                texto_base['inicio']
                <= questao['numero']
                <= texto_base['fim']
            ):
                continue

            # O texto-base precisa ter sido impresso antes da questão.
            if questao.get('_linha', 0) <= texto_base['linha_cabecalho']:
                continue

            if (
                texto_base['idioma']
                and questao.get('_idioma') != texto_base['idioma']
            ):
                continue

            questao['textos_base'].append(texto_base)

    # Remove repetições dentro da mesma questão, preservando a ordem.
    for questao in questoes:
        vistos = set()
        unicos = []

        for texto_base in questao['textos_base']:
            if texto_base['chave'] in vistos:
                continue

            vistos.add(texto_base['chave'])
            unicos.append(texto_base)

        questao['textos_base'] = unicos


# ============================================================
# ALTERNATIVAS
# ============================================================


def limpar_texto_alternativa(texto):
    if not texto:
        return ''

    texto = limpar_linhas_de_impressao(texto)
    texto = _remover_cauda_rodape_repetida(texto)
    texto = re.sub(
        r'\s*\*?\d{6}[A-Z]{2}\d+\*?'
        r'(?:\s+ENEM\s*\d{4}\b.*)?$',
        '',
        texto,
        flags=re.IGNORECASE,
    )
    texto = re.sub(r'[ \t]+', ' ', texto)
    return texto.strip()


def _expandir_alternativas_inline(texto):
    """Quebra uma linha somente quando contém uma sequência A–E explícita."""
    linhas_expandidas = []
    padrao = re.compile(
        r'(?<![A-Za-z0-9])\(?([A-E])\)?(?:\)|[.\:\-])\s+',
        re.IGNORECASE,
    )

    for linha in texto.splitlines():
        encontrados = list(padrao.finditer(linha))
        sequencia = None
        for inicio in range(len(encontrados) - 4):
            candidatos = encontrados[inicio:inicio + 5]
            if [item.group(1).upper() for item in candidatos] == ['A', 'B', 'C', 'D', 'E']:
                sequencia = candidatos
                break

        if sequencia is None:
            linhas_expandidas.append(linha)
            continue

        partes = []
        prefixo = linha[:sequencia[0].start()].strip()
        if prefixo:
            partes.append(prefixo)
        for indice, marcador in enumerate(sequencia):
            fim = sequencia[indice + 1].start() if indice < 4 else len(linha)
            partes.append(linha[marcador.start():fim].strip())
        linhas_expandidas.extend(partes)

    return '\n'.join(linhas_expandidas)


_PADRAO_LETRA_ISOLADA = re.compile(
    r'^\(?\s*([A-Ea-e])\s*\)?\s*[.\:\-]?$'
)

# Um bloco inicial muito maior que o intervalo até a letra B costuma
# indicar que a letra "A" detectada faz parte do enunciado, e não de
# uma alternativa. O limite é conservador para não cortar alternativas
# legitimamente longas.
LIMITE_LINHAS_BLOCO_INICIAL = 5


def _letra_isolada(linha):
    """Devolve a letra de uma linha que contém apenas o marcador."""
    if not linha:
        return None

    resultado = _PADRAO_LETRA_ISOLADA.fullmatch(linha.strip())
    return resultado.group(1).upper() if resultado else None


def _linha_anterior_preenchida(linhas, indice):
    """Retorna o texto da linha preenchida imediatamente anterior."""
    for posicao in range(indice - 1, -1, -1):
        if linhas[posicao].strip():
            return linhas[posicao]
    return ''


def _encontrar_marcadores_alternativas(
    linhas,
    permitir_marcadores_sem_pontuacao=False,
):
    encontrados = []
    for indice, linha in enumerate(linhas):
        linha_limpa = linha.strip()
        if not linha_limpa:
            continue

        # Marcador isolado: aceita A, A), (A), A ., A - etc.
        isolado = re.fullmatch(
            r'\(?\s*([A-Ea-e])\s*(\)?)\s*([.\:\-]?)\s*',
            linha_limpa,
        )
        if isolado:
            letra = isolado.group(1)
            tem_marca = bool(
                isolado.group(2)
                or isolado.group(3)
                or '(' in linha_limpa
            )

            # Letras minúsculas só são marcadores quando vêm com
            # pontuação/parênteses. Sem isso, " c" é apenas o começo
            # da palavra seguinte ("conservar"), quebrada pelo PDF.
            if letra.isupper() or tem_marca:
                # O PDF quebra palavras no início das linhas: depois de
                # um marcador isolado surge, por exemplo, " B" seguido de
                # "atata chips." (a alternativa A é "Batata chips.").
                # Nesse caso a letra com espaço inicial é fragmento da
                # alternativa anterior, não um novo marcador.
                if (
                    linha[:1].isspace()
                    and _letra_isolada(
                        _linha_anterior_preenchida(linhas, indice)
                    )
                ):
                    continue

                encontrados.append({
                    'letra': letra.upper(),
                    'linha': indice,
                    'isolado': True,
                })
                continue

        # Marcador junto do texto: exige pontuação para não confundir
        # frases legítimas como "A alternativa correta é...".
        pontuacao = r'(?:\)|[.\:\-])' if not permitir_marcadores_sem_pontuacao else r'(?:\)|[.\:\-])?'
        junto = re.match(
            rf'^\(?\s*([A-E])\s*({pontuacao})\s+(.+)$',
            linha_limpa,
            re.IGNORECASE,
        )
        if junto:
            letra = junto.group(1)
            marca = junto.group(2)

            # Fragmentos minúsculos sem pontuação não são alternativas.
            if letra.isupper() or marca:
                encontrados.append({
                    'letra': letra.upper(),
                    'linha': indice,
                    'isolado': False,
                })
    return encontrados


def _encontrar_sequencia_abced(marcadores):
    candidatos = []

    for inicio, marcador_inicial in enumerate(marcadores):
        if marcador_inicial['letra'] != 'A':
            continue

        selecionados = [marcador_inicial]
        proxima_letra = 'B'

        for marcador in marcadores[inicio + 1:]:
            if marcador['letra'] != proxima_letra:
                continue

            selecionados.append(marcador)
            if proxima_letra == 'B':
                proxima_letra = 'C'
            elif proxima_letra == 'C':
                proxima_letra = 'D'
            elif proxima_letra == 'D':
                proxima_letra = 'E'
            else:
                break

        if len(selecionados) == 5:
            distancia = (
                selecionados[-1]['linha']
                - selecionados[0]['linha']
            )
            distancia_a_b = (
                selecionados[1]['linha']
                - selecionados[0]['linha']
            )
            quantidade_isolados = sum(
                marcador.get('isolado', False)
                for marcador in selecionados
            )
            candidatos.append((
                # Enunciados que começam com "A" podem gerar um falso
                # marcador A. Nesse caso o "bloco A" absorve todo o
                # enunciado e fica muito maior que o intervalo até B.
                distancia_a_b > LIMITE_LINHAS_BLOCO_INICIAL,
                # Marcadores isolados são mais confiáveis do que letras
                # junto do texto. Isso evita escolher um bloco A-E
                # inline da questão seguinte.
                -quantidade_isolados,
                # Entre candidatos igualmente confiáveis, prefere o
                # bloco mais compacto e, depois, o que aparece primeiro.
                distancia_a_b,
                selecionados[0]['linha'],
                distancia,
                selecionados,
            ))

    if not candidatos:
        return None

    candidatos.sort(key=lambda item: item[:5])
    return candidatos[0][5]


def _montar_texto_alternativa(linhas_alternativa):
    """
    Junta as linhas de uma alternativa respeitando quebras no meio
    de palavras.

    O PDF costuma dividir palavras em fragmentos: "apresen" + "tar".
    Quando a linha original começa com espaço, o fragmento é colado ao
    anterior sem espaço; caso contrário, as palavras são separadas por
    um espaço simples.
    """

    if not linhas_alternativa:
        return ''

    partes = list(linhas_alternativa)
    partes[0] = re.sub(
        r'^\(?\s*[A-E]\s*\)?\s*[.\:\-]?\s*',
        '',
        partes[0],
        flags=re.IGNORECASE,
    )

    while partes and not partes[0].strip():
        partes.pop(0)

    if not partes:
        return ''

    resultado = partes[0].strip()
    colar_na_proxima = partes[0][:1].isspace()

    for parte in partes[1:]:
        limpo = parte.strip()
        if not limpo:
            continue
        resultado += limpo if colar_na_proxima else f' {limpo}'
        colar_na_proxima = parte[:1].isspace()

    return resultado


def extrair_alternativas_generico(texto):
    if not texto:
        return []

    texto = _expandir_alternativas_inline(texto)
    linhas = texto.splitlines()
    marcadores = _encontrar_marcadores_alternativas(
        linhas,
        permitir_marcadores_sem_pontuacao=True,
    )
    sequencia = _encontrar_sequencia_abced(marcadores)
    if not sequencia:
        return []

    limite_final = len(linhas)
    marcadores_posteriores = [
        marcador
        for marcador in marcadores
        if marcador['linha'] > sequencia[-1]['linha']
    ]
    proxima_sequencia = _encontrar_sequencia_abced(marcadores_posteriores)
    if proxima_sequencia:
        limite_final = proxima_sequencia[0]['linha']

    alternativas = []
    for indice, marcador in enumerate(sequencia):
        fim = (
            sequencia[indice + 1]['linha']
            if indice < 4
            else limite_final
        )
        partes = linhas[marcador['linha']:fim]
        texto_alternativa = limpar_texto_alternativa(
            limpar_conteudo_questao(
                _montar_texto_alternativa(partes)
            )
        )
        alternativas.append({
            'letra': marcador['letra'],
            'texto': texto_alternativa,
        })

    if [item['letra'] for item in alternativas] != ['A', 'B', 'C', 'D', 'E']:
        return []
    return alternativas


def separar_material_apos_alternativa(texto):
    if not texto:
        return '', ''

    marcadores = [
        'Leia o Texto', 'Leia os Textos', 'Leia o texto', 'Leia os textos',
        'Read the Text', 'Read the Texts', 'Read the text', 'Read the texts',
        'Lee el Texto', 'Lee los Textos', 'Lee el texto', 'Lee los textos',
        'Fonte:', 'Source:', 'Fuente:',
    ]
    posicoes = [texto.find(marcador) for marcador in marcadores if texto.find(marcador) != -1]
    if not posicoes:
        return texto.strip(), ''
    corte = min(posicoes)
    return texto[:corte].strip(), texto[corte:].strip()


# ============================================================
# IDIOMA E SEPARAÇÃO DE QUESTÕES
# ============================================================


def detectar_idioma_secao(linhas, linha_questao):
    for linha in reversed(linhas[:linha_questao + 1]):
        normalizada = _normalizar_busca(linha)
        if (
            re.search(r'\bOPCAO\s+(?:DE\s+)?INGLES\b', normalizada)
            or re.search(r'\bLINGUA\s+INGLESA\b', normalizada)
            or normalizada in {'INGLES', 'LINGUA INGLESA'}
        ):
            return 'Inglês'
        if (
            re.search(r'\bOPCAO\s+(?:DE\s+)?ESPANHOL\b', normalizada)
            or re.search(r'\bLINGUA\s+ESPANHOLA\b', normalizada)
            or normalizada in {'ESPANHOL', 'LINGUA ESPANHOLA'}
        ):
            return 'Espanhol'
    return None


def separar_questoes_generico(texto, preservar_blocos_repetidos=False):
    linhas = texto.splitlines()
    marcadores = encontrar_marcadores_questoes(texto)
    if preservar_blocos_repetidos:
        marcadores = selecionar_blocos_enem(marcadores)
    else:
        marcadores = selecionar_bloco_principal(marcadores)

    textos_base = encontrar_textos_base(texto, marcadores)
    cabecalhos_textos_base = {
        texto_base['linha_cabecalho']
        for texto_base in textos_base
    }

    questoes = []
    for indice, marcador in enumerate(marcadores):
        linha_inicio = marcador['linha']
        linha_fim = marcadores[indice + 1]['linha'] if indice + 1 < len(marcadores) else len(linhas)

        # Um texto-base que começa dentro deste bloco pertence ao
        # próximo grupo de questões. Ele não deve contaminar o
        # enunciado da questão atual.
        for cabecalho in sorted(cabecalhos_textos_base):
            if linha_inicio < cabecalho < linha_fim:
                linha_fim = cabecalho
                break

        conteudo = limpar_conteudo_questao('\n'.join(linhas[linha_inicio + 1:linha_fim]))
        conteudo = _expandir_alternativas_inline(conteudo)
        alternativas = extrair_alternativas_generico(conteudo)
        enunciado = conteudo

        if len(alternativas) == 5:
            linhas_conteudo = conteudo.splitlines()
            marcadores_alternativas = _encontrar_marcadores_alternativas(
                linhas_conteudo,
                permitir_marcadores_sem_pontuacao=True,
            )
            sequencia = _encontrar_sequencia_abced(marcadores_alternativas)
            if sequencia:
                enunciado = limpar_conteudo_questao(
                    '\n'.join(linhas_conteudo[:sequencia[0]['linha']])
                )

        texto_apoio = ''
        for alternativa in alternativas:
            if alternativa['letra'] == 'E':
                alternativa['texto'], texto_apoio = separar_material_apos_alternativa(
                    alternativa['texto']
                )
                alternativa['texto'] = limpar_texto_alternativa(alternativa['texto'])
                break

        numero = marcador['numero']
        questoes.append({
            'numero': numero,
            'texto': enunciado,
            'alternativas': alternativas,
            '_texto_apoio': texto_apoio,
            '_linha': linha_inicio,
            '_idioma': detectar_idioma_secao(linhas, linha_inicio) if numero in range(1, 6) else None,
        })

    for indice, questao in enumerate(questoes):
        texto_apoio = questao.pop('_texto_apoio', '')
        if texto_apoio and indice + 1 < len(questoes):
            questoes[indice + 1]['texto'] = (
                texto_apoio + '\n\n' + questoes[indice + 1]['texto']
            ).strip()

    _associar_textos_base(questoes, textos_base)

    for questao in questoes:
        questao.pop('_linha', None)

    return questoes


def separar_questoes_enem(texto):
    return separar_questoes_generico(texto, preservar_blocos_repetidos=True)


# ============================================================
# GABARITO
# ============================================================


def _idioma_gabarito_na_linha(linhas, indice_linha):
    for linha in reversed(linhas[:indice_linha + 1]):
        normalizada = _normalizar_busca(linha)
        if re.search(r'\bOPCAO\s+INGLES\b', normalizada) or normalizada in {'INGLES', 'LINGUA INGLESA'}:
            return 'Inglês'
        if re.search(r'\bOPCAO\s+ESPANHOL\b', normalizada) or normalizada in {'ESPANHOL', 'LINGUA ESPANHOLA'}:
            return 'Espanhol'
    return None


def extrair_gabarito_generico(texto, preservar_idiomas=False, idioma_padrao=None):
    if not texto:
        return {}

    gabarito = {}
    linhas = texto.splitlines()
    for indice_linha, linha in enumerate(linhas):
        linha_limpa = linha.strip()
        duplo = re.match(
            r'^0*(\d{1,2})\s*[-.\:\)]?\s*([A-E])\s+([A-E])\b',
            linha_limpa,
            re.IGNORECASE,
        )
        if preservar_idiomas and duplo and int(duplo.group(1)) in range(1, 6):
            numero = int(duplo.group(1))
            gabarito[('Inglês', numero)] = duplo.group(2).upper()
            gabarito[('Espanhol', numero)] = duplo.group(3).upper()
            continue

        resultado = re.match(
            r'^0*(\d{1,3})\s*[-.\:\)]?\s*([A-E])\b',
            linha_limpa,
            re.IGNORECASE,
        )
        if not resultado:
            continue

        numero = int(resultado.group(1))
        letra = resultado.group(2).upper()
        idioma = None
        if preservar_idiomas and numero in range(1, 6):
            idioma = _idioma_gabarito_na_linha(linhas, indice_linha)
            if idioma is None:
                # Gabaritos separados por idioma (ENEM Digital 1º dia)
                # recebem o idioma informado pelo chamador. Nos
                # gabaritos bilíngues sem cabeçalho, a primeira
                # ocorrência é de Inglês e a segunda, de Espanhol.
                idioma = idioma_padrao
            if idioma is None:
                if ('Inglês', numero) not in gabarito:
                    idioma = 'Inglês'
                elif ('Espanhol', numero) not in gabarito:
                    idioma = 'Espanhol'

        gabarito[(idioma, numero) if idioma else numero] = letra
    return gabarito


def extrair_gabarito_enem(texto, idioma_padrao=None):
    """
    Extrai o gabarito oficial, preservando o idioma das questões 1–5.

    ``idioma_padrao`` é usado nos PDFs de gabarito separados por
    idioma (ENEM Digital 1º dia), que não têm cabeçalho de seção.
    """
    return extrair_gabarito_generico(
        texto,
        preservar_idiomas=True,
        idioma_padrao=idioma_padrao,
    )


def extrair_questoes_anuladas_gabarito(texto):
    """
    Localiza as questões marcadas como anuladas no gabarito oficial.

    O gabarito não traz letra para essas questões, portanto elas não
    podem ser importadas como se tivessem uma resposta correta.
    """
    anuladas = set()

    if not texto:
        return anuladas

    linhas = texto.splitlines()

    for indice_linha, linha in enumerate(linhas):
        resultado = re.match(
            r'^0*(\d{1,3})\s*[-.\:\)]?\s*ANULAD[OA]\b',
            linha.strip(),
            re.IGNORECASE,
        )

        if not resultado:
            continue

        numero = int(resultado.group(1))
        idioma = None

        if numero in range(1, 6):
            idioma = _idioma_gabarito_na_linha(linhas, indice_linha)

        anuladas.add((idioma, numero) if idioma else numero)

    return anuladas


def obter_resposta_gabarito(questao, gabarito):
    numero = questao['numero']
    idioma = questao.get('_idioma') or questao.get('idioma')
    if idioma and numero in range(1, 6):
        return gabarito.get((idioma, numero))
    return gabarito.get(numero)


def _idioma_efetivo_da_questao(questao):
    """Normaliza o idioma da mesma forma que a gravação no banco."""
    numero = questao['numero']
    idioma = questao.get('_idioma') or questao.get('idioma')
    if numero in range(1, 6) and idioma in {'Inglês', 'Espanhol'}:
        return idioma
    return None


def _chave_gabarito_da_questao(questao):
    numero = questao['numero']
    idioma = questao.get('_idioma') or questao.get('idioma')
    if idioma and numero in range(1, 6):
        return (idioma, numero)
    return numero


def _prefixo_questao(questao):
    """
    Monta o identificador exibido nas mensagens de problema.

    Quando a página é conhecida, ela é incluída para facilitar a
    localização no PDF. Sem página, o formato antigo é preservado.
    """
    numero = questao['numero']
    idioma = _idioma_efetivo_da_questao(questao)
    identificador = f'{idioma}: ' if idioma else ''
    pagina = questao.get('_pagina')
    pagina_texto = f' (página {pagina})' if pagina else ''
    return f'Questão {identificador}{numero}{pagina_texto}'


def validar_questoes_com_gabarito(questoes, gabarito, anuladas=None):
    anuladas = anuladas or set()
    erros = []
    if not questoes:
        erros.append('Nenhuma questão foi encontrada no PDF da prova.')
    for questao in questoes:
        alternativas = questao['alternativas']
        if len(alternativas) != 5:
            erros.append(
                f'{_prefixo_questao(questao)}: '
                f'{len(alternativas)} alternativas encontradas.'
            )
        if (
            _chave_gabarito_da_questao(questao) not in anuladas
            and obter_resposta_gabarito(questao, gabarito) is None
        ):
            erros.append(
                f'{_prefixo_questao(questao)}: gabarito não encontrado.'
            )
    return erros


def _problemas_da_questao(questao):
    """Lista os problemas individuais de uma questão extraída."""
    erros = []
    prefixo = _prefixo_questao(questao)
    letras_esperadas = ['A', 'B', 'C', 'D', 'E']
    artefato_impressao = re.compile(
        r'ENEM\s*\d{4}|\*?\d{6}[A-Z]{2}\d+\*?',
        re.IGNORECASE,
    )

    alternativas = questao.get('alternativas') or []
    letras = [alternativa.get('letra') for alternativa in alternativas]

    if not (questao.get('texto') or '').strip():
        erros.append(f'{prefixo}: enunciado sem texto.')

    if letras != letras_esperadas:
        erros.append(
            f'{prefixo}: letras encontradas '
            f'{letras!r}; esperado {letras_esperadas!r}.'
        )
        return erros

    for alternativa in alternativas:
        texto = (alternativa.get('texto') or '').strip()
        tem_imagem = bool(
            alternativa.get('_imagem_alternativa')
            or alternativa.get('imagem_alternativa')
        )

        if not texto and not tem_imagem:
            erros.append(
                f'{prefixo}: alternativa '
                f'{alternativa.get("letra")} sem texto.'
            )
        elif texto and artefato_impressao.search(texto):
            erros.append(
                f'{prefixo}: alternativa '
                f'{alternativa.get("letra")} contém artefato de impressão.'
            )

    return erros


def _descricao_chave_gabarito(chave_gabarito):
    if isinstance(chave_gabarito, tuple):
        idioma, numero = chave_gabarito
        return f'{idioma}: {numero}'
    return str(chave_gabarito)


def validar_estrutura_questoes(questoes, gabarito):
    """Valida a estrutura que será persistida pela interface de processamento."""
    erros = []
    chaves_vistas = set()
    chaves_gabarito_das_questoes = set()

    for questao in questoes:
        numero = questao['numero']
        idioma = _idioma_efetivo_da_questao(questao)
        chave = (numero, idioma)

        if chave in chaves_vistas:
            erros.append(
                f'{_prefixo_questao(questao)}: duplicada no PDF.'
            )
        else:
            chaves_vistas.add(chave)

        chaves_gabarito_das_questoes.add(
            _chave_gabarito_da_questao(questao)
        )
        erros.extend(_problemas_da_questao(questao))

    # Se o gabarito cita questões que não foram extraídas do PDF,
    # a extração está incompleta e isso precisa ser informado.
    for chave_gabarito in gabarito:
        if chave_gabarito in chaves_gabarito_das_questoes:
            continue
        erros.append(
            f'Gabarito contém a questão '
            f'{_descricao_chave_gabarito(chave_gabarito)}, '
            'mas ela não foi extraída da prova.'
        )

    return erros


def dividir_questoes_validas(questoes, gabarito, anuladas=None):
    """
    Separa as questões que podem ser importadas das que têm problemas.

    Uma questão inválida não impede a importação das demais. Os motivos
    são devolvidos individualmente para serem exibidos ao usuário.
    Questões anuladas no gabarito oficial são relatadas separadamente e
    não são importadas sem uma resposta correta.
    """
    anuladas = anuladas or set()
    validas = []
    problemas = []
    chaves_vistas = set()
    chaves_gabarito_das_questoes = set()

    for questao in questoes:
        numero = questao['numero']
        idioma = _idioma_efetivo_da_questao(questao)
        chave = (numero, idioma)
        motivos = []

        if chave in chaves_vistas:
            motivos.append(
                f'{_prefixo_questao(questao)}: duplicada no PDF.'
            )
        else:
            chaves_vistas.add(chave)

        chaves_gabarito_das_questoes.add(
            _chave_gabarito_da_questao(questao)
        )
        motivos.extend(_problemas_da_questao(questao))

        if _chave_gabarito_da_questao(questao) in anuladas:
            motivos.append(
                f'{_prefixo_questao(questao)}: '
                'anulada no gabarito oficial.'
            )
        elif obter_resposta_gabarito(questao, gabarito) is None:
            motivos.append(
                f'{_prefixo_questao(questao)}: gabarito não encontrado.'
            )

        if motivos:
            problemas.extend(motivos)
        else:
            validas.append(questao)

    for chave_gabarito in gabarito:
        if chave_gabarito in chaves_gabarito_das_questoes:
            continue
        problemas.append(
            f'Gabarito contém a questão '
            f'{_descricao_chave_gabarito(chave_gabarito)}, '
            'mas ela não foi extraída da prova.'
        )

    return validas, problemas


# ============================================================
# PREPARAÇÃO E IMPORTAÇÃO
# ============================================================


def preparar_questoes(questoes, gabarito=None):
    gabarito = gabarito or {}
    resultado = []
    for questao in questoes:
        alternativas = []
        resposta = obter_resposta_gabarito(questao, gabarito)
        for alternativa in questao['alternativas']:
            alternativas.append({
                'letra': alternativa['letra'],
                'texto': limpar_texto_alternativa(alternativa['texto']),
                'correta': resposta == alternativa['letra'],
                'imagem_alternativa': (
                    alternativa.get('_imagem_alternativa')
                    or alternativa.get('imagem_alternativa')
                ),
            })
        textos_base = []
        for texto_base in questao.get('textos_base') or []:
            textos_base.append({
                'chave': texto_base['chave'],
                'identificador': texto_base.get('identificador', ''),
                'titulo': texto_base.get('titulo', ''),
                'texto': texto_base['texto'],
                'ordem': texto_base.get('ordem', 0),
                'inicio': texto_base.get('inicio'),
                'fim': texto_base.get('fim'),
                'idioma': texto_base.get('idioma'),
            })
        resultado.append({
            'numero': questao['numero'],
            'texto': questao['texto'],
            'alternativas': alternativas,
            'idioma': (
                questao.get('_idioma')
                or questao.get('idioma')
            ),
            'textos_base': textos_base,
        })
    return resultado


def preparar_questoes_para_importacao(questoes, gabarito=None):
    return preparar_questoes(questoes, gabarito)


@transaction.atomic
def importar_questoes_no_banco(prova, questoes, gabarito=None):
    from .models import (
        Alternativa,
        Disciplina,
        Questao,
        QuestaoTextoBase,
        TextoBase,
    )

    gabarito = gabarito or {}
    Questao.objects.filter(prova=prova).delete()
    TextoBase.objects.filter(prova=prova).delete()
    quantidade_importada = 0

    for questao_data in questoes:
        numero = questao_data['numero']
        idioma = questao_data.get('idioma')
        if not (
            prova.tipo == 'enem'
            and numero in range(1, 6)
            and idioma in {'Inglês', 'Espanhol'}
        ):
            idioma = None

        nome_disciplina = idioma or 'Não classificada'
        disciplina, _ = Disciplina.objects.get_or_create(nome=nome_disciplina)
        questao = Questao.objects.create(
            prova=prova,
            disciplina=disciplina,
            numero=numero,
            idioma=idioma,
            enunciado=questao_data['texto'],
        )

        for posicao, texto_data in enumerate(
            questao_data.get('textos_base') or []
        ):
            texto_base, _ = TextoBase.objects.get_or_create(
                prova=prova,
                chave=texto_data['chave'],
                defaults={
                    'identificador': texto_data.get('identificador', ''),
                    'titulo': texto_data.get('titulo', ''),
                    'texto': texto_data['texto'],
                    'ordem': texto_data.get('ordem', posicao),
                },
            )
            QuestaoTextoBase.objects.get_or_create(
                texto_base=texto_base,
                questao=questao,
                defaults={'ordem': posicao},
            )

        resposta = obter_resposta_gabarito(
            {'numero': numero, 'idioma': idioma},
            gabarito,
        )
        for alternativa_data in questao_data['alternativas']:
            letra = alternativa_data['letra']
            if resposta is not None:
                # O gabarito lido do PDF tem prioridade sobre qualquer
                # marcação preparada anteriormente.
                correta = letra == resposta
            else:
                correta = alternativa_data.get('correta', False)

            imagem = None
            referencia_imagem = alternativa_data.get('imagem_alternativa')
            if referencia_imagem:
                from .models import ImagemProva

                filtros = {
                    'prova': prova,
                    'pagina': referencia_imagem['pagina'],
                    'indice_pagina': referencia_imagem['indice_pagina'],
                }

                hash_referencia = referencia_imagem.get('hash_sha256')
                if hash_referencia:
                    filtros['hash_sha256'] = hash_referencia

                imagem = ImagemProva.objects.filter(**filtros).first()

                if imagem is None and hash_referencia:
                    # Compatibilidade com referências antigas sem hash.
                    filtros.pop('hash_sha256')
                    imagem = ImagemProva.objects.filter(
                        **filtros
                    ).first()

                if imagem is None:
                    raise ValueError(
                        f'Questão {numero}: imagem da alternativa '
                        f'{letra} não foi extraída do PDF.'
                    )

            Alternativa.objects.create(
                questao=questao,
                letra=letra,
                texto=alternativa_data['texto'],
                correta=correta,
                imagem=imagem,
            )
        quantidade_importada += 1

    return quantidade_importada
