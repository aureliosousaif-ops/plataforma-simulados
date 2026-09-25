# ============================================================
# IMPORTADOR DE PROVAS EM PDF
# ============================================================
#
# Este arquivo é responsável por:
#
# 1. Extrair texto dos PDFs
# 2. Localizar as questões
# 3. Separar questões duplicadas
# 4. Encontrar alternativas A, B, C, D e E
# 5. Corrigir textos de apoio que entram na alternativa E
# 6. Extrair gabaritos
# 7. Validar as questões
# 8. Preparar os dados para importação
# 9. Importar questões para o banco de dados
#
# O parser é genérico e não depende de uma quantidade
# específica de questões.
#
# Pode trabalhar com:
#
# 10, 20, 40, 45, 50, 90 etc.
#
# ============================================================


# ============================================================
# IMPORTAÇÕES
# ============================================================

import re

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
        # "QUESTÃO".
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
                "QUESTÃƒO",
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
        # Alguns PDFs podem possuir texto adicional na linha.
        # ----------------------------------------------------

        if resultado is None:

            resultado = re.search(
                r"\bQUESTAO\s*0*(\d{1,3})\b",
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

def selecionar_bloco_principal(marcadores):
    """
    Alguns PDFs possuem o mesmo bloco de questões repetido.

    Exemplo:

        1
        2
        3
        ...
        40

        1
        2
        3
        ...
        40

    Nesse caso, selecionamos somente o primeiro bloco.
    """

    if not marcadores:
        return []

    # --------------------------------------------------------
    # Procura uma segunda ocorrência da questão 1.
    # --------------------------------------------------------

    primeira_ocorrencia_1 = None

    for indice, marcador in enumerate(
        marcadores
    ):

        if marcador["numero"] != 1:
            continue

        # Primeira questão 1 encontrada.
        if primeira_ocorrencia_1 is None:

            primeira_ocorrencia_1 = indice

            continue

        # Segunda questão 1 encontrada.
        # O bloco anterior é considerado o principal.
        return marcadores[
            primeira_ocorrencia_1:
            indice
        ]

    # Se não houver repetição,
    # mantém todos os marcadores.
    return marcadores


# ============================================================
# 6. EXTRAIR ALTERNATIVAS
# ============================================================

def extrair_alternativas_generico(texto):
    """
    Extrai as alternativas A, B, C, D e E.

    Aceita formatos como:

        (A) texto
        (B) texto
        (C) texto
        (D) texto
        (E) texto

    Também aceita:

        A) texto
        B) texto

        A. texto
        B. texto

    O método procura uma sequência completa:

        A B C D E

    e utiliza a última sequência encontrada.
    """

    if not texto:
        return []

    linhas = texto.splitlines()

    encontrados = []

    # --------------------------------------------------------
    # Localiza possíveis alternativas.
    # --------------------------------------------------------

    for indice, linha in enumerate(
        linhas
    ):

        linha_limpa = linha.strip()

        if not linha_limpa:
            continue

        resultado = re.match(
            r"^\(?([A-E])\)?[\.\:\-]?\s+(.*)$",
            linha_limpa,
            re.IGNORECASE
        )

        if resultado:

            letra = (
                resultado
                .group(1)
                .upper()
            )

            conteudo = (
                resultado
                .group(2)
                .strip()
            )

            encontrados.append(
                {
                    "letra": letra,
                    "linha": indice,
                    "texto": conteudo,
                }
            )

    # --------------------------------------------------------
    # Se não encontrou alternativas.
    # --------------------------------------------------------

    if not encontrados:
        return []

    # --------------------------------------------------------
    # Procura uma sequência A B C D E.
    # --------------------------------------------------------

    sequencias = []

    for indice in range(
        len(encontrados)
    ):

        bloco = encontrados[
            indice:
            indice + 5
        ]

        if len(bloco) < 5:
            continue

        letras = [
            item["letra"]
            for item in bloco
        ]

        if letras == [
            "A",
            "B",
            "C",
            "D",
            "E",
        ]:

            sequencias.append(
                bloco
            )

    # --------------------------------------------------------
    # Se nenhuma sequência completa foi encontrada.
    # --------------------------------------------------------

    if not sequencias:
        return []

    # --------------------------------------------------------
    # Utiliza a última sequência encontrada.
    # --------------------------------------------------------

    sequencia = sequencias[
        -1
    ]

    alternativas = []

    # --------------------------------------------------------
    # Monta cada alternativa.
    # --------------------------------------------------------

    for indice, alternativa in enumerate(
        sequencia
    ):

        inicio = alternativa[
            "linha"
        ]

        # Define o fim da alternativa.
        if indice + 1 < len(
            sequencia
        ):

            fim = sequencia[
                indice + 1
            ]["linha"]

        else:

            fim = len(
                linhas
            )

        # Pega todas as linhas da alternativa.
        partes = linhas[
            inicio:
            fim
        ]

        if partes:

            # Remove o marcador A), B), C), etc.
            partes[0] = re.sub(
                r"^\(?[A-E]\)?[\.\:\-]?\s*",
                "",
                partes[0],
                flags=re.IGNORECASE
            )

        # Junta as linhas.
        texto_alternativa = "\n".join(
            partes
        ).strip()

        # Limpa o texto.
        texto_alternativa = (
            limpar_conteudo_questao(
                texto_alternativa
            )
        )

        alternativas.append(
            {
                "letra": alternativa[
                    "letra"
                ],
                "texto": texto_alternativa,
            }
        )

    return alternativas


# ============================================================
# 7. SEPARAR TEXTO DE APOIO DA ALTERNATIVA E
# ============================================================

def separar_material_apos_alternativa(texto):
    """
    Separa o texto de apoio que foi absorvido pela alternativa E.

    Exemplos:

        (E) resposta da questão.
        Leia o Texto II para responder às questões 03 e 04.

    ou:

        (E) resposta da questão.
        Fonte: SILVA, Luiza Helena...
    """

    # --------------------------------------------------------
    # Se não houver texto, não há nada para separar.
    # --------------------------------------------------------

    if not texto:
        return (
            "",
            ""
        )

    # --------------------------------------------------------
    # Marcadores de material que pode ter sido absorvido
    # pela alternativa E.
    #
    # "Fonte:" também é considerado material de apoio.
    # --------------------------------------------------------

    marcadores = [
        "Leia o Texto",
        "Leia os Textos",
        "Leia o texto",
        "Leia os textos",
        "Fonte:",
    ]

    posicoes = []

    # --------------------------------------------------------
    # Procura os marcadores.
    # --------------------------------------------------------

    for marcador in marcadores:

        posicao = texto.find(
            marcador
        )

        if posicao != -1:

            posicoes.append(
                posicao
            )

    # --------------------------------------------------------
    # Se não encontrou nenhum marcador,
    # mantém tudo como alternativa.
    # --------------------------------------------------------

    if not posicoes:

        return (
            texto.strip(),
            ""
        )

    # --------------------------------------------------------
    # Usa o primeiro marcador encontrado.
    # --------------------------------------------------------

    corte = min(
        posicoes
    )

    # --------------------------------------------------------
    # Parte que realmente pertence à alternativa.
    # --------------------------------------------------------

    texto_alternativa = (
        texto[
            :corte
        ]
        .strip()
    )

    # --------------------------------------------------------
    # Parte considerada material de apoio.
    # --------------------------------------------------------

    texto_apoio = (
        texto[
            corte:
        ]
        .strip()
    )

    return (
        texto_alternativa,
        texto_apoio
    )


# ============================================================
# 8. SEPARAR QUESTÕES GENERICAMENTE
# ============================================================

def separar_questoes_generico(texto):
    """
    Separa questões de qualquer prova.

    Pode trabalhar com:

        10 questões
        20 questões
        40 questões
        45 questões
        50 questões
        90 questões
        etc.

    Também corrige o problema encontrado no EXATO em que
    o início de um novo texto de apoio era colocado dentro
    da alternativa E.
    """

    # --------------------------------------------------------
    # Divide o texto em linhas.
    # --------------------------------------------------------

    linhas = texto.splitlines()

    # --------------------------------------------------------
    # Localiza as questões.
    # --------------------------------------------------------

    marcadores = encontrar_marcadores_questoes(
        texto
    )

    # --------------------------------------------------------
    # Remove blocos duplicados.
    # --------------------------------------------------------

    marcadores = selecionar_bloco_principal(
        marcadores
    )

    questoes = []

    # --------------------------------------------------------
    # Se nenhuma questão foi encontrada.
    # --------------------------------------------------------

    if not marcadores:
        return questoes

    # ========================================================
    # PERCORRE AS QUESTÕES
    # ========================================================

    for indice, marcador in enumerate(
        marcadores
    ):

        numero = marcador[
            "numero"
        ]

        linha_inicio = marcador[
            "linha"
        ]

        # ----------------------------------------------------
        # Define o final da questão.
        # ----------------------------------------------------

        if indice + 1 < len(
            marcadores
        ):

            linha_fim = (
                marcadores[
                    indice + 1
                ]["linha"]
            )

        else:

            linha_fim = len(
                linhas
            )

        # ----------------------------------------------------
        # Extrai o conteúdo.
        # ----------------------------------------------------

        bloco = linhas[
            linha_inicio + 1:
            linha_fim
        ]

        conteudo = "\n".join(
            bloco
        ).strip()

        # ----------------------------------------------------
        # Limpa o conteúdo.
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

            # Atualiza a alternativa E.
            alternativa[
                "texto"
            ] = texto_alternativa

            break

        # ----------------------------------------------------
        # Cria a questão.
        # ----------------------------------------------------

        questao = {
            "numero": numero,
            "texto": conteudo,
            "alternativas": alternativas,
            "_texto_apoio": texto_apoio,
        }

        questoes.append(
            questao
        )

    # ========================================================
    # TRANSFERIR TEXTOS DE APOIO
    # ========================================================

    for indice, questao in enumerate(
        questoes
    ):

        # Pega o texto temporário.
        texto_apoio = questao.pop(
            "_texto_apoio",
            ""
        )

        # Se não existe texto de apoio,
        # não há nada para fazer.
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

            # Coloca o texto de apoio no início
            # da próxima questão.
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
# 9. COMPATIBILIDADE COM O ENEM
# ============================================================

def separar_questoes_enem(texto):
    """
    Mantém compatibilidade com o código antigo.

    O ENEM passa a utilizar o parser genérico.
    """

    return separar_questoes_generico(
        texto
    )


# ============================================================
# 10. EXTRAIR GABARITO GENERICAMENTE
# ============================================================

def extrair_gabarito_generico(texto):
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
    for linha in linhas:

        linha_limpa = linha.strip()

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

            gabarito[
                numero
            ] = letra

    return gabarito


# ============================================================
# 11. COMPATIBILIDADE COM O GABARITO DO ENEM
# ============================================================

def extrair_gabarito_enem(texto):
    """
    Mantém compatibilidade com o código anterior.

    Agora utiliza o extrator genérico.
    """

    return extrair_gabarito_generico(
        texto
    )


# ============================================================
# 12. VALIDAR QUESTÕES E GABARITO
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

        if numero not in gabarito:

            erros.append(
                (
                    f"Questão {numero}: "
                    "gabarito não encontrado."
                )
            )

    return erros


# ============================================================
# 13. PREPARAR QUESTÕES
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

            # Verifica se é a resposta correta.
            correta = (
                gabarito.get(
                    numero
                ) == letra
            )

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
            }
        )

    return resultado


# ============================================================
# 14. IMPORTAR QUESTÕES NO BANCO
# ============================================================

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
        Questao,
        Alternativa,
    )

    if gabarito is None:
        gabarito = {}

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

        # ----------------------------------------------------
        # Cria os dados básicos da questão.
        # ----------------------------------------------------

        dados_questao = {
            "prova": prova,
            "numero": numero,
            "enunciado": enunciado,
        }

        # ----------------------------------------------------
        # Verifica se o modelo possui o campo disciplina.
        # ----------------------------------------------------

        campos_questao = {
            campo.name
            for campo in Questao._meta.fields
        }

        if (
            "disciplina"
            in campos_questao
        ):

            # Não força uma disciplina específica.
            #
            # A prova pode ser EXATO, ENEM,
            # vestibular, concurso etc.

            dados_questao[
                "disciplina"
            ] = ""

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

            correta = (
                gabarito.get(
                    numero
                ) == letra
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
# COMPATIBILIDADE COM O VIEWS.PY
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