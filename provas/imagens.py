# ============================================================
# EXTRAÇÃO E ASSOCIAÇÃO DE IMAGENS DAS PROVAS
# ============================================================

import hashlib
import re
from io import BytesIO
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from pypdf import PdfReader
from pypdf.generic import ContentStream

from .importador import (
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
