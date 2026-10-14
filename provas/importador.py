# ============================================================
# IMPORTADOR DE PROVAS EM PDF
# ============================================================

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
            r'ENEM\s*2024',
            linha_normalizada,
            flags=re.IGNORECASE,
        )
        if not (eh_codigo or eh_identificacao):
            resultado.append(linha)
    return '\n'.join(resultado)


def _remover_cauda_rodape_repetida(texto):
    """Remove uma cauda iniciada por duas ocorrências contíguas de ENEM2024."""
    if not texto:
        return ''

    repeticao = re.search(
        r'(?:ENEM\s*2024\s*){2,}',
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
    return limpar_texto('\n'.join(paginas))


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


def encontrar_marcadores_questoes(texto):
    marcadores = []
    for indice, linha in enumerate(texto.splitlines()):
        linha_busca = _normalizar_busca(linha)
        linha_busca = re.sub(r'^(QUESTION|PREGUNTA)\b', 'QUESTAO', linha_busca)
        resultado = re.match(
            r'^QUESTAO\s*0*(\d{1,3})(?:\b|\s|$)',
            linha_busca,
        )
        if resultado:
            marcadores.append({
                'numero': int(resultado.group(1)),
                'linha': indice,
            })
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
# ALTERNATIVAS
# ============================================================


def limpar_texto_alternativa(texto):
    if not texto:
        return ''

    texto = limpar_linhas_de_impressao(texto)
    texto = _remover_cauda_rodape_repetida(texto)
    texto = re.sub(
        r'\s*\*?\d{6}[A-Z]{2}\d+\*?'
        r'(?:\s+ENEM\s*2024\b.*)?$',
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
            r'\(?\s*([A-E])\s*\)?\s*[.\:\-]?\s*',
            linha_limpa,
            re.IGNORECASE,
        )
        if isolado:
            encontrados.append({
                'letra': isolado.group(1).upper(),
                'linha': indice,
                'isolado': True,
            })
            continue

        # Marcador junto do texto: exige pontuação para não confundir
        # frases legítimas como "A alternativa correta é...".
        pontuacao = r'(?:\)|[.\:\-])' if not permitir_marcadores_sem_pontuacao else r'(?:\)|[.\:\-])?'
        junto = re.match(
            rf'^\(?\s*([A-E])\s*{pontuacao}\s+(.+)$',
            linha_limpa,
            re.IGNORECASE,
        )
        if junto:
            encontrados.append({
                'letra': junto.group(1).upper(),
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
            quantidade_isolados = sum(
                marcador.get('isolado', False)
                for marcador in selecionados
            )
            candidatos.append((
                quantidade_isolados,
                selecionados[0]['linha'],
                distancia,
                selecionados,
            ))

    if not candidatos:
        return None

    # Marcadores isolados são mais confiáveis do que letras junto do texto.
    # Isso evita escolher um bloco A-E inline da questão seguinte quando o
    # bloco real da questão atual aparece primeiro no texto extraído.
    # Em empate, a sequência que aparece primeiro vence; a distância fica
    # apenas como critério final para manter a preferência por blocos compactos.
    candidatos.sort(key=lambda item: (-item[0], item[1], item[2]))
    return candidatos[0][3]


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
        if partes:
            partes[0] = re.sub(
                r'^\(?\s*[A-E]\s*\)?\s*[.\:\-]?\s*',
                '',
                partes[0],
                flags=re.IGNORECASE,
            )
        texto_alternativa = limpar_texto_alternativa(
            limpar_conteudo_questao('\n'.join(partes))
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
        if re.search(r'\bOPCAO\s+INGLES\b', normalizada):
            return 'Inglês'
        if re.search(r'\bOPCAO\s+ESPANHOL\b', normalizada):
            return 'Espanhol'
    return None


def separar_questoes_generico(texto, preservar_blocos_repetidos=False):
    linhas = texto.splitlines()
    marcadores = encontrar_marcadores_questoes(texto)
    if preservar_blocos_repetidos:
        marcadores = selecionar_blocos_enem(marcadores)
    else:
        marcadores = selecionar_bloco_principal(marcadores)

    questoes = []
    for indice, marcador in enumerate(marcadores):
        linha_inicio = marcador['linha']
        linha_fim = marcadores[indice + 1]['linha'] if indice + 1 < len(marcadores) else len(linhas)
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
            '_idioma': detectar_idioma_secao(linhas, linha_inicio) if numero in range(1, 6) else None,
        })

    for indice, questao in enumerate(questoes):
        texto_apoio = questao.pop('_texto_apoio', '')
        if texto_apoio and indice + 1 < len(questoes):
            questoes[indice + 1]['texto'] = (
                texto_apoio + '\n\n' + questoes[indice + 1]['texto']
            ).strip()

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


def extrair_gabarito_generico(texto, preservar_idiomas=False):
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
                if ('Inglês', numero) not in gabarito:
                    idioma = 'Inglês'
                elif ('Espanhol', numero) not in gabarito:
                    idioma = 'Espanhol'

        gabarito[(idioma, numero) if idioma else numero] = letra
    return gabarito


def extrair_gabarito_enem(texto):
    return extrair_gabarito_generico(texto, preservar_idiomas=True)


def obter_resposta_gabarito(questao, gabarito):
    numero = questao['numero']
    idioma = questao.get('_idioma') or questao.get('idioma')
    if idioma and numero in range(1, 6):
        return gabarito.get((idioma, numero))
    return gabarito.get(numero)


def validar_questoes_com_gabarito(questoes, gabarito):
    erros = []
    if not questoes:
        erros.append('Nenhuma questão foi encontrada no PDF da prova.')
    for questao in questoes:
        numero = questao['numero']
        alternativas = questao['alternativas']
        if len(alternativas) != 5:
            erros.append(f'Questão {numero}: {len(alternativas)} alternativas encontradas.')
        if obter_resposta_gabarito(questao, gabarito) is None:
            identificador = f'{questao.get("_idioma")}: ' if questao.get('_idioma') else ''
            erros.append(f'Questão {identificador}{numero}: gabarito não encontrado.')
    return erros


def validar_estrutura_questoes(questoes, gabarito):
    """Valida a estrutura que será persistida pela interface de processamento."""
    erros = []
    letras_esperadas = ['A', 'B', 'C', 'D', 'E']
    artefato_impressao = re.compile(
        r'ENEM\s*2024|\*?\d{6}[A-Z]{2}\d+\*?',
        re.IGNORECASE,
    )

    for questao in questoes:
        numero = questao['numero']
        identificador = f'{questao.get("_idioma")}: ' if questao.get('_idioma') else ''
        alternativas = questao.get('alternativas') or []
        letras = [alternativa.get('letra') for alternativa in alternativas]

        if not (questao.get('texto') or '').strip():
            erros.append(
                f'Questão {identificador}{numero}: enunciado sem texto.'
            )

        if letras != letras_esperadas:
            erros.append(
                f'Questão {identificador}{numero}: letras encontradas '
                f'{letras!r}; esperado {letras_esperadas!r}.'
            )
            continue

        for alternativa in alternativas:
            texto = (alternativa.get('texto') or '').strip()
            if not texto:
                erros.append(
                    f'Questão {identificador}{numero}: alternativa '
                    f'{alternativa.get("letra")} sem texto.'
                )
            elif artefato_impressao.search(texto):
                erros.append(
                    f'Questão {identificador}{numero}: alternativa '
                    f'{alternativa.get("letra")} contém artefato de impressão.'
                )

        if obter_resposta_gabarito(questao, gabarito) is None:
            continue

    return erros


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
            })
        resultado.append({
            'numero': questao['numero'],
            'texto': questao['texto'],
            'alternativas': alternativas,
            'idioma': questao.get('_idioma'),
        })
    return resultado


def preparar_questoes_para_importacao(questoes, gabarito=None):
    return preparar_questoes(questoes, gabarito)


@transaction.atomic
def importar_questoes_no_banco(prova, questoes, gabarito=None):
    from .models import Alternativa, Disciplina, Questao

    gabarito = gabarito or {}
    Questao.objects.filter(prova=prova).delete()
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

        resposta = obter_resposta_gabarito(
            {'numero': numero, 'idioma': idioma},
            gabarito,
        )
        for alternativa_data in questao_data['alternativas']:
            letra = alternativa_data['letra']
            Alternativa.objects.create(
                questao=questao,
                letra=letra,
                texto=alternativa_data['texto'],
                correta=alternativa_data.get('correta', resposta == letra),
            )
        quantidade_importada += 1

    return quantidade_importada
