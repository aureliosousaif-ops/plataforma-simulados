# ============================================================
# EXTRAÇÃO E ASSOCIAÇÃO DE IMAGENS DAS PROVAS
# ============================================================

import hashlib
import re
from io import BytesIO
from pathlib import Path

import pypdfium2 as pdfium
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from pypdf import PdfReader
from pypdf.generic import ContentStream

from .importador import (
    _PADRAO_LETRA_ISOLADA,
    _normalizar_busca,
    detectar_idioma_secao,
    encontrar_marcadores_questoes,
)


# ============================================================
# CONSTANTES
# ============================================================

# Formatos que podem ser gravados diretamente pelo ImageField.
EXTENSOES_PERMITIDAS = {
    'jpg', 'jpeg', 'png', 'gif', 'bmp',
    'tif', 'tiff', 'webp', 'jp2', 'jpx', 'j2k',
}

# Matriz identidade usada nas transformações do PDF.
MATRIZ_IDENTIDADE = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

# Altura considerada quando o PDF não informa o tamanho da página.
ALTURA_PAGINA_PADRAO = 842.0

# Fração superior da página em que uma imagem pode continuar a questão
# iniciada na página anterior.
LIMITE_TOPO_PAGINA = 0.75

# Cache em memória dos marcadores por assinatura do PDF.
_CACHE_MARCADORES = {}


# ============================================================
# MATRIZES E POSIÇÃO NO PDF
# ============================================================


def _multiplicar_matrizes(primeira, segunda):
    """
    Multiplica duas matrizes no formato (a, b, c, d, e, f) do PDF.
    """
    a1, b1, c1, d1, e1, f1 = primeira
    a2, b2, c2, d2, e2, f2 = segunda

    return (
        a1 * a2 + b1 * c2,
        a1 * b2 + b1 * d2,
        c1 * a2 + d1 * c2,
        c1 * b2 + d1 * d2,
        e1 * a2 + f1 * c2 + e2,
        e1 * b2 + f1 * d2 + f2,
    )


def _resolver_objeto(objeto):
    """
    Resolve um objeto indireto do PDF, mantendo dicionários simples.
    """
    if objeto is None:
        return None

    if hasattr(objeto, 'get_object'):
        try:
            return objeto.get_object()
        except Exception:
            return objeto

    return objeto


def _recursos_da_pagina(pagina):
    """
    Obtém o dicionário de recursos da página, inclusive herdados.
    """
    recursos = pagina.get('/Resources')

    if recursos is None and hasattr(pagina, 'get_inherited'):
        try:
            recursos = pagina.get_inherited('/Resources')
        except Exception:
            recursos = None

    return _resolver_objeto(recursos) or {}


def _xobjects_dos_recursos(recursos):
    """
    Obtém o dicionário /XObject de um dicionário de recursos.
    """
    xobjects = recursos.get('/XObject') if hasattr(recursos, 'get') else None
    return _resolver_objeto(xobjects) or {}


def _processar_conteudo(
    pagina,
    conteudo,
    matriz,
    recursos,
    posicoes,
    inline_posicoes,
    visitados,
):
    """
    Percorre operadores do content stream para estimar a posição das imagens.
    """
    if conteudo is None:
        return

    try:
        operacoes = conteudo.operations
    except Exception:
        return

    pilha = []

    for operandos, operador in operacoes:

        if operador == b'q':
            pilha.append(matriz)

        elif operador == b'Q':
            matriz = pilha.pop() if pilha else MATRIZ_IDENTIDADE

        elif operador == b'cm' and len(operandos) >= 6:
            try:
                nova_matriz = tuple(
                    float(valor) for valor in operandos[:6]
                )
            except (TypeError, ValueError):
                continue
            matriz = _multiplicar_matrizes(nova_matriz, matriz)

        elif operador == b'Do' and operandos:
            nome = str(operandos[0])
            xobjects = _xobjects_dos_recursos(recursos)
            objeto = xobjects.get(nome)

            if objeto is None:
                continue

            resolvido = _resolver_objeto(objeto)
            subtipo = str(resolvido.get('/Subtype', ''))
            referencia = getattr(objeto, 'indirect_reference', None)

            if referencia is None:
                referencia = getattr(resolvido, 'indirect_reference', None)

            if subtipo == '/Image':
                chave = getattr(referencia, 'idnum', None)
                if chave is None:
                    continue

                posicoes.setdefault(chave, []).append({
                    'x': matriz[4],
                    'y': matriz[5],
                    'largura_exibicao': (
                        (matriz[0] ** 2 + matriz[1] ** 2) ** 0.5
                    ),
                    'altura_exibicao': (
                        (matriz[2] ** 2 + matriz[3] ** 2) ** 0.5
                    ),
                })

            elif subtipo == '/Form':
                chave_form = getattr(referencia, 'idnum', None)
                if chave_form is None:
                    chave_form = id(resolvido)

                if chave_form in visitados:
                    continue

                matriz_form = matriz
                matriz_pdf = resolvido.get('/Matrix')

                if matriz_pdf and len(matriz_pdf) == 6:
                    try:
                        matriz_form = _multiplicar_matrizes(
                            tuple(float(valor) for valor in matriz_pdf),
                            matriz,
                        )
                    except (TypeError, ValueError):
                        pass

                recursos_form = _resolver_objeto(
                    resolvido.get('/Resources')
                ) or recursos

                try:
                    conteudo_form = ContentStream(resolvido, pagina.pdf)
                except Exception:
                    continue

                _processar_conteudo(
                    pagina,
                    conteudo_form,
                    matriz_form,
                    recursos_form,
                    posicoes,
                    inline_posicoes,
                    visitados | {chave_form},
                )

        elif operador == b'INLINE IMAGE':
            inline_posicoes.append({
                'x': matriz[4],
                'y': matriz[5],
                'largura_exibicao': (
                    (matriz[0] ** 2 + matriz[1] ** 2) ** 0.5
                ),
                'altura_exibicao': (
                    (matriz[2] ** 2 + matriz[3] ** 2) ** 0.5
                ),
            })


def _extrair_posicoes_pagina(pagina):
    """
    Retorna as posições estimadas das imagens e das imagens inline.
    """
    posicoes = {}
    inline_posicoes = []

    try:
        conteudo = pagina.get_contents()
        recursos = _recursos_da_pagina(pagina)
        _processar_conteudo(
            pagina,
            conteudo,
            MATRIZ_IDENTIDADE,
            recursos,
            posicoes,
            inline_posicoes,
            set(),
        )
    except Exception:
        # Posição é apenas uma ajuda para as sugestões. A extração
        # dos bytes e das dimensões continua funcionando sem ela.
        return posicoes, inline_posicoes

    return posicoes, inline_posicoes


# ============================================================
# TEXTO E MARCADORES COM POSIÇÃO
# ============================================================


def _linhas_posicionadas(pagina):
    """
    Agrupa fragmentos de texto em linhas com coordenadas aproximadas.

    Quando o PDF não fornece fragmentos úteis, cai para o texto simples,
    sem coordenadas.
    """
    fragmentos = []

    def visitante(texto, matriz_texto, matriz_linha, fonte, tamanho):
        if not texto:
            return

        x = (
            matriz_linha[4] * matriz_texto[0]
            + matriz_linha[5] * matriz_texto[2]
            + matriz_texto[4]
        )
        y = (
            matriz_linha[4] * matriz_texto[1]
            + matriz_linha[5] * matriz_texto[3]
            + matriz_texto[5]
        )

        for parte in texto.replace('\r', '\n').split('\n'):
            parte = parte.strip()
            if parte:
                fragmentos.append({
                    'texto': parte,
                    'x': float(x),
                    'y': float(y),
                })

    try:
        pagina.extract_text(visitor_text=visitante)
    except Exception:
        fragmentos = []

    if not fragmentos:
        try:
            texto = pagina.extract_text() or ''
        except Exception:
            texto = ''

        return [
            {
                'texto': linha.strip(),
                'x': None,
                'y': None,
            }
            for linha in texto.splitlines()
            if linha.strip()
        ]

    # Agrupa fragmentos que estão na mesma altura.
    fragmentos.sort(key=lambda item: (-item['y'], item['x']))
    grupos = []

    for fragmento in fragmentos:
        if (
            not grupos
            or abs(fragmento['y'] - grupos[-1]['y']) > 2.5
        ):
            grupos.append({
                'y': fragmento['y'],
                'fragmentos': [fragmento],
            })
        else:
            grupos[-1]['fragmentos'].append(fragmento)

    linhas = []

    for grupo in grupos:
        atuais = []

        for fragmento in sorted(
            grupo['fragmentos'],
            key=lambda item: item['x'],
        ):
            if (
                atuais
                and fragmento['x'] - atuais[-1]['x'] > 60
            ):
                linhas.append({
                    'texto': ' '.join(
                        item['texto'] for item in atuais
                    ),
                    'x': atuais[0]['x'],
                    'y': grupo['y'],
                })
                atuais = []

            atuais.append(fragmento)

        if atuais:
            linhas.append({
                'texto': ' '.join(item['texto'] for item in atuais),
                'x': atuais[0]['x'],
                'y': grupo['y'],
            })

    linhas.sort(key=lambda item: (-item['y'], item['x']))
    return linhas


def mapear_marcadores_pdf(caminho_pdf):
    """
    Lê o PDF e devolve os marcadores de questão com página e posição.

    Cada item contém: pagina, numero, idioma, x, y, altura_pagina e ordem.
    O resultado é cacheado pela assinatura do arquivo (caminho, tamanho e
    data de modificação) para evitar releituras do mesmo PDF.
    """
    caminho = Path(caminho_pdf)

    try:
        informacoes = caminho.stat()
        assinatura = (
            str(caminho.resolve()),
            informacoes.st_size,
            informacoes.st_mtime_ns,
        )
    except OSError:
        assinatura = None

    if assinatura is not None and assinatura in _CACHE_MARCADORES:
        return [dict(marcador) for marcador in _CACHE_MARCADORES[assinatura]]

    leitor = PdfReader(caminho_pdf)
    marcadores = []
    idioma_corrente = None

    for numero_pagina, pagina in enumerate(leitor.pages, start=1):

        linhas = _linhas_posicionadas(pagina)

        try:
            altura_pagina = float(pagina.mediabox.height)
        except Exception:
            altura_pagina = ALTURA_PAGINA_PADRAO

        textos = [linha['texto'] for linha in linhas]

        for indice, linha in enumerate(linhas):
            normalizada = _normalizar_busca(linha['texto'])

            if (
                re.search(r'\bOPCAO\s+INGLES\b', normalizada)
                or normalizada in {'INGLES', 'LINGUA INGLESA'}
            ):
                idioma_corrente = 'Inglês'

            elif (
                re.search(r'\bOPCAO\s+ESPANHOL\b', normalizada)
                or normalizada in {'ESPANHOL', 'LINGUA ESPANHOLA'}
            ):
                idioma_corrente = 'Espanhol'

            encontrados = encontrar_marcadores_questoes(
                linha['texto']
            )

            for encontrado in encontrados:
                numero = encontrado['numero']
                idioma = None

                if numero in range(1, 6):
                    try:
                        idioma = detectar_idioma_secao(textos, indice)
                    except Exception:
                        idioma = None

                    idioma = idioma or idioma_corrente

                marcadores.append({
                    'pagina': numero_pagina,
                    'numero': numero,
                    'idioma': idioma,
                    'x': linha['x'],
                    'y': linha['y'],
                    'altura_pagina': altura_pagina,
                    'ordem': len(marcadores),
                })

    if assinatura is not None:
        # Mantém o cache pequeno e descarta PDFs que não estão em uso.
        if len(_CACHE_MARCADORES) >= 8:
            _CACHE_MARCADORES.clear()

        _CACHE_MARCADORES[assinatura] = [
            dict(marcador) for marcador in marcadores
        ]

    return marcadores


# ============================================================
# ALTERNATIVAS COMPOSTAS POR IMAGENS
# ============================================================

# Tolerâncias usadas para ligar uma imagem ao marcador da alternativa.
# As coordenadas vêm do PDF e a imagem fica ligeiramente acima da
# linha de base da letra correspondente.
TOLERANCIA_Y_IMAGEM_ALTERNATIVA = 35.0
TOLERANCIA_X_IMAGEM_ALTERNATIVA = 80.0
MARGEM_ACIMA_PRIMEIRA_LETRA = 12.0

# Distância horizontal máxima entre uma letra e o marcador da questão
# que a antecede. Evita misturar as colunas esquerda e direita.
TOLERANCIA_X_MARCADOR_QUESTAO = 180.0


# ============================================================
# ALTERNATIVAS DESENHADAS DIRETAMENTE NO PDF (VETORIAIS)
# ============================================================

# Alturas e margens usadas para delimitar a região de cada
# alternativa desenhada. A letra fica no canto esquerdo da primeira
# linha do conteúdo; o desenho ocupa o espaço até a letra seguinte
# (ou até a margem inferior da página).
BANDA_ACIMA_LETRA = 12.0
MARGEM_INFERIOR_PAGINA_BANDA = 25.0
RECUO_X_BANDA = 15.0
MARGEM_X_DIREITA_BANDA = 15.0

# Índice inicial dentro da página para as imagens renderizadas. As
# imagens incorporadas usam índices a partir de zero; o deslocamento
# evita colisão na busca por (página, índice).
INDICE_BASE_RENDERIZADA = 1000

# Escala usada para rasterizar a região. O dobro gera aproximadamente
# 144 DPI, nítidos para leitura na tela.
ESCALA_RENDERIZACAO_BANDA = 2.0


def _letras_alternativas_pagina(pagina):
    """Localiza as letras A–E isoladas e suas posições na página."""
    letras = []

    for linha in _linhas_posicionadas(pagina):
        resultado = _PADRAO_LETRA_ISOLADA.fullmatch(linha['texto'].strip())

        if not resultado:
            continue

        letras.append({
            'letra': resultado.group(1).upper(),
            'x': linha['x'],
            'y': linha['y'],
        })

    return letras


def _marcador_acima_da_letra(letra, marcadores):
    """
    Encontra o marcador de questão imediatamente acima da letra.

    A coluna é limitada para que as alternativas da coluna direita não
    sejam atribuídas à questão da coluna esquerda (e vice-versa). Quando
    a página tem apenas um marcador acima da letra, ele é usado mesmo
    que a questão ocupe as duas colunas.
    """
    candidatos = [
        marcador
        for marcador in marcadores
        if (
            marcador.get('y') is not None
            and marcador['y'] >= letra['y']
        )
    ]

    if not candidatos:
        return None

    na_coluna = [
        marcador
        for marcador in candidatos
        if abs((marcador.get('x') or 0) - letra['x'])
        <= TOLERANCIA_X_MARCADOR_QUESTAO
    ]

    if na_coluna:
        candidatos = na_coluna
    elif len(candidatos) != 1:
        return None

    return min(candidatos, key=lambda marcador: marcador['y'] - letra['y'])


def _centro_vertical_imagem(imagem):
    if imagem.y is None:
        return None

    altura = imagem.altura_exibicao or 0
    return float(imagem.y) + float(altura) / 2


def associar_imagens_as_letras(letras, imagens):
    """
    Associa uma imagem a cada letra A–E pela geometria do PDF.

    Somente devolve o mapa quando as cinco letras encontram imagens
    distintas na mesma coluna e na mesma faixa vertical. Caso contrário,
    a associação é considerada ambígua e nenhuma imagem é usada.
    """
    if len(letras) != 5:
        return None

    letras_ordenadas = sorted(letras, key=lambda item: item['letra'])

    if [item['letra'] for item in letras_ordenadas] != ['A', 'B', 'C', 'D', 'E']:
        return None

    primeira_y = letras_ordenadas[0]['y']
    disponiveis = [
        imagem
        for imagem in imagens
        if imagem.x is not None and imagem.y is not None
    ]
    usadas = set()
    resultado = {}

    for letra in letras_ordenadas:
        candidatos = []

        for imagem in disponiveis:
            if imagem.indice_pagina in usadas:
                continue

            centro = _centro_vertical_imagem(imagem)

            if centro is None:
                continue

            # Imagens acima da primeira letra pertencem ao enunciado.
            if centro > primeira_y + MARGEM_ACIMA_PRIMEIRA_LETRA:
                continue

            distancia_x = abs(imagem.x - letra['x'])
            if distancia_x > TOLERANCIA_X_IMAGEM_ALTERNATIVA:
                continue

            distancia_y = abs(centro - letra['y'])
            if distancia_y > TOLERANCIA_Y_IMAGEM_ALTERNATIVA:
                continue

            candidatos.append((distancia_y, distancia_x, imagem))

        if not candidatos:
            return None

        escolhida = min(
            candidatos,
            key=lambda item: (item[0], item[1], item[2].indice_pagina),
        )[2]

        resultado[letra['letra']] = escolhida
        usadas.add(escolhida.indice_pagina)

    return resultado


def mapear_alternativas_por_imagem(prova):
    """
    Mapeia as questões cujas alternativas são imagens.

    O resultado usa a chave ``(numero, idioma)`` e contém a página e um
    dicionário ``letra -> ImagemProva``.
    """
    from .models import ImagemProva

    if not prova.arquivo_pdf:
        return {}

    caminho = prova.arquivo_pdf.path

    try:
        marcadores = mapear_marcadores_pdf(caminho)
    except Exception:
        return {}

    if not marcadores:
        return {}

    try:
        leitor = PdfReader(caminho)
    except Exception:
        return {}

    imagens_por_pagina = {}

    for imagem in ImagemProva.objects.filter(
        prova=prova,
        exibida=True,
        ignorada=False,
    ):
        imagens_por_pagina.setdefault(imagem.pagina, []).append(imagem)

    resultado = {}

    for numero_pagina in sorted({item['pagina'] for item in marcadores}):
        if numero_pagina < 1 or numero_pagina > len(leitor.pages):
            continue

        letras = _letras_alternativas_pagina(
            leitor.pages[numero_pagina - 1]
        )

        if not letras:
            continue

        marcadores_pagina = [
            marcador
            for marcador in marcadores
            if marcador['pagina'] == numero_pagina
        ]

        grupos = {}

        for letra in letras:
            marcador = _marcador_acima_da_letra(
                letra,
                marcadores_pagina,
            )

            if marcador is None:
                continue

            chave = (
                marcador['numero'],
                marcador.get('idioma') or None,
            )
            grupos.setdefault(chave, []).append(letra)

        for chave, letras_questao in grupos.items():
            if sorted(
                item['letra'] for item in letras_questao
            ) != ['A', 'B', 'C', 'D', 'E']:
                continue

            associacao = associar_imagens_as_letras(
                letras_questao,
                imagens_por_pagina.get(numero_pagina, []),
            )

            if associacao is None:
                continue

            resultado[chave] = {
                'pagina': numero_pagina,
                'letras': associacao,
            }

    return resultado


def anotar_imagens_nas_alternativas(prova, questoes):
    """
    Adiciona metadados de imagem às alternativas antes da validação.

    A gravação no banco só acontece durante a importação, quando as
    imagens já foram registradas por ``extrair_e_registrar_imagens``.
    """
    mapa = mapear_alternativas_por_imagem(prova)

    if not mapa:
        return 0

    anotadas = 0

    for questao in questoes:
        chave = (
            questao['numero'],
            questao.get('_idioma') or questao.get('idioma') or None,
        )
        informacoes = mapa.get(chave)

        if not informacoes:
            continue

        alternativas = questao.get('alternativas') or []

        if len(alternativas) != 5:
            continue

        for alternativa in alternativas:
            imagem = informacoes['letras'].get(
                alternativa.get('letra')
            )

            if imagem is None:
                continue

            alternativa['_imagem_alternativa'] = {
                'pagina': imagem.pagina,
                'indice_pagina': imagem.indice_pagina,
            }
            anotadas += 1

    return anotadas


def _texto_alternativa_vazio(texto):
    """
    Indica se o texto extraído da alternativa está efetivamente vazio.

    Além do texto em branco, considera vazio o fragmento ``/`` que
    alguns PDFs do ENEM deixam no canto inferior da página e que pode
    vazar como conteúdo da última alternativa.
    """
    return (texto or '').strip() in {'', '/'}


def mapear_letras_por_questao(caminho_pdf):
    """
    Agrupa as letras de alternativa A–E por questão, em ordem de leitura.

    Cada item contém letra, página e posição. As letras de páginas
    continuadas (sem marcador próprio) ficam com a questão do marcador
    anterior. Devolve também a largura de cada página.
    """
    marcadores = mapear_marcadores_pdf(caminho_pdf)

    try:
        leitor = PdfReader(caminho_pdf)
    except Exception:
        return {}, {}

    marcadores_por_pagina = {}
    for marcador in marcadores:
        marcadores_por_pagina.setdefault(
            marcador['pagina'], []
        ).append(marcador)

    eventos_por_pagina = {}
    larguras = {}

    for numero_pagina, pagina in enumerate(leitor.pages, start=1):
        try:
            larguras[numero_pagina] = float(pagina.mediabox.width)
        except Exception:
            larguras[numero_pagina] = 0.0

        letras = _letras_alternativas_pagina(pagina)

        if not letras and numero_pagina not in marcadores_por_pagina:
            continue

        eventos = [
            ('m', marcador)
            for marcador in marcadores_por_pagina.get(
                numero_pagina, []
            )
        ]
        for letra in letras:
            letra = dict(letra)
            letra['pagina'] = numero_pagina
            eventos.append(('l', letra))

        # Ordem de leitura: de cima para baixo. Marcadores e letras
        # na mesma altura mantêm a ordem de inserção (marcador antes).
        eventos.sort(key=lambda item: -float(item[1]['y'] or 0))
        eventos_por_pagina[numero_pagina] = eventos

    questao_corrente = None
    grupos = {}

    for numero_pagina in sorted(eventos_por_pagina):
        for tipo, item in eventos_por_pagina[numero_pagina]:
            if tipo == 'm':
                questao_corrente = (
                    item['numero'],
                    item.get('idioma') or None,
                )
                continue

            if questao_corrente is None:
                continue

            # Na página do marcador, a letra precisa estar na mesma
            # coluna da questão. Fragmentos isolados de fórmulas no
            # meio da página (um "e" solto de uma operação matemática,
            # por exemplo) são descartados aqui. Páginas continuadas,
            # sem marcador, não têm filtro: a questão ocupa a largura
            # toda da página.
            numero_marcador, _ = questao_corrente
            marcador_corrente = next(
                (
                    marcador
                    for marcador in marcadores_por_pagina.get(
                        numero_pagina, []
                    )
                    if marcador['numero'] == numero_marcador
                ),
                None,
            )

            if (
                marcador_corrente is not None
                and marcador_corrente.get('x') is not None
                and item.get('x') is not None
                and abs(
                    item['x'] - marcador_corrente['x']
                ) > TOLERANCIA_X_MARCADOR_QUESTAO
            ):
                continue

            grupos.setdefault(questao_corrente, []).append(item)

    return grupos, larguras


def _bandas_das_letras(letras, larguras):
    """
    Converte as linhas de letras A–E em regiões renderizáveis.

    A região de cada letra vai da sua linha até a linha da letra
    seguinte (ou até a margem inferior da página, quando a letra é a
    última da página). Devolve None quando as letras não formam a
    sequência completa A–E.
    """
    ordem = [item['letra'] for item in letras]

    if ordem != ['A', 'B', 'C', 'D', 'E']:
        return None

    bandas = []

    for indice, item in enumerate(letras):
        pagina = item['pagina']
        largura = larguras.get(pagina) or 0.0

        if largura <= 0 or item.get('y') is None:
            return None

        topo = float(item['y']) + BANDA_ACIMA_LETRA

        seguinte = (
            letras[indice + 1]
            if indice + 1 < len(letras)
            else None
        )

        if seguinte is not None and seguinte['pagina'] == pagina:
            base = float(seguinte['y']) + BANDA_ACIMA_LETRA
        else:
            base = MARGEM_INFERIOR_PAGINA_BANDA

        x0 = float(item.get('x') or 0) + RECUO_X_BANDA
        x1 = largura - MARGEM_X_DIREITA_BANDA

        if x1 - x0 <= 0 or topo - base <= 0:
            return None

        bandas.append({
            'letra': item['letra'],
            'pagina': pagina,
            'x0': x0,
            'x1': x1,
            'base': base,
            'topo': topo,
        })

    return bandas


def _renderizar_banda_png(caminho_pdf, banda):
    """
    Renderiza a região de uma alternativa como PNG.

    O recorte é feito no espaço de coordenadas do PDF e a rasterização
    usa o pypdfium2, que interpreta corretamente o conteúdo vetorial
    (fórmulas, diagramas e textos desenhados com trajetos).
    """
    documento = pdfium.PdfDocument(str(caminho_pdf))

    try:
        pagina = documento[banda['pagina'] - 1]

        try:
            largura = float(pagina.get_width())
            altura = float(pagina.get_height())
            recorte = (
                banda['x0'],
                banda['base'],
                max(largura - banda['x1'], 0.0),
                max(altura - banda['topo'], 0.0),
            )
            bitmap = pagina.render(
                scale=ESCALA_RENDERIZACAO_BANDA,
                crop=recorte,
            )
            imagem = bitmap.to_pil()
        finally:
            pagina.close()
    finally:
        documento.close()

    try:
        buffer = BytesIO()
        imagem.save(buffer, format='PNG', optimize=True)
        dados = buffer.getvalue()
        return dados, imagem.size
    finally:
        imagem.close()


def anotar_alternativas_vetoriais(prova, questoes):
    """
    Renderiza e associa as alternativas desenhadas diretamente no PDF.

    Algumas provas do ENEM (notadamente o ENEM Digital) apresentam
    alternativas como fórmulas químicas ou diagramas desenhados com
    trajetos vetoriais: não há texto extraível nem imagem incorporada,
    e a importação seria rejeitada por "alternativa sem texto".

    Quando todas as cinco letras da questão são localizadas, cada
    região é rasterizada, registrada como ``ImagemProva`` e referenci
    pela alternativa. O texto é zerado porque o conteúdo real é a
    imagem. Se qualquer letra faltar, a questão não é anotada e segue
    o comportamento anterior (rejeição com mensagem explícita).
    """
    from .models import ImagemProva

    if not prova.arquivo_pdf:
        return 0

    try:
        caminho = prova.arquivo_pdf.path
    except (ValueError, OSError):
        return 0

    candidatas = []

    for questao in questoes:
        alternativas = questao.get('alternativas') or []

        if len(alternativas) != 5:
            continue

        if any(
            alternativa.get('_imagem_alternativa')
            or alternativa.get('imagem_alternativa')
            for alternativa in alternativas
        ):
            continue

        if any(
            _texto_alternativa_vazio(alternativa.get('texto'))
            for alternativa in alternativas
        ):
            candidatas.append(questao)

    if not candidatas:
        return 0

    try:
        grupos, larguras = mapear_letras_por_questao(caminho)
    except Exception:
        return 0

    if not grupos:
        return 0

    anotadas = 0
    contadores_por_pagina = {}

    for questao in candidatas:
        chave = (
            questao['numero'],
            questao.get('_idioma') or questao.get('idioma') or None,
        )
        letras = grupos.get(chave)

        if not letras:
            # Questões de idioma (1–5) podem ter a chave com idioma
            # diferente entre a extração e os marcadores. Quando existe
            # um único grupo com o mesmo número, ele é usado.
            candidatos = [
                grupo
                for (numero, _), grupo in grupos.items()
                if numero == questao['numero']
            ]
            if len(candidatos) == 1:
                letras = candidatos[0]

        if not letras:
            continue

        bandas = _bandas_das_letras(letras, larguras)

        if bandas is None:
            continue

        # Todas as regiões são renderizadas antes de qualquer
        # gravação: uma falha não deixa a questão parcialmente anotada.
        renderizadas = []
        completa = True

        for banda in bandas:
            try:
                dados, tamanho = _renderizar_banda_png(
                    caminho,
                    banda,
                )
            except Exception:
                completa = False
                break

            renderizadas.append((banda, dados, tamanho))

        if not completa:
            continue

        with transaction.atomic():
            for banda, dados, tamanho in renderizadas:
                hash_sha256 = hashlib.sha256(dados).hexdigest()

                contador = contadores_por_pagina.setdefault(
                    banda['pagina'], 0
                )
                indice_pagina = INDICE_BASE_RENDERIZADA + contador
                contadores_por_pagina[banda['pagina']] = contador + 1

                existente = ImagemProva.objects.filter(
                    prova=prova,
                    hash_sha256=hash_sha256,
                    pagina=banda['pagina'],
                    indice_pagina=indice_pagina,
                ).first()

                if existente is None:
                    nome = _garantir_arquivo(
                        prova.id,
                        hash_sha256,
                        'png',
                        dados,
                    )
                    existente = ImagemProva.objects.create(
                        prova=prova,
                        arquivo=nome,
                        hash_sha256=hash_sha256,
                        pagina=banda['pagina'],
                        indice_pagina=indice_pagina,
                        nome_original=(
                            f'alternativa-'
                            f'{banda["pagina"]}-{banda["letra"]}.png'
                        ),
                        largura=tamanho[0],
                        altura=tamanho[1],
                        exibida=True,
                        x=banda['x0'],
                        y=banda['base'],
                        largura_exibicao=(
                            banda['x1'] - banda['x0']
                        ),
                        altura_exibicao=(
                            banda['topo'] - banda['base']
                        ),
                    )

                for alternativa in questao['alternativas']:
                    if alternativa.get('letra') != banda['letra']:
                        continue

                    alternativa['_imagem_alternativa'] = {
                        'pagina': banda['pagina'],
                        'indice_pagina': indice_pagina,
                        'hash_sha256': hash_sha256,
                    }
                    alternativa['texto'] = ''
                    anotadas += 1

    return anotadas


def anotar_paginas_questoes(prova, questoes):
    """
    Acrescenta a página de origem às questões extraídas.

    A página é usada nas mensagens de problema para que o usuário saiba
    exatamente onde procurar no PDF.
    """
    if not prova.arquivo_pdf:
        return 0

    try:
        marcadores = mapear_marcadores_pdf(prova.arquivo_pdf.path)
    except Exception:
        return 0

    paginas = {}

    for marcador in marcadores:
        chave = (
            marcador['numero'],
            marcador.get('idioma') or None,
        )
        paginas.setdefault(chave, marcador['pagina'])

    anotadas = 0

    for questao in questoes:
        chave = (
            questao['numero'],
            questao.get('_idioma') or questao.get('idioma') or None,
        )
        pagina = paginas.get(chave)

        if pagina is None:
            pagina = paginas.get((questao['numero'], None))

        if pagina is None:
            candidatas = [
                valor
                for (numero, _), valor in paginas.items()
                if numero == questao['numero']
            ]
            if len(set(candidatas)) == 1:
                pagina = candidatas[0]

        if pagina is None:
            continue

        questao['_pagina'] = pagina
        anotadas += 1

    return anotadas


# ============================================================
# EXTRAÇÃO DAS IMAGENS
# ============================================================


def _extensao_da_imagem(nome_original, formato):
    """
    Define uma extensão segura para o arquivo extraído.
    """
    extensao = Path(nome_original or '').suffix.lower().lstrip('.')

    if extensao == 'jpeg':
        extensao = 'jpg'

    if extensao in EXTENSOES_PERMITIDAS:
        return extensao

    formato = (formato or '').lower()

    if formato == 'jpeg':
        formato = 'jpg'

    if formato in EXTENSOES_PERMITIDAS:
        return formato

    return None


def _converter_para_png(imagem):
    """
    Converte uma imagem sem extensão reconhecida para PNG.
    """
    if imagem is None:
        return None

    buffer = BytesIO()
    imagem.save(buffer, format='PNG')
    return buffer.getvalue()


def extrair_imagens_pdf(caminho_pdf):
    """
    Extrai todas as imagens incorporadas ao PDF.

    Retorna uma lista de dicionários com bytes, dimensões, página,
    ordem na página, posição estimada e indicação de exibição.
    """
    leitor = PdfReader(caminho_pdf)
    resultado = []

    for numero_pagina, pagina in enumerate(leitor.pages, start=1):
        try:
            imagens = list(pagina.images)
        except Exception:
            continue

        posicoes, inline_posicoes = _extrair_posicoes_pagina(pagina)
        indice_inline = 0

        for indice, imagem_pdf in enumerate(imagens):
            dados = imagem_pdf.data or b''
            imagem_pil = imagem_pdf.image

            posicao = None
            referencia = imagem_pdf.indirect_reference
            chave = getattr(referencia, 'idnum', None)

            if chave is not None and posicoes.get(chave):
                posicao = posicoes[chave][0]

            elif imagem_pdf.is_inline:
                if indice_inline < len(inline_posicoes):
                    posicao = inline_posicoes[indice_inline]
                indice_inline += 1

            if not dados and imagem_pil is not None:
                formato = (imagem_pil.format or 'PNG').upper()
                if formato == 'JPEG':
                    formato = 'PNG'
                buffer = BytesIO()
                imagem_pil.save(buffer, format=formato)
                dados = buffer.getvalue()

            if not dados:
                continue

            formato = ''
            if imagem_pil is not None:
                formato = imagem_pil.format or ''

            extensao = _extensao_da_imagem(
                imagem_pdf.name,
                formato,
            )

            if extensao is None:
                dados = _converter_para_png(imagem_pil)
                if not dados:
                    continue
                extensao = 'png'

            largura = 0
            altura = 0
            if imagem_pil is not None:
                largura, altura = imagem_pil.size

            resultado.append({
                'dados': dados,
                'extensao': extensao,
                'nome_original': imagem_pdf.name or '',
                'largura': largura,
                'altura': altura,
                'pagina': numero_pagina,
                'indice_pagina': indice,
                'exibida': bool(imagem_pdf.is_displayed),
                'x': posicao.get('x') if posicao else None,
                'y': posicao.get('y') if posicao else None,
                'largura_exibicao': (
                    posicao.get('largura_exibicao') if posicao else None
                ),
                'altura_exibicao': (
                    posicao.get('altura_exibicao') if posicao else None
                ),
            })

    return resultado


# ============================================================
# PERSISTÊNCIA E DEDUPLICAÇÃO
# ============================================================


def _nome_arquivo_imagem(prova_id, hash_sha256, extensao):
    """
    Gera um caminho determinístico baseado no hash do conteúdo.
    """
    return (
        f'provas/imagens/{prova_id}/'
        f'{hash_sha256[:2]}/{hash_sha256}.{extensao}'
    )


def _garantir_arquivo(prova_id, hash_sha256, extensao, dados):
    """
    Grava o arquivo apenas uma vez, mesmo ao reprocessar o PDF.
    """
    nome = _nome_arquivo_imagem(
        prova_id,
        hash_sha256,
        extensao,
    )

    if default_storage.exists(nome):
        return nome

    return default_storage.save(nome, ContentFile(dados))


def extrair_e_registrar_imagens(prova, caminho_pdf=None):
    """
    Extrai as imagens do PDF e registra somente as ainda inexistentes.

    A deduplicação usa prova + hash + página + índice da imagem na página.
    O arquivo físico é compartilhado pelo hash.
    """
    from .models import ImagemProva

    caminho = caminho_pdf

    if not caminho and prova.arquivo_pdf:
        caminho = prova.arquivo_pdf.path

    if not caminho:
        raise ValueError(
            'A prova não possui um PDF para extração de imagens.'
        )

    imagens = extrair_imagens_pdf(caminho)
    criadas = 0
    reutilizadas = 0

    with transaction.atomic():

        for imagem in imagens:
            hash_sha256 = hashlib.sha256(
                imagem['dados']
            ).hexdigest()

            existente = ImagemProva.objects.filter(
                prova=prova,
                hash_sha256=hash_sha256,
                pagina=imagem['pagina'],
                indice_pagina=imagem['indice_pagina'],
            ).first()

            if existente is not None:
                campos_atualizados = []

                if (
                    not existente.arquivo
                    or not default_storage.exists(
                        existente.arquivo.name
                    )
                ):
                    nome = _garantir_arquivo(
                        prova.id,
                        hash_sha256,
                        imagem['extensao'],
                        imagem['dados'],
                    )
                    existente.arquivo.name = nome
                    campos_atualizados.append('arquivo')

                for campo in (
                    'largura',
                    'altura',
                    'exibida',
                    'x',
                    'y',
                    'largura_exibicao',
                    'altura_exibicao',
                ):
                    valor = imagem[campo]
                    if getattr(existente, campo) != valor:
                        setattr(existente, campo, valor)
                        campos_atualizados.append(campo)

                if campos_atualizados:
                    existente.save(update_fields=campos_atualizados)

                reutilizadas += 1
                continue

            nome = _garantir_arquivo(
                prova.id,
                hash_sha256,
                imagem['extensao'],
                imagem['dados'],
            )

            ImagemProva.objects.create(
                prova=prova,
                arquivo=nome,
                hash_sha256=hash_sha256,
                pagina=imagem['pagina'],
                indice_pagina=imagem['indice_pagina'],
                nome_original=imagem['nome_original'][:255],
                largura=imagem['largura'],
                altura=imagem['altura'],
                exibida=imagem['exibida'],
                x=imagem['x'],
                y=imagem['y'],
                largura_exibicao=imagem['largura_exibicao'],
                altura_exibicao=imagem['altura_exibicao'],
            )
            criadas += 1

    return {
        'extraidas': len(imagens),
        'criadas': criadas,
        'reutilizadas': reutilizadas,
    }


# ============================================================
# SUGESTÕES DE ASSOCIAÇÃO
# ============================================================


def _chave_questao(questao):
    """
    Normaliza a chave usada para localizar questões nos marcadores.
    """
    return (questao.numero, questao.idioma or None)


def _indice_questoes(questoes):
    """
    Monta índices por chave e por número.
    """
    por_chave = {}
    por_numero = {}

    for questao in questoes:
        por_chave[_chave_questao(questao)] = questao
        por_numero.setdefault(questao.numero, []).append(questao)

    return por_chave, por_numero


def _resolver_questao(marcador, por_chave, por_numero):
    """
    Localiza a questão correspondente a um marcador.

    Quando o idioma não foi identificado e existem duas variantes
    (Inglês/Espanhol), a associação fica ambígua e não é sugerida.
    """
    numero = marcador['numero']
    idioma = marcador.get('idioma') or None

    if (numero, idioma) in por_chave:
        return por_chave[(numero, idioma)]

    candidatos = por_numero.get(numero, [])

    if idioma is not None:
        # Alguns PDFs não repetem o cabeçalho de idioma em todas as
        # páginas. Se só existe uma questão com esse número, ela é
        # uma alternativa segura.
        if len(candidatos) == 1:
            return candidatos[0]
        return None

    if len(candidatos) == 1:
        return candidatos[0]

    sem_idioma = [
        questao for questao in candidatos
        if not questao.idioma
    ]

    if len(sem_idioma) == 1:
        return sem_idioma[0]

    return None


def _altura_pagina_da_imagem(imagem, marcadores):
    """
    Obtém a altura da página a partir dos marcadores do PDF.
    """
    for marcador in marcadores:
        altura = marcador.get('altura_pagina')

        if altura:
            return float(altura)

    return ALTURA_PAGINA_PADRAO


def _imagem_no_topo_da_pagina(imagem, marcadores):
    """
    Indica se a imagem está na faixa superior da página.

    Somente nesse caso ela pode continuar a questão iniciada na página
    anterior sem risco de pertencer a outra questão da página atual.
    """
    if imagem.y is None:
        return False

    altura_pagina = _altura_pagina_da_imagem(imagem, marcadores)
    altura_imagem = getattr(imagem, 'altura_exibicao', None) or 0
    topo_da_imagem = imagem.y + altura_imagem

    return topo_da_imagem >= altura_pagina * LIMITE_TOPO_PAGINA


def _filtrar_por_coluna(imagem, candidatos):
    """
    Prefere marcadores na mesma coluna da imagem, quando existirem.
    """
    if imagem.x is None or not candidatos:
        return candidatos

    mesma_coluna = [
        marcador
        for marcador in candidatos
        if (
            marcador.get('x') is None
            or abs(marcador['x'] - imagem.x) <= 180
        )
    ]

    return mesma_coluna or candidatos


def sugerir_questao_para_imagem(imagem, marcadores, questoes):
    """
    Sugere uma questão para a imagem usando página, número e posição.

    A imagem só é associada à página anterior quando sua página não
    possui marcadores e ela está no topo, indicando continuação. Quando
    a página possui marcadores, apenas eles são considerados.

    Retorna ``None`` quando a associação é ambígua.
    """
    if not marcadores or not questoes:
        return None

    por_chave, por_numero = _indice_questoes(questoes)

    marcadores_da_pagina = [
        marcador
        for marcador in marcadores
        if marcador['pagina'] == imagem.pagina
    ]

    if marcadores_da_pagina:

        if imagem.y is None:
            if len(marcadores_da_pagina) != 1:
                # Sem posição vertical e com vários marcadores na mesma
                # página, não há como escolher com segurança.
                return None

            candidatos = marcadores_da_pagina

        else:
            # No PDF, o eixo Y cresce para cima. O marcador está acima
            # da imagem quando seu Y é maior.
            candidatos = [
                marcador
                for marcador in marcadores_da_pagina
                if (
                    marcador.get('y') is not None
                    and marcador['y'] >= imagem.y - 2
                )
            ]

            candidatos = _filtrar_por_coluna(imagem, candidatos)

    else:
        # Página sem marcadores: a imagem pode ser continuação da última
        # questão iniciada antes, mas apenas se estiver no topo.
        if not _imagem_no_topo_da_pagina(imagem, marcadores):
            return None

        candidatos = [
            marcador
            for marcador in marcadores
            if marcador['pagina'] < imagem.pagina
        ]

        candidatos = _filtrar_por_coluna(imagem, candidatos)

    for marcador in reversed(candidatos):
        questao = _resolver_questao(
            marcador,
            por_chave,
            por_numero,
        )
        if questao is not None:
            return questao

    return None


def marcadores_da_prova(prova):
    """
    Devolve os marcadores do PDF da prova ou ``None`` se não for possível
    lê-lo.
    """
    if not prova.arquivo_pdf:
        return None

    try:
        return mapear_marcadores_pdf(prova.arquivo_pdf.path)
    except Exception:
        return None


def associacao_imagem_segura(associacao, marcadores=None):
    """
    Valida, somente em memória, se uma associação confirmada é segura.

    Associações manuais são respeitadas. Associações automáticas são
    revalidadas pela posição da imagem e pelos marcadores do PDF. Se o
    PDF não puder ser lido, mantém a confiança na associação gravada.
    """
    imagem = associacao.imagem
    questao = associacao.questao

    if associacao.origem != 'automatica':
        return True

    if imagem.prova_id != questao.prova_id:
        return False

    if marcadores is None:
        marcadores = marcadores_da_prova(questao.prova)

    if marcadores is None:
        # Sem PDF disponível não há geometria para revalidar.
        return True

    if not marcadores:
        return False

    return (
        sugerir_questao_para_imagem(imagem, marcadores, [questao])
        is questao
    )


def imagem_legada_segura(questao, marcadores=None):
    """
    Valida o campo legado ``Questao.imagem``.

    Imagens enviadas manualmente para ``questoes/`` são preservadas.
    Imagens extraídas do PDF só aparecem se a geometria confirmar que
    pertencem à questão.
    """
    from .models import ImagemProva

    if not questao.imagem:
        return False

    nome = questao.imagem.name

    imagem = ImagemProva.objects.filter(
        prova_id=questao.prova_id,
        arquivo=nome,
    ).first()

    if imagem is None:
        # Upload manual fora do pipeline de extração.
        return True

    if marcadores is None:
        marcadores = marcadores_da_prova(questao.prova)

    if marcadores is None:
        return True

    if not marcadores:
        return False

    return (
        sugerir_questao_para_imagem(imagem, marcadores, [questao])
        is questao
    )



@transaction.atomic
def gerar_sugestoes_associacao(prova):
    """
    Recria as sugestões automáticas não confirmadas da prova.

    Associações confirmadas e imagens ignoradas são preservadas.
    """
    from .models import ImagemProva, ImagemQuestao

    if not prova.arquivo_pdf:
        return 0

    imagens = list(
        ImagemProva.objects.filter(
            prova=prova,
            ignorada=False,
            exibida=True,
            alternativas_como_imagem__isnull=True,
        )
    )

    if not imagens:
        return 0

    questoes = list(prova.questoes.all())

    if not questoes:
        return 0

    try:
        marcadores = mapear_marcadores_pdf(
            prova.arquivo_pdf.path
        )
    except Exception:
        marcadores = []

    if not marcadores:
        return 0

    ImagemQuestao.objects.filter(
        imagem__prova=prova,
        confirmada=False,
        origem='automatica',
    ).delete()

    imagens_confirmadas = set(
        ImagemQuestao.objects.filter(
            imagem__prova=prova,
            confirmada=True,
        ).values_list('imagem_id', flat=True)
    )

    criadas = 0

    for imagem in imagens:
        if imagem.id in imagens_confirmadas:
            continue

        questao = sugerir_questao_para_imagem(
            imagem,
            marcadores,
            questoes,
        )

        if questao is None:
            continue

        _, criada = ImagemQuestao.objects.get_or_create(
            imagem=imagem,
            questao=questao,
            defaults={
                'confirmada': False,
                'origem': 'automatica',
                'ordem': (
                    imagem.pagina * 1000
                    + imagem.indice_pagina
                ),
            },
        )

        if criada:
            criadas += 1

    return criadas


# ============================================================
# CONFIRMAÇÃO E SINCRONIZAÇÃO
# ============================================================


def sincronizar_imagem_principal(questao):
    """
    Mantém o campo legado ``Questao.imagem`` alinhado às confirmações.

    Quando não há associação confirmada, limpa o campo apenas se ele
    apontar para uma imagem extraída da própria prova. Imagens antigas
    enviadas manualmente para ``questoes/`` são preservadas.
    """
    from .models import ImagemProva

    confirmadas = list(
        questao.imagens_associadas
        .filter(confirmada=True)
        .select_related('imagem')
        .order_by('ordem', 'id')
    )

    if confirmadas:
        nome = confirmadas[0].imagem.arquivo.name

        if nome and questao.imagem.name != nome:
            questao.imagem.name = nome
            questao.save(update_fields=['imagem'])

        return

    nome_atual = questao.imagem.name if questao.imagem else ''

    if not nome_atual:
        return

    pertence_a_prova = ImagemProva.objects.filter(
        prova_id=questao.prova_id,
        arquivo=nome_atual,
    ).exists()

    if pertence_a_prova:
        questao.imagem = None
        questao.save(update_fields=['imagem'])


@transaction.atomic
def associar_imagem(imagem, questao, origem='manual', confirmar=True):
    """
    Cria ou atualiza uma associação manual.

    Ao confirmar, remove outras associações da mesma imagem para que
    ela pertença a apenas uma questão.
    """
    from .models import ImagemQuestao

    associacoes_anteriores = list(
        ImagemQuestao.objects
        .filter(imagem=imagem)
        .exclude(questao=questao)
        .select_related('questao')
    )

    if confirmar:
        for anterior in associacoes_anteriores:
            questao_anterior = anterior.questao
            anterior.delete()
            sincronizar_imagem_principal(questao_anterior)

    associacao, _ = ImagemQuestao.objects.update_or_create(
        imagem=imagem,
        questao=questao,
        defaults={
            'confirmada': confirmar,
            'origem': origem,
            'ordem': (
                imagem.pagina * 1000
                + imagem.indice_pagina
            ),
        },
    )

    if confirmar:
        sincronizar_imagem_principal(questao)

    return associacao


@transaction.atomic
def confirmar_associacao(associacao):
    """
    Confirma uma sugestão, mantendo apenas uma confirmação por imagem.
    """
    from .models import ImagemQuestao

    outras = list(
        ImagemQuestao.objects
        .filter(
            imagem=associacao.imagem,
            confirmada=True,
        )
        .exclude(pk=associacao.pk)
        .select_related('questao')
    )

    for outra in outras:
        outra.confirmada = False
        outra.save(update_fields=['confirmada'])
        sincronizar_imagem_principal(outra.questao)

    associacao.confirmada = True
    associacao.save(update_fields=['confirmada'])
    sincronizar_imagem_principal(associacao.questao)

    return associacao


@transaction.atomic
def remover_associacao(associacao):
    """
    Remove uma associação e atualiza o campo legado da questão.
    """
    questao = associacao.questao
    associacao.delete()
    sincronizar_imagem_principal(questao)


@transaction.atomic
def ignorar_imagem(imagem, ignorar=True):
    """
    Oculta ou reativa uma imagem na revisão.

    Uma imagem com associação confirmada não pode ser ignorada sem que
    a associação seja removida antes.
    """
    if ignorar and imagem.associacoes.filter(
        confirmada=True
    ).exists():
        return False

    imagem.ignorada = ignorar
    imagem.save(update_fields=['ignorada'])

    if ignorar:
        imagem.associacoes.filter(
            confirmada=False,
            origem='automatica',
        ).delete()

    return True


@transaction.atomic
def confirmar_todas_sugestoes(prova):
    """
    Confirma todas as sugestões pendentes da prova.
    """
    from .models import ImagemQuestao

    sugestoes = list(
        ImagemQuestao.objects
        .filter(
            imagem__prova=prova,
            imagem__ignorada=False,
            confirmada=False,
        )
        .select_related('imagem', 'questao')
    )

    confirmadas = 0

    for sugestao in sugestoes:
        if ImagemQuestao.objects.filter(
            imagem=sugestao.imagem,
            confirmada=True,
        ).exclude(pk=sugestao.pk).exists():
            continue

        confirmar_associacao(sugestao)
        confirmadas += 1

    return confirmadas


# ============================================================
# PRESERVAÇÃO AO REPROCESSAR
# ============================================================


def capturar_confirmacoes(prova):
    """
    Guarda as confirmações antes de as questões serem recriadas.
    """
    from .models import ImagemQuestao

    return list(
        ImagemQuestao.objects
        .filter(
            questao__prova=prova,
            confirmada=True,
        )
        .values(
            'imagem_id',
            'questao__numero',
            'questao__idioma',
            'ordem',
        )
    )


@transaction.atomic
def restaurar_confirmacoes(prova, confirmacoes):
    """
    Reaplica confirmações nas novas questões com mesmo número/idioma.
    """
    from .models import ImagemProva, ImagemQuestao

    if not confirmacoes:
        return 0

    questoes = {
        (questao.numero, questao.idioma or None): questao
        for questao in prova.questoes.all()
    }

    imagens = set(
        ImagemProva.objects
        .filter(prova=prova)
        .values_list('id', flat=True)
    )

    restauradas = 0

    for item in confirmacoes:
        chave = (
            item['questao__numero'],
            item['questao__idioma'] or None,
        )
        questao = questoes.get(chave)

        if questao is None or item['imagem_id'] not in imagens:
            continue

        ImagemQuestao.objects.update_or_create(
            imagem_id=item['imagem_id'],
            questao=questao,
            defaults={
                'confirmada': True,
                'origem': 'manual',
                'ordem': item['ordem'],
            },
        )
        sincronizar_imagem_principal(questao)
        restauradas += 1

    return restauradas
