# ============================================================
# IMPORTADOR DE PROVAS EM PDF
# ============================================================

# Este arquivo é responsável por:
#
# 1. Extrair texto dos PDFs
# 2. Localizar as questões
# 3. Separar questões duplicadas
# 4. Encontrar alternativas A, B, C, D e E
# 5. Corrigir textos de apoio que entram na alternativa E
# 6. Limpar códigos e rodapés dos PDFs
# 7. Extrair gabaritos
# 8. Validar as questões
# 9. Preparar os dados para importação
# 10. Importar questões para o banco
#
# O parser é genérico e não depende de uma quantidade
# específica de questões.
#
# Pode trabalhar com:
#
# 10, 20, 40, 45, 50, 90 etc.


# ============================================================
# IMPORTAÇÕES
# ============================================================

import re
import unicodedata

from django.db import transaction
from pypdf import PdfReader


# ============================================================
# 1. EXTRAIR TEXTO DO PDF
# ============================================================

def extrair_texto_pdf(caminho_pdf):
    """
    Extrai o texto de todas as páginas do PDF.
    """

    # Abre o arquivo PDF.
    reader = PdfReader(
        caminho_pdf
    )

    paginas = []

    # Percorre todas as páginas.
    for pagina in reader.pages:

        texto = pagina.extract_text()

        # Algumas páginas podem não retornar texto.
        if texto is None:
            texto = ""

        paginas.append(
            texto
        )

    # Junta todas as páginas.
    texto_completo = "\n".join(
        paginas
    )

    # Faz a limpeza inicial.
    return limpar_texto(
        texto_completo
    )


# ============================================================
# 2. LIMPAR TEXTO
# ============================================================

def limpar_texto(texto):
    """
    Faz uma limpeza básica do texto extraído do PDF.
    """

    if not texto:
        return ""

    # Padroniza as quebras de linha.
    texto = texto.replace(
        "\r\n",
        "\n"
    )

    texto = texto.replace(
        "\r",
        "\n"
    )

    # Remove espaços e tabs repetidos.
    texto = re.sub(
        r"[ \t]+",
        " ",
        texto
    )

    # Remove excesso de linhas vazias.
    texto = re.sub(
        r"\n{3,}",
        "\n\n",
        texto
    )

    return texto.strip()


# ============================================================
# 3. LIMPAR CONTEÚDO DE UMA QUESTÃO
# ============================================================

def limpar_conteudo_questao(texto):
    """
    Limpa o conteúdo individual de uma questão.
    """

    if not texto:
        return ""

    # Remove espaços externos.
    texto = texto.strip()

    # Remove espaços repetidos.
    texto = re.sub(
        r"[ \t]+",
        " ",
        texto
    )

    # Evita excesso de linhas vazias.
    texto = re.sub(
        r"\n{3,}",
        "\n\n",
        texto
    )

    return texto.strip()


# ============================================================
# 4. ENCONTRAR MARCADORES DAS QUESTÕES
# ============================================================

def encontrar_marcadores_questoes(texto):
    """
    Localiza onde cada questão começa.

    Aceita diferentes formas que podem aparecer
    durante a extração de um PDF:

        QUESTÃO 01
        QUESTAO 01
        QUESTˆO 01
        QUESTÃO 1
        QUESTAO 1
    """

    linhas = texto.splitlines()

    marcadores = []

    # Percorre todas as linhas do PDF.
    for indice, linha in enumerate(
        linhas
    ):

        linha_limpa = linha.strip()

        if not linha_limpa:
            continue

        # ----------------------------------------------------
        # Normaliza apenas o necessário para reconhecer
        # marcadores em português, inglês e espanhol.
        # ----------------------------------------------------

        linha_busca = (
            linha_limpa.upper()
        )

        # Corrige algumas representações comuns
        # encontradas na extração de PDFs.
        linha_busca = (
            linha_busca
            .replace(
                "QUESTÃO",
                "QUESTAO"
            )
            .replace(
                "QUESTAO",
                "QUESTAO"
            )
            .replace(
                "QUESTˆO",
                "QUESTAO"
            )
            .replace(
                "QUESTÃƒO",
                "QUESTAO"
            )
            .replace(
                "QUESTION",
                "QUESTAO"
            )
            .replace(
                "PREGUNTA",
                "QUESTAO"
            )
        )

        # ----------------------------------------------------
        # Procura o padrão:
        #
        # QUESTAO 01
        # QUESTAO 1
        # ----------------------------------------------------

        resultado = re.match(
            r"^\s*QUESTAO\s*0*(\d{1,3})\s*$",
            linha_busca
        )

        # ----------------------------------------------------
        # Alguns PDFs podem possuir texto adicional
        # na linha.
        # ----------------------------------------------------

        if resultado is None:

            resultado = re.match(
                r"^\s*QUESTAO\s*0*(\d{1,3})\b",
                linha_busca
            )

        # ----------------------------------------------------
        # Se encontrou uma questão...
        # ----------------------------------------------------

        if resultado:

            numero = int(
                resultado.group(1)
            )

            marcadores.append(
                {
                    "numero": numero,
                    "linha": indice,
                }
            )

    return marcadores


# ============================================================
# 5. SELECIONAR BLOCO PRINCIPAL
# ============================================================

def _dividir_blocos(marcadores):
    blocos = []

    if not marcadores:
        return blocos

    bloco_atual = [marcadores[0]]

    for marcador in marcadores[1:]:
        numero_anterior = bloco_atual[-1]['numero']
        numero_atual = marcador['numero']

        if numero_atual == numero_anterior + 1:
            bloco_atual.append(marcador)
        else:
            blocos.append(bloco_atual)
            bloco_atual = [marcador]

    if bloco_atual:
        blocos.append(bloco_atual)

    return blocos


def selecionar_bloco_principal(marcadores):
    """
    Seleciona as questões principais encontradas no PDF.

    Alguns PDFs possuem blocos repetidos.

    No ENEM identificado neste projeto, a estrutura é:

        BLOCO 0 → questões 1 a 5 em português
        BLOCO 1 → questões 1 a 5 em espanhol
                    + questões 6 a 90 em português

    Portanto, o resultado correto é:

        BLOCO 0 → 1 a 5
        BLOCO 1 → 6 a 90

    Para outros PDFs, a maior sequência contínua
    será utilizada.
    """

    # --------------------------------------------------------
    # 1. Verifica se existem marcadores.
    # --------------------------------------------------------

    if not marcadores:
        return []

    # --------------------------------------------------------
    # 2. Divide os marcadores em blocos contínuos.
    # --------------------------------------------------------

    blocos = _dividir_blocos(marcadores)

    # --------------------------------------------------------
    # 3. Estrutura especial encontrada no ENEM.
    # --------------------------------------------------------

    if len(blocos) >= 2:

        primeiro_bloco = (
            blocos[0]
        )

        segundo_bloco = (
            blocos[1]
        )

        numeros_primeiro = [
            marcador["numero"]
            for marcador in primeiro_bloco
        ]

        numeros_segundo = [
            marcador["numero"]
            for marcador in segundo_bloco
        ]

        # Primeiro bloco exatamente 1 a 5.
        primeiro_eh_1_a_5 = (
            numeros_primeiro
            == [1, 2, 3, 4, 5]
        )

        # Segundo bloco começa em 1
        # e possui questões a partir da 6.
        segundo_tem_6 = (
            numeros_segundo
            and numeros_segundo[0] == 1
            and 6 in numeros_segundo
        )

        if (
            primeiro_eh_1_a_5
            and segundo_tem_6
        ):

            # Mantém 1 a 5 do primeiro bloco.
            questoes_1_a_5 = (
                primeiro_bloco
            )

            # Mantém somente 6 em diante
            # do segundo bloco.
            questoes_6_a_90 = [
                marcador
                for marcador in segundo_bloco
                if marcador["numero"] >= 6
            ]

            return (
                questoes_1_a_5
                + questoes_6_a_90
            )

    # --------------------------------------------------------
    # 4. Regra genérica para outros PDFs.
    # --------------------------------------------------------

    maior_bloco = max(
        blocos,
        key=len
    )

    return maior_bloco


def selecionar_blocos_enem(marcadores):
    """
    Preserva as duas seções de língua estrangeira do ENEM.

    A estrutura esperada é um primeiro bloco 1–5 e um segundo
    bloco que reinicia em 1 e segue até a questão 90. Os cinco
    números repetidos pertencem a idiomas diferentes.
    """

    blocos = _dividir_blocos(marcadores)

    if len(blocos) >= 2:
        primeiro = [item['numero'] for item in blocos[0]]
        segundo = [item['numero'] for item in blocos[1]]

        if (
            primeiro == [1, 2, 3, 4, 5]
            and segundo
            and segundo[0] == 1
            and 6 in segundo
        ):
            return blocos[0] + blocos[1]

    return selecionar_bloco_principal(marcadores)


# ============================================================
# 6. LIMPAR RODAPÉS E CÓDIGOS DAS ALTERNATIVAS
# ============================================================

def limpar_texto_alternativa(texto):
    """
    Remove códigos e rodapés que o PDF pode anexar
    ao final do texto de uma alternativa.

    Exemplo:

        texto da alternativa.
        *010175AZ5* ENEM20E4 ...
    """

    if not texto:
        return ""

    # --------------------------------------------------------
    # Remove tudo a partir do código interno do PDF.
    #
    # Exemplos:
    #
    # *010175AZ5*
    # *010175AZ10*
    # *010175AZ31*
    # --------------------------------------------------------

    texto = re.sub(
    r"\s*\*\d+[A-Z0-9]+\*[\s\S]*$",
    "",
    texto,
    flags=re.IGNORECASE
)

    # Normaliza espaços.
    texto = re.sub(
        r"[ \t]+",
        " ",
        texto
    )

    # Remove espaços externos.
    return texto.strip()

# ============================================================
# 7. EXTRAIR ALTERNATIVAS
# ============================================================

def extrair_alternativas_generico(texto):
    """
    Extrai as alternativas A, B, C, D e E.

    Aceita formatos como:

        A
        texto da alternativa

        B
        texto da alternativa

    Também aceita:

        A texto da alternativa
        B texto da alternativa

        A) texto
        B. texto
        (C) texto

    O parser procura a sequência A-B-C-D-E e ignora
    marcadores falsos encontrados dentro do texto.
    """

    if not texto:
        return []

    # ========================================================
    # 1. SEPARAR O TEXTO EM LINHAS
    # ========================================================

    linhas = texto.splitlines()

    encontrados = []

    # ========================================================
    # 2. LOCALIZAR OS MARCADORES
    # ========================================================

    for indice, linha in enumerate(linhas):

        linha_limpa = linha.strip()

        if not linha_limpa:
            continue

        # ----------------------------------------------------
        # MARCADOR SOZINHO
        #
        # A
        # B
        # C
        # D
        # E
        #
        # Também aceita:
        # A)
        # B.
        # C:
        # D-
        # ----------------------------------------------------

        resultado = re.match(
            r"^\(?([A-E])\)?[\.\:\-]?$",
            linha_limpa
        )

        if resultado:

            encontrados.append(
                {
                    "letra": resultado.group(1).upper(),
                    "linha": indice,
                }
            )

            continue

        # ----------------------------------------------------
        # MARCADOR JUNTO DO TEXTO
        #
        # Exemplos:
        #
        # B identificar contextos...
        # C tirar proveito...
        #
        # Também aceita:
        #
        # A) texto...
        # B. texto...
        # C: texto...
        # ----------------------------------------------------

        resultado = re.match(
            r"^\(?([A-E])\)?(?:[\.\:\-])?\s+(.+)$",
            linha_limpa
        )

        if resultado:

            encontrados.append(
                {
                    "letra": resultado.group(1).upper(),
                    "linha": indice,
                }
            )

    # ========================================================
    # 3. PROCURAR A PRIMEIRA SEQUÊNCIA A-B-C-D-E
    # ========================================================

    sequencia = None

    for indice, marcador in enumerate(encontrados):

        # ----------------------------------------------------
        # A sequência sempre precisa começar com A.
        # ----------------------------------------------------

        if marcador["letra"] != "A":
            continue

        candidatos = [marcador]

        proxima_letra = "B"

        # ----------------------------------------------------
        # Procura B, C, D e E na ordem.
        #
        # Se aparecer um marcador falso no meio,
        # ele será ignorado.
        # ----------------------------------------------------

        for proximo in encontrados[indice + 1:]:

            if proximo["letra"] != proxima_letra:
                continue

            candidatos.append(proximo)

            if proxima_letra == "B":

                proxima_letra = "C"

            elif proxima_letra == "C":

                proxima_letra = "D"

            elif proxima_letra == "D":

                proxima_letra = "E"

            elif proxima_letra == "E":

                break

        # ----------------------------------------------------
        # Se encontrou A-B-C-D-E, terminou a busca.
        # ----------------------------------------------------

        if len(candidatos) == 5:

            sequencia = candidatos

            break

    # ========================================================
    # 4. SE NÃO ENCONTROU A-B-C-D-E
    # ========================================================

    if sequencia is None:

        return []

    alternativas = []

    # ========================================================
    # 5. EXTRAIR CADA ALTERNATIVA
    # ========================================================

    for indice, alternativa in enumerate(sequencia):

        letra = alternativa["letra"]

        inicio = alternativa["linha"]

        # ----------------------------------------------------
        # O final da alternativa é o início da próxima.
        # ----------------------------------------------------

        if indice < 4:

            fim = sequencia[
                indice + 1
            ]["linha"]

        else:

            fim = len(linhas)

        # ----------------------------------------------------
        # Pega as linhas da alternativa.
        # ----------------------------------------------------

        partes = linhas[
            inicio:fim
        ]

        # ----------------------------------------------------
        # Remove o marcador A/B/C/D/E da primeira linha.
        # ----------------------------------------------------

        if partes:

            partes[0] = re.sub(
                r"^\(?[A-E]\)?[\.\:\-]?\s*",
                "",
                partes[0],
                flags=re.IGNORECASE
            )

        # ----------------------------------------------------
        # Junta novamente o texto.
        # ----------------------------------------------------

        texto_alternativa = "\n".join(
            partes
        ).strip()

        # ----------------------------------------------------
        # Limpeza do conteúdo.
        # ----------------------------------------------------

        texto_alternativa = (
            limpar_conteudo_questao(
                texto_alternativa
            )
        )

        # ----------------------------------------------------
        # Remove códigos e rodapés do PDF.
        # ----------------------------------------------------

        texto_alternativa = (
            limpar_texto_alternativa(
                texto_alternativa
            )
        )

        # ----------------------------------------------------
        # Salva a alternativa.
        # ----------------------------------------------------

        alternativas.append(
            {
                "letra": letra,
                "texto": texto_alternativa,
            }
        )

    # ========================================================
    # 6. GARANTIR A SEQUÊNCIA A-B-C-D-E
    # ========================================================

    letras_encontradas = [
        alternativa["letra"]
        for alternativa in alternativas
    ]

    if letras_encontradas != [
        "A",
        "B",
        "C",
        "D",
        "E",
    ]:

        return []

    # ========================================================
    # 7. RETORNAR ALTERNATIVAS
    # ========================================================

    return alternativas
# ============================================================
# 8. SEPARAR TEXTO DE APOIO DA ALTERNATIVA E
# ============================================================

def separar_material_apos_alternativa(texto):
    """
    Separa o texto de apoio que foi absorvido
    pela alternativa E.
    """

    if not texto:
        return (
            "",
            ""
        )

    marcadores = [
        "Leia o Texto",
        "Leia os Textos",
        "Leia o texto",
        "Leia os textos",
        "Read the Text",
        "Read the Texts",
        "Read the text",
        "Read the texts",
        "Lee el Texto",
        "Lee los Textos",
        "Lee el texto",
        "Lee los textos",
        "Fonte:",
        "Source:",
        "Fuente:",
    ]

    posicoes = []

    for marcador in marcadores:

        posicao = texto.find(
            marcador
        )

        if posicao != -1:

            posicoes.append(
                posicao
            )

    if not posicoes:

        return (
            texto.strip(),
            ""
        )

    corte = min(
        posicoes
    )

    texto_alternativa = (
        texto[
            :corte
        ].strip()
    )

    texto_apoio = (
        texto[
            corte:
        ].strip()
    )

    return (
        texto_alternativa,
        texto_apoio
    )


def detectar_idioma_secao(linhas, linha_questao):
    """
    Detecta o idioma da seção ENEM que contém a questão.

    A classificação considera apenas o cabeçalho oficial da seção,
    nunca palavras isoladas encontradas no enunciado.
    """

    for linha in reversed(linhas[:linha_questao + 1]):
        normalizada = unicodedata.normalize(
            'NFKD',
            linha.upper()
        ).encode(
            'ASCII',
            'ignore'
        ).decode('ASCII')

        normalizada = re.sub(
            r'\s+',
            ' ',
            normalizada
        ).strip()

        if re.search(
            r'\bOPCAO\s+INGLES\b',
            normalizada
        ):
            return 'Inglês'

        if re.search(
            r'\bOPCAO\s+ESPANHOL\b',
            normalizada
        ):
            return 'Espanhol'

    return None

# ============================================================
# 9. SEPARAR QUESTÕES GENERICAMENTE
# ============================================================

def separar_questoes_generico(
    texto,
    preservar_blocos_repetidos=False
):
    """
    Separa questões de qualquer prova.

    O enunciado fica separado das alternativas.
    As alternativas A, B, C, D e E não são mais
    armazenadas dentro do campo enunciado.
    """

    # --------------------------------------------------------
    # 1. Divide o texto em linhas.
    # --------------------------------------------------------

    linhas = texto.splitlines()

    # --------------------------------------------------------
    # 2. Localiza as questões.
    # --------------------------------------------------------

    marcadores = encontrar_marcadores_questoes(texto)

    # --------------------------------------------------------
    # 3. Seleciona o bloco principal.
    # --------------------------------------------------------

    if preservar_blocos_repetidos:
        marcadores = selecionar_blocos_enem(
            marcadores
        )
    else:
        marcadores = selecionar_bloco_principal(
            marcadores
        )

    questoes = []

    # --------------------------------------------------------
    # 4. Se nenhuma questão foi encontrada.
    # --------------------------------------------------------

    if not marcadores:
        return questoes

    # ========================================================
    # 5. PERCORRER AS QUESTÕES
    # ========================================================

    for indice, marcador in enumerate(marcadores):

        numero = marcador["numero"]

        linha_inicio = marcador["linha"]

        # ----------------------------------------------------
        # Define o final da questão.
        # ----------------------------------------------------

        if indice + 1 < len(marcadores):

            linha_fim = (
                marcadores[
                    indice + 1
                ]["linha"]
            )

        else:

            linha_fim = len(linhas)

        # ----------------------------------------------------
        # Extrai o conteúdo bruto da questão.
        # ----------------------------------------------------

        bloco = linhas[
            linha_inicio + 1:
            linha_fim
        ]

        conteudo = "\n".join(
            bloco
        ).strip()

        # ----------------------------------------------------
        # Limpeza inicial.
        # ----------------------------------------------------

        conteudo = limpar_conteudo_questao(
            conteudo
        )

        # ----------------------------------------------------
        # Extrai as alternativas.
        # ----------------------------------------------------

        alternativas = (
            extrair_alternativas_generico(
                conteudo
            )
        )

        # ----------------------------------------------------
        # Inicializa o enunciado.
        # ----------------------------------------------------

        enunciado = conteudo

        # ----------------------------------------------------
        # Se encontrou 5 alternativas, precisamos remover
        # A, B, C, D e E do enunciado.
        #
        # O parser procura novamente os marcadores para
        # descobrir onde começa a primeira alternativa.
        # ----------------------------------------------------

        if len(alternativas) == 5:

            linhas_conteudo = (
                conteudo.splitlines()
            )

            marcadores_alternativas = []

            # ------------------------------------------------
            # Localiza possíveis marcadores.
            # ------------------------------------------------

            for indice_linha, linha in enumerate(
                linhas_conteudo
            ):

                linha_limpa = linha.strip()

                if not linha_limpa:
                    continue

                # --------------------------------------------
                # Marcador sozinho:
                #
                # A
                # B
                # C
                # D
                # E
                # --------------------------------------------

                resultado = re.match(
                    r"^\(?([A-E])\)?[\.\:\-]?$",
                    linha_limpa
                )

                if resultado:

                    marcadores_alternativas.append(
                        {
                            "letra": (
                                resultado.group(1).upper()
                            ),
                            "linha": indice_linha,
                        }
                    )

                    continue

                # --------------------------------------------
                # Marcador junto do texto.
                #
                # Exemplo:
                # B identificar contextos...
                # --------------------------------------------

                resultado = re.match(
                    r"^\(?([A-E])\)?(?:[\.\:\-])?\s+(.+)$",
                    linha_limpa
                )

                if resultado:

                    marcadores_alternativas.append(
                        {
                            "letra": (
                                resultado.group(1).upper()
                            ),
                            "linha": indice_linha,
                        }
                    )

            # ------------------------------------------------
            # Procura uma sequência A-B-C-D-E.
            # ------------------------------------------------

            sequencia = None

            for indice_marcador, marcador_alt in enumerate(
                marcadores_alternativas
            ):

                if marcador_alt["letra"] != "A":
                    continue

                candidatos = [
                    marcador_alt
                ]

                proxima_letra = "B"

                for proximo in (
                    marcadores_alternativas[
                        indice_marcador + 1:
                    ]
                ):

                    if proximo["letra"] != proxima_letra:
                        continue

                    candidatos.append(
                        proximo
                    )

                    if proxima_letra == "B":

                        proxima_letra = "C"

                    elif proxima_letra == "C":

                        proxima_letra = "D"

                    elif proxima_letra == "D":

                        proxima_letra = "E"

                    elif proxima_letra == "E":

                        break

                if len(candidatos) == 5:

                    sequencia = candidatos

                    break

            # ------------------------------------------------
            # Se encontrou A-B-C-D-E, tudo antes do A
            # será considerado o enunciado.
            # ------------------------------------------------

            if sequencia:

                primeira_alternativa = (
                    sequencia[0]["linha"]
                )

                enunciado = "\n".join(
                    linhas_conteudo[
                        :primeira_alternativa
                    ]
                ).strip()

                enunciado = (
                    limpar_conteudo_questao(
                        enunciado
                    )
                )

        # ----------------------------------------------------
        # Guarda temporariamente texto de apoio.
        # ----------------------------------------------------

        texto_apoio = ""

        # ----------------------------------------------------
        # Procura a alternativa E.
        # ----------------------------------------------------

        for alternativa in alternativas:

            if alternativa["letra"] != "E":
                continue

            texto_e = alternativa[
                "texto"
            ]

            # ------------------------------------------------
            # Separa eventual texto de apoio.
            # ------------------------------------------------

            (
                texto_alternativa,
                texto_apoio,
            ) = separar_material_apos_alternativa(
                texto_e
            )

            # ------------------------------------------------
            # Atualiza a alternativa E.
            # ------------------------------------------------

            alternativa[
                "texto"
            ] = limpar_texto_alternativa(
                texto_alternativa
            )

            break

        # ----------------------------------------------------
        # Cria a questão.
        # ----------------------------------------------------

        questao = {
            "numero": numero,
            "texto": enunciado,
            "alternativas": alternativas,
            "_texto_apoio": texto_apoio,
            "_idioma": (
                detectar_idioma_secao(
                    linhas,
                    linha_inicio
                )
                if numero in range(1, 6)
                else None
            ),
        }

        questoes.append(
            questao
        )

    # ========================================================
    # 6. TRANSFERIR TEXTOS DE APOIO
    # ========================================================

    for indice, questao in enumerate(
        questoes
    ):

        texto_apoio = questao.pop(
            "_texto_apoio",
            ""
        )

        if not texto_apoio:
            continue

        # ----------------------------------------------------
        # Procura a próxima questão.
        # ----------------------------------------------------

        if indice + 1 < len(
            questoes
        ):

            proxima_questao = questoes[
                indice + 1
            ]

            texto_original = (
                proxima_questao[
                    "texto"
                ]
            )

            proxima_questao[
                "texto"
            ] = (
                texto_apoio
                + "\n\n"
                + texto_original
            )

    # --------------------------------------------------------
    # Retorna as questões.
    # --------------------------------------------------------

    return questoes


# ============================================================
# 10. COMPATIBILIDADE COM O ENEM
# ============================================================

def separar_questoes_enem(texto):
    """
    Mantém compatibilidade com o código antigo.

    O ENEM passa a utilizar o parser genérico.
    """

    return separar_questoes_generico(
        texto,
        preservar_blocos_repetidos=True
    )


# ============================================================
# 11. EXTRAIR GABARITO GENERICAMENTE
# ============================================================

def _idioma_gabarito_na_linha(linhas, indice_linha):
    for linha in reversed(linhas[:indice_linha + 1]):
        normalizada = unicodedata.normalize(
            'NFKD',
            linha.upper()
        ).encode(
            'ASCII',
            'ignore'
        ).decode('ASCII')
        normalizada = re.sub(r'\s+', ' ', normalizada).strip()

        if re.search(r'\bOPCAO\s+INGLES\b', normalizada):
            return 'Inglês'
        if re.search(r'\bOPCAO\s+ESPANHOL\b', normalizada):
            return 'Espanhol'
        if normalizada in {'INGLES', 'LINGUA INGLESA'}:
            return 'Inglês'
        if normalizada in {'ESPANHOL', 'LINGUA ESPANHOLA'}:
            return 'Espanhol'

    return None


def extrair_gabarito_generico(
    texto,
    preservar_idiomas=False
):
    """
    Tenta localizar respostas no formato:

        1 A
        2 B
        3 C

    ou:

        01 - A
        02 - B
        03 - C
    """

    if not texto:
        return {}

    gabarito = {}

    linhas = texto.splitlines()

    # Percorre todas as linhas.
    for indice_linha, linha in enumerate(linhas):

        linha_limpa = (
            linha.strip()
        )

        # O gabarito oficial pode trazer as duas opções na mesma
        # linha: número, resposta de Inglês e resposta de Espanhol.
        # As duas colunas precisam ser preservadas separadamente.
        resultado_duplo = re.match(
            r"^0*(\d{1,2})\s*[\-\.\:\)]?\s*"
            r"([A-E])\s+([A-E])\b",
            linha_limpa,
            re.IGNORECASE
        )

        if (
            preservar_idiomas
            and resultado_duplo
            and int(resultado_duplo.group(1)) in range(1, 6)
        ):
            numero_duplo = int(resultado_duplo.group(1))
            gabarito[('Inglês', numero_duplo)] = (
                resultado_duplo.group(2).upper()
            )
            gabarito[('Espanhol', numero_duplo)] = (
                resultado_duplo.group(3).upper()
            )
            continue

        # Procura número + letra.
        resultado = re.match(
            r"^0*(\d{1,3})\s*[\-\.\:\)]?\s*([A-E])\b",
            linha_limpa,
            re.IGNORECASE
        )

        if resultado:

            numero = int(
                resultado.group(1)
            )

            letra = (
                resultado
                .group(2)
                .upper()
            )

            idioma = None
            if preservar_idiomas and numero in range(1, 6):
                idioma = _idioma_gabarito_na_linha(
                    linhas,
                    indice_linha
                )

                # Alguns extratores removem os cabeçalhos do gabarito.
                # Quando o mesmo número aparece novamente, preserva a
                # ordem das duas opções do ENEM em vez de sobrescrever.
                if idioma is None:
                    if ('Inglês', numero) not in gabarito:
                        idioma = 'Inglês'
                    elif ('Espanhol', numero) not in gabarito:
                        idioma = 'Espanhol'

            chave = (
                (idioma, numero)
                if idioma
                else numero
            )

            gabarito[chave] = letra

    return gabarito


# ============================================================
# 12. COMPATIBILIDADE COM O GABARITO DO ENEM
# ============================================================

def extrair_gabarito_enem(texto):
    """
    Mantém compatibilidade com o código anterior.

    Agora utiliza o extrator genérico.
    """

    return extrair_gabarito_generico(
        texto,
        preservar_idiomas=True
    )


def obter_resposta_gabarito(questao, gabarito):
    numero = questao['numero']
    idioma = questao.get('_idioma') or questao.get('idioma')

    if idioma and numero in range(1, 6):
        return gabarito.get((idioma, numero))

    return gabarito.get(numero)


# ============================================================
# 13. VALIDAR QUESTÕES E GABARITO
# ============================================================

def validar_questoes_com_gabarito(
    questoes,
    gabarito
):
    """
    Verifica:

    - quantidade de alternativas;
    - existência do gabarito.
    """

    erros = []

    if not questoes:
        erros.append(
            'Nenhuma questão foi encontrada no PDF da prova.'
        )

    # Percorre todas as questões.
    for questao in questoes:

        numero = questao[
            "numero"
        ]

        alternativas = questao[
            "alternativas"
        ]

        # ----------------------------------------------------
        # Verifica se possui 5 alternativas.
        # ----------------------------------------------------

        if len(
            alternativas
        ) != 5:

            erros.append(
                (
                    f"Questão {numero}: "
                    f"{len(alternativas)} "
                    "alternativas encontradas."
                )
            )

        # ----------------------------------------------------
        # Verifica se existe resposta no gabarito.
        # ----------------------------------------------------

        resposta = obter_resposta_gabarito(
            questao,
            gabarito
        )

        if resposta is None:

            erros.append(
                (
                    f"Questão {numero}: "
                    "gabarito não encontrado."
                )
            )

    return erros


# ============================================================
# 14. PREPARAR QUESTÕES
# ============================================================

def preparar_questoes(
    questoes,
    gabarito=None
):
    """
    Prepara as questões para utilização pelo sistema.
    """

    if gabarito is None:
        gabarito = {}

    resultado = []

    # Percorre todas as questões.
    for questao in questoes:

        numero = questao[
            "numero"
        ]

        alternativas = []

        # Percorre as alternativas.
        for alternativa in questao[
            "alternativas"
        ]:

            letra = alternativa[
                "letra"
            ]

            texto_alternativa = (
                alternativa[
                    "texto"
                ]
            )

            # Limpeza final de segurança.
            texto_alternativa = (
                limpar_texto_alternativa(
                    texto_alternativa
                )
            )

            # Verifica se é a resposta correta.
            resposta = obter_resposta_gabarito(
                questao,
                gabarito
            )
            correta = resposta == letra

            alternativas.append(
                {
                    "letra": letra,
                    "texto": texto_alternativa,
                    "correta": correta,
                }
            )

        resultado.append(
            {
                "numero": numero,
                "texto": questao[
                    "texto"
                ],
                "alternativas": alternativas,
                "idioma": questao.get(
                    "_idioma"
                ),
            }
        )

    return resultado


# ============================================================
# 15. IMPORTAR QUESTÕES NO BANCO
# ============================================================

@transaction.atomic
def importar_questoes_no_banco(
    prova,
    questoes,
    gabarito=None
):
    """
    Importa as questões e alternativas para o banco.

    Esta função procura os campos existentes nos modelos
    antes de criar os registros, evitando depender de uma
    quantidade fixa de campos.
    """

    # Importa os modelos somente quando a função for utilizada.
    from .models import (
        Alternativa,
        Disciplina,
        Questao,
    )

    if gabarito is None:
        gabarito = {}

    # Permite reprocessar uma prova que ainda não possui
    # simulados sem deixar questões antigas duplicadas.
    Questao.objects.filter(
        prova=prova
    ).delete()

    quantidade_importada = 0

    # ========================================================
    # PERCORRE AS QUESTÕES
    # ========================================================

    for questao_data in questoes:

        numero = questao_data[
            "numero"
        ]

        enunciado = questao_data[
            "texto"
        ]

        idioma = questao_data.get('idioma')
        if not (
            prova.tipo == 'enem'
            and numero in range(1, 6)
            and idioma in {'Inglês', 'Espanhol'}
        ):
            idioma = None

        # ----------------------------------------------------
        # Cria os dados básicos da questão.
        # ----------------------------------------------------

        dados_questao = {
            "prova": prova,
            "numero": numero,
            "enunciado": enunciado,
            "idioma": idioma,
        }

        # ----------------------------------------------------
        # Verifica se o modelo possui disciplina.
        # ----------------------------------------------------

        campos_questao = {
            campo.name
            for campo in Questao._meta.fields
        }

        if "disciplina" in campos_questao:

            nome_disciplina = (
                idioma
                if idioma
                else 'Não classificada'
            )

            disciplina, _ = Disciplina.objects.get_or_create(
                nome=nome_disciplina
            )

            dados_questao['disciplina'] = disciplina

        # ----------------------------------------------------
        # Cria a questão.
        # ----------------------------------------------------

        questao = Questao.objects.create(
            **dados_questao
        )

        # ====================================================
        # CRIA AS ALTERNATIVAS
        # ====================================================

        for alternativa_data in questao_data[
            "alternativas"
        ]:

            letra = alternativa_data[
                "letra"
            ]

            texto_alternativa = (
                alternativa_data[
                    "texto"
                ]
            )

            # Limpeza final antes de salvar.
            texto_alternativa = (
                limpar_texto_alternativa(
                    texto_alternativa
                )
            )

            correta = alternativa_data.get(
                'correta',
                gabarito.get(numero) == letra
            )

            # ------------------------------------------------
            # Cria a alternativa.
            # ------------------------------------------------

            Alternativa.objects.create(
                questao=questao,
                letra=letra,
                texto=texto_alternativa,
                correta=correta,
            )

        quantidade_importada += 1

    return quantidade_importada


# ============================================================
# 16. COMPATIBILIDADE COM O VIEWS.PY
# ============================================================

def preparar_questoes_para_importacao(
    questoes,
    gabarito=None
):
    """
    Mantém compatibilidade com o views.py.

    O sistema antigo utiliza o nome:

        preparar_questoes_para_importacao()

    Internamente, utilizamos:

        preparar_questoes()

    Assim não precisamos alterar o views.py.
    """

    # --------------------------------------------------------
    # Se nenhum gabarito foi informado,
    # utiliza um dicionário vazio.
    # --------------------------------------------------------

    if gabarito is None:
        gabarito = {}

    # --------------------------------------------------------
    # Reaproveita a função principal de preparação.
    # --------------------------------------------------------

    return preparar_questoes(
        questoes,
        gabarito
    )
