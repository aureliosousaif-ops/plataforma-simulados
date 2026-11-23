# ============================================================
# RENDERIZAÇÃO DAS PÁGINAS ORIGINAIS DAS PROVAS
# ============================================================

import json
import os
import re
import unicodedata
from pathlib import Path

import pypdfium2 as pdfium
from django.conf import settings
from pypdf import PdfReader

from .importador import encontrar_marcadores_questoes


# ============================================================
# CONSTANTES
# ============================================================

# Escala usada para rasterizar as páginas. A escala 2 gera imagens
# com aproximadamente 144 DPI, nítidas para leitura na tela.
ESCALA_RENDERIZACAO = 2.0

# Subpasta dentro de MEDIA_ROOT usada como cache das páginas.
PASTA_CACHE = 'provas/paginas'


# ============================================================
# CAMINHOS E ASSINATURA DO PDF
# ============================================================


def _caminho_pdf(prova):
    """Retorna o caminho absoluto do PDF ou None quando não houver arquivo."""
    if not prova or not prova.arquivo_pdf:
        return None

    try:
        caminho = Path(prova.arquivo_pdf.path)
    except (ValueError, OSError):
        return None

    if not caminho.exists():
        return None

    return caminho


def _assinatura_pdf(caminho_pdf):
    """
    Cria uma assinatura baseada no tamanho e na data do PDF.

    O cache é invalidado automaticamente quando o arquivo muda, sem
    precisar gravar nada no banco de dados.
    """
    informacao = caminho_pdf.stat()
    return f'{informacao.st_size}-{int(informacao.st_mtime)}'


def _pasta_cache(prova):
    """Pasta de cache da prova, dentro de MEDIA_ROOT."""
    return Path(settings.MEDIA_ROOT) / PASTA_CACHE / str(prova.pk)


def _caminho_pagina(prova, numero_pagina, assinatura):
    """Caminho do PNG em cache para uma página da prova."""
    return (
        _pasta_cache(prova)
        / assinatura
        / f'pagina-{numero_pagina:03d}.png'
    )


def _caminho_indice(prova, assinatura):
    """Caminho do índice de páginas em cache para uma prova."""
    return _pasta_cache(prova) / f'indice-{assinatura}.json'


def _salvar_arquivo(caminho, escrever):
    """
    Grava um arquivo de forma atômica.

    O conteúdo é escrito em um arquivo temporário e só depois movido
    para o destino, evitando que duas requisições leiam um PNG pela
    metade.
    """
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(caminho.suffix + '.tmp')

    try:
        escrever(temporario)
        os.replace(temporario, caminho)
    finally:
        if temporario.exists():
            temporario.unlink()


# ============================================================
# RENDERIZAÇÃO DE UMA PÁGINA
# ============================================================


def total_paginas(prova):
    """Retorna a quantidade de páginas do PDF da prova."""
    caminho_pdf = _caminho_pdf(prova)

    if caminho_pdf is None:
        return 0

    documento = pdfium.PdfDocument(str(caminho_pdf))

    try:
        return len(documento)
    finally:
        documento.close()


def renderizar_pagina(prova, numero_pagina):
    """
    Renderiza uma página do PDF como PNG e devolve o caminho em cache.

    A imagem é gravada em MEDIA_ROOT/provas/paginas/<prova>/<assinatura>/.
    Nenhum registro é criado ou alterado no banco de dados.
    """
    caminho_pdf = _caminho_pdf(prova)

    if caminho_pdf is None:
        raise ValueError('A prova não possui um PDF disponível.')

    try:
        numero_pagina = int(numero_pagina)
    except (TypeError, ValueError):
        raise ValueError('Número de página inválido.')

    assinatura = _assinatura_pdf(caminho_pdf)
    destino = _caminho_pagina(prova, numero_pagina, assinatura)

    if destino.exists() and destino.stat().st_size > 0:
        return destino

    documento = pdfium.PdfDocument(str(caminho_pdf))

    try:
        if numero_pagina < 1 or numero_pagina > len(documento):
            raise ValueError('Página fora do intervalo do PDF.')

        pagina = documento[numero_pagina - 1]

        try:
            bitmap = pagina.render(scale=ESCALA_RENDERIZACAO)
            imagem = bitmap.to_pil()

            try:
                _salvar_arquivo(
                    destino,
                    lambda temporario: imagem.save(
                        temporario,
                        format='PNG',
                        optimize=True,
                    ),
                )
            finally:
                imagem.close()
        finally:
            pagina.close()
    finally:
        documento.close()

    return destino


# ============================================================
# ÍNDICE DE QUESTÕES POR PÁGINA
# ============================================================


def _normalizar_busca(texto):
    """Normaliza o texto para comparações sem acentos e sem pontuação."""
    if not texto:
        return ''

    texto = unicodedata.normalize('NFKD', texto)
    texto = ''.join(
        caractere
        for caractere in texto
        if not unicodedata.combining(caractere)
    )
    texto = texto.lower()
    texto = re.sub(r'[^a-z0-9]+', ' ', texto)
    return re.sub(r'\s+', ' ', texto).strip()


def _trecho_busca(enunciado):
    """
    Extrai o trecho inicial do enunciado usado para localizar a página.

    Trechos muito curtos, como "TEXTO I", não são suficientes. Nesses
    casos o índice usa os marcadores de questão encontrados no PDF.
    """
    normalizado = _normalizar_busca(enunciado)

    if not normalizado:
        return ''

    palavras = normalizado.split()

    for quantidade in (16, 12, 8, 6):
        if len(palavras) >= quantidade:
            return ' '.join(palavras[:quantidade])

    return ' '.join(palavras)


def _paginas_por_marcador(textos_paginas):
    """
    Mapeia cada número de questão para as páginas em que ele aparece.

    O PDF do ENEM repete as questões 1 a 5 nas versões de Inglês e de
    Espanhol, por isso cada número pode apontar para mais de uma página.
    """
    paginas = {}

    for numero_pagina, texto in enumerate(textos_paginas, start=1):
        for marcador in encontrar_marcadores_questoes(texto):
            paginas.setdefault(marcador['numero'], [])
            if numero_pagina not in paginas[marcador['numero']]:
                paginas[marcador['numero']].append(numero_pagina)

    return paginas


def _localizar_pagina(questao, textos_normalizados, paginas_por_numero):
    """Descobre em qual página a questão começa."""
    candidatas = paginas_por_numero.get(questao.numero, [])
    trecho = _trecho_busca(questao.enunciado)

    # Primeiro tenta o trecho do enunciado entre as páginas em que o
    # marcador da questão aparece. Isso resolve as variantes de idioma.
    if trecho:
        for numero_pagina in candidatas:
            if trecho in textos_normalizados[numero_pagina - 1]:
                return numero_pagina

        for numero_pagina, texto in enumerate(textos_normalizados, start=1):
            if trecho in texto:
                return numero_pagina

    if not candidatas:
        return None

    # Nas questões 1 a 5, a versão de Espanhol aparece depois da versão
    # de Inglês no caderno.
    if questao.idioma == 'Espanhol':
        return max(candidatas)

    return min(candidatas)


def _carregar_indice(prova, assinatura):
    """Lê o índice em cache, quando existir e estiver íntegro."""
    caminho = _caminho_indice(prova, assinatura)

    if not caminho.exists():
        return None

    try:
        with caminho.open('r', encoding='utf-8') as arquivo:
            dados = json.load(arquivo)
    except (OSError, ValueError):
        return None

    if dados.get('assinatura') != assinatura:
        return None

    paginas = dados.get('paginas')

    return paginas if isinstance(paginas, dict) else None


def _gravar_indice(prova, assinatura, paginas):
    """Grava o índice em cache de forma atômica."""
    caminho = _caminho_indice(prova, assinatura)
    dados = {
        'assinatura': assinatura,
        'paginas': paginas,
    }

    def escrever(temporario):
        with temporario.open('w', encoding='utf-8') as arquivo:
            json.dump(dados, arquivo, ensure_ascii=False, indent=2)

    _salvar_arquivo(caminho, escrever)


def construir_indice_paginas(prova):
    """
    Constrói o mapa "número da questão -> página inicial" do PDF.

    O mapa inclui chaves no formato "numero" e "numero:idioma", pois
    as questões 1 a 5 possuem versões em Inglês e em Espanhol.
    """
    caminho_pdf = _caminho_pdf(prova)

    if caminho_pdf is None:
        return {}

    leitor = PdfReader(str(caminho_pdf))
    textos_paginas = [
        pagina.extract_text() or ''
        for pagina in leitor.pages
    ]
    textos_normalizados = [
        _normalizar_busca(texto)
        for texto in textos_paginas
    ]
    paginas_por_numero = _paginas_por_marcador(textos_paginas)

    paginas = {}

    for questao in prova.questoes.all():
        numero_pagina = _localizar_pagina(
            questao,
            textos_normalizados,
            paginas_por_numero,
        )

        if numero_pagina is None:
            continue

        paginas[str(questao.numero)] = numero_pagina

        if questao.idioma:
            paginas[
                f'{questao.numero}:{questao.idioma}'
            ] = numero_pagina

    return paginas


def obter_indice_paginas(prova):
    """
    Devolve o índice de páginas da prova, usando cache em disco.

    Uma falha ao ler o PDF não deve impedir a visualização da questão.
    Nesse caso o índice vazio é devolvido.
    """
    caminho_pdf = _caminho_pdf(prova)

    if caminho_pdf is None:
        return {}

    assinatura = _assinatura_pdf(caminho_pdf)
    paginas = _carregar_indice(prova, assinatura)

    if paginas is not None:
        return paginas

    try:
        paginas = construir_indice_paginas(prova)
    except Exception:
        return {}

    try:
        _gravar_indice(prova, assinatura, paginas)
    except OSError:
        pass

    return paginas


def localizar_pagina_questao(prova, questao):
    """
    Retorna o número da página original em que a questão começa.

    Usa o índice do PDF e, como alternativa, a página da primeira
    imagem associada à questão.
    """
    if not prova or not questao:
        return None

    indice = obter_indice_paginas(prova)
    chave_com_idioma = f'{questao.numero}:{questao.idioma or ""}'

    pagina = indice.get(chave_com_idioma) or indice.get(str(questao.numero))

    if pagina:
        return pagina

    associacoes = getattr(questao, 'imagens_associadas', None)

    if associacoes is not None:
        paginas_associadas = [
            associacao.imagem.pagina
            for associacao in associacoes.all()
            if associacao.imagem_id and associacao.imagem.pagina
        ]

        if paginas_associadas:
            return min(paginas_associadas)

    return None
