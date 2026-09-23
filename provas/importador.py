# Importa expressões regulares para localizar questões e alternativas.
import re

# Importa o leitor de arquivos PDF.
from pypdf import PdfReader


def extrair_texto_pdf(caminho_pdf):
    """
    Lê todas as páginas de um PDF e retorna o texto extraído.
    """

    # Abre o arquivo PDF.
    leitor = PdfReader(caminho_pdf)

    # Guarda o texto de cada página.
    textos = []

    # Percorre todas as páginas.
    for pagina in leitor.pages:

        # Extrai o texto da página.
        texto = pagina.extract_text()

        # Guarda somente páginas que possuem texto.
        if texto:
            textos.append(texto)

    # Junta todas as páginas.
    texto_completo = '\n'.join(textos)

    # Faz uma limpeza básica.
    return limpar_texto(texto_completo)


def limpar_texto(texto):
    """
    Faz uma limpeza básica no texto extraído.
    """

    # Padroniza as quebras de linha.
    texto = texto.replace('\r\n', '\n')
    texto = texto.replace('\r', '\n')

    # Remove espaços e tabulações repetidos.
    texto = re.sub(r'[ \t]+', ' ', texto)

    # Remove excesso de linhas vazias.
    texto = re.sub(r'\n{3,}', '\n\n', texto)

    # Remove espaços no início e no final.
    return texto.strip()


def encontrar_marcadores_questoes(texto):
    """
    Localiza todas as ocorrências de QUESTÃO 01, QUESTÃO 02 etc.
    """

    # Procura a palavra QUESTÃO seguida de um número.
    padrao = re.compile(
        r'QUESTÃO\s+(\d{1,3})',
        re.IGNORECASE
    )

    # Retorna todos os marcadores encontrados.
    return list(padrao.finditer(texto))


def separar_questoes_enem(texto):
    """
    Separa as 90 questões principais do ENEM.

    O PDF possui:
    - Questões 01 a 45 na prova principal.
    - Questões 01 a 05 novamente na opção espanhol.
    - Questões 06 a 90 na sequência principal.

    As questões em espanhol são ignoradas.
    """

    # Localiza todos os marcadores de questões.
    marcadores = encontrar_marcadores_questoes(texto)

    # Lista que receberá os marcadores da prova principal.
    marcadores_principais = []

    # Guarda a primeira ocorrência de cada número.
    primeiras_ocorrencias = {}

    # Percorre todos os marcadores encontrados.
    for marcador in marcadores:

        # Converte o número da questão para inteiro.
        numero = int(marcador.group(1))

        # Guarda somente a primeira ocorrência.
        if numero not in primeiras_ocorrencias:
            primeiras_ocorrencias[numero] = marcador

    # Adiciona as questões 01 até 05 da prova principal.
    for numero in range(1, 6):

        # Verifica se a questão foi encontrada.
        if numero in primeiras_ocorrencias:
            marcadores_principais.append(
                primeiras_ocorrencias[numero]
            )

    # Adiciona as questões 06 até 90.
    for numero in range(6, 91):

        # Procura a primeira ocorrência do número.
        if numero in primeiras_ocorrencias:

            # Adiciona o marcador encontrado.
            marcadores_principais.append(
                primeiras_ocorrencias[numero]
            )

    # Localiza a segunda ocorrência da questão 01.
    # Ela marca o início da versão em espanhol.
    ocorrencias_01 = [
        marcador
        for marcador in marcadores
        if int(marcador.group(1)) == 1
    ]

    # Guarda o início do bloco em espanhol.
    marcador_inicio_espanhol = None

    # Verifica se existe uma segunda questão 01.
    if len(ocorrencias_01) >= 2:
        marcador_inicio_espanhol = ocorrencias_01[1]

    # Ordena os marcadores pela posição no PDF.
    marcadores_principais.sort(
        key=lambda marcador: marcador.start()
    )

    # Lista final das questões.
    questoes = []

    # Percorre cada marcador principal.
    for indice, marcador in enumerate(
        marcadores_principais
    ):

        # Obtém o número da questão.
        numero = int(marcador.group(1))

        # Define o início do conteúdo.
        inicio = marcador.end()

        # Define o final do conteúdo.
        if (
            numero == 5
            and marcador_inicio_espanhol is not None
        ):

            # A questão 5 termina antes do bloco espanhol.
            fim = marcador_inicio_espanhol.start()

        elif indice + 1 < len(marcadores_principais):

            # As outras questões terminam na próxima questão.
            fim = marcadores_principais[
                indice + 1
            ].start()

        else:

            # A questão 90 termina no final do PDF.
            fim = len(texto)

        # Extrai o conteúdo da questão.
        conteudo = texto[inicio:fim].strip()

        # Remove o texto de separação do espanhol,
        # caso ele ainda esteja presente.
        conteudo = re.sub(
            r'Questões de 01 a 05 \(opção espanhol\)\s*$',
            '',
            conteudo,
            flags=re.IGNORECASE
        ).strip()

        # Extrai as alternativas A, B, C, D e E.
        alternativas = extrair_alternativas(
            conteudo
        )

        # Adiciona a questão à lista.
        questoes.append(
            {
                'numero': numero,
                'conteudo': conteudo,
                'alternativas': alternativas,
            }
        )

    # Garante a ordem numérica das questões.
    questoes.sort(
        key=lambda questao: questao['numero']
    )

    # Retorna as questões processadas.
    return questoes
def extrair_alternativas(conteudo):
    """
    Separa as alternativas A, B, C, D e E.

    Também remove rodapés e informações repetidas
    inseridas pelo PDF entre as questões.
    """

    # Remove o rodapé do ENEM quando ele aparece
    # depois do conteúdo da alternativa.
    conteudo = re.sub(
        r'\*010175AZ2\*.*',
        '',
        conteudo,
        flags=re.DOTALL
    )

    # Remove linhas de identificação do caderno.
    conteudo = re.sub(
        r'(?mi)^.*LINGUAGENS,\s*CÓDIGOS\s*E\s*SUAS\s*TECNOLOGIAS.*$',
        '',
        conteudo
    )

    # Remove repetições do nome ENEM2024.
    conteudo = re.sub(
        r'ENEM2024',
        '',
        conteudo,
        flags=re.IGNORECASE
    )

    # Remove identificadores técnicos do arquivo.
    conteudo = re.sub(
        r'\b\d{8}[A-Z]{2}\.indb\b',
        '',
        conteudo,
        flags=re.IGNORECASE
    )

    # Limpa espaços e linhas vazias.
    conteudo = re.sub(
        r'\n\s*\n+',
        '\n',
        conteudo
    ).strip()

    # Procura as letras das alternativas.
    padrao = re.compile(
        r'(?m)^[ \t]*([ABCDE])'
        r'(?:[ \t]*[\.\)])?'
        r'(?=[ \t]+|\n|$)'
    )

    marcadores = list(
        padrao.finditer(conteudo)
    )

    sequencias_validas = []

    for indice, marcador in enumerate(marcadores):

        if marcador.group(1) != 'A':
            continue

        sequencia = [marcador]
        proxima_letra = 'B'

        for outro in marcadores[indice + 1:]:

            letra = outro.group(1)

            if letra == proxima_letra:

                sequencia.append(outro)

                if proxima_letra == 'B':
                    proxima_letra = 'C'

                elif proxima_letra == 'C':
                    proxima_letra = 'D'

                elif proxima_letra == 'D':
                    proxima_letra = 'E'

                elif proxima_letra == 'E':
                    break

        if len(sequencia) == 5:
            sequencias_validas.append(sequencia)

    # Nenhuma sequência válida encontrada.
    if not sequencias_validas:
        return []

    # Usa a última sequência A-B-C-D-E encontrada.
    sequencia = sequencias_validas[-1]

    alternativas = []

    for indice, marcador in enumerate(sequencia):

        letra = marcador.group(1)

        inicio = marcador.end()

        if indice + 1 < len(sequencia):

            fim = sequencia[
                indice + 1
            ].start()

        else:

            fim = len(conteudo)

        texto_alternativa = conteudo[
            inicio:fim
        ]

        texto_alternativa = texto_alternativa.replace(
            '\n',
            ' '
        )

        texto_alternativa = re.sub(
            r'\s+',
            ' ',
            texto_alternativa
        ).strip()

        alternativas.append(
            {
                'letra': letra,
                'texto': texto_alternativa,
            }
        )

    return alternativas


def extrair_gabarito_enem(texto):
    """
    Extrai o gabarito do ENEM.

    O PDF possui dois blocos:

    1. Questões 46 a 90:
       número + resposta

       Exemplo:
       46 C
       47 E

    2. Questões 1 a 45:
       número + resposta em Inglês + resposta em Espanhol

       Exemplo:
       1 C C
       2 A D

    Como a prova importada é a versão em Inglês,
    usamos a primeira resposta das questões 1 a 5.
    """

    # Limpa o texto extraído do PDF.
    texto = limpar_texto(texto)

    # Cria o dicionário que armazenará:
    # número da questão -> resposta correta.
    gabarito = {}

    # ---------------------------------------------------------
    # QUESTÕES 46 A 90
    # ---------------------------------------------------------

    # Procura linhas no formato:
    #
    # 46 C
    # 47 E
    # ...
    # 90 C
    #
    # O intervalo é limitado entre 46 e 90.
    padrao_46_90 = re.compile(
        r'(?m)^\s*(4[6-9]|[5-8]\d|90)\s+([ABCDE])\s*$'
    )

    # Percorre todas as respostas encontradas.
    for correspondencia in padrao_46_90.finditer(texto):

        # Obtém o número da questão.
        numero = int(
            correspondencia.group(1)
        )

        # Obtém a alternativa correta.
        resposta = correspondencia.group(2)

        # Salva no dicionário.
        gabarito[numero] = resposta

    # ---------------------------------------------------------
    # QUESTÕES 1 A 45
    # ---------------------------------------------------------

    # Localiza o bloco que contém:
    #
    # INGLÊS ESPANHOL
    #
    # Esse bloco aparece antes das questões 1 a 45.
    padrao_inicio = re.search(
        r'INGLÊS\s+ESPANHOL',
        texto,
        re.IGNORECASE
    )

    # Verifica se o bloco foi encontrado.
    if not padrao_inicio:
        raise ValueError(
            'Não foi possível localizar o bloco de Inglês/Espanhol.'
        )

    # Pega somente o texto depois de:
    # INGLÊS ESPANHOL
    texto_linguagens = texto[
        padrao_inicio.end():
    ]

    # ---------------------------------------------------------
    # QUESTÕES 1 A 5
    # ---------------------------------------------------------

    # As primeiras cinco questões possuem:
    #
    # 1 C C
    # 2 A D
    # 3 A D
    # 4 A D
    # 5 E A
    #
    # A primeira letra é Inglês.
    # A segunda letra é Espanhol.
    padrao_1_5 = re.compile(
        r'(?m)^\s*([1-5])\s+([ABCDE])\s+([ABCDE])\s*$'
    )

    # Procura as questões 1 a 5.
    for correspondencia in padrao_1_5.finditer(
        texto_linguagens
    ):

        # Número da questão.
        numero = int(
            correspondencia.group(1)
        )

        # Resposta da versão em Inglês.
        resposta_ingles = correspondencia.group(2)

        # Guarda a resposta em Inglês.
        gabarito[numero] = resposta_ingles

    # ---------------------------------------------------------
    # QUESTÕES 6 A 45
    # ---------------------------------------------------------

    # Procura linhas no formato:
    #
    # 6 E
    # 7 C
    # ...
    # 45 B
    #
    # O intervalo vai de 6 até 45.
    padrao_6_45 = re.compile(
        r'(?m)^\s*(?:[6-9]|[1-3]\d|4[0-5])\s+([ABCDE])\s*$'
    )

    # Percorre as questões encontradas.
    for correspondencia in padrao_6_45.finditer(
        texto_linguagens
    ):

        # Recupera a linha completa.
        linha = correspondencia.group(0).strip()

        # Separa os valores da linha.
        partes = linha.split()

        # Garante que existem número e resposta.
        if len(partes) != 2:
            continue

        # Obtém o número.
        numero = int(partes[0])

        # Obtém a resposta.
        resposta = partes[1]

        # Garante que estamos realmente entre 6 e 45.
        if 6 <= numero <= 45:

            # Salva no dicionário.
            gabarito[numero] = resposta

    # ---------------------------------------------------------
    # VALIDAÇÃO
    # ---------------------------------------------------------

    # Cria uma lista com as questões que estão faltando.
    faltantes = [
        numero
        for numero in range(1, 91)
        if numero not in gabarito
    ]

    # Se existir alguma questão faltando,
    # interrompe o processamento.
    if faltantes:

        raise ValueError(
            f'Gabarito incompleto. '
            f'Foram encontradas {len(gabarito)} respostas. '
            f'Faltantes: {faltantes}'
        )

    # Retorna o gabarito completo.
    return gabarito

def validar_questoes_com_gabarito(questoes, gabarito):
    """
    Confere se as questões extraídas do PDF
    possuem alternativas e respostas válidas.

    Nenhuma informação é salva no banco nesta etapa.
    """

    # Cria uma lista para armazenar problemas encontrados.
    problemas = []

    # Verifica a quantidade de questões.
    if len(questoes) != 90:
        problemas.append(
            f'Foram encontradas {len(questoes)} questões. '
            f'O esperado para esta prova é 90.'
        )

    # Percorre todas as questões extraídas.
    for questao in questoes:

        # Obtém o número da questão.
        numero = questao['numero']

        # Obtém as alternativas.
        alternativas = questao['alternativas']

        # Cria uma lista somente com as letras.
        letras = [
            alternativa['letra']
            for alternativa in alternativas
        ]

        # Verifica se existem exatamente 5 alternativas.
        if len(alternativas) != 5:

            problemas.append(
                f'Questão {numero}: '
                f'encontradas {len(alternativas)} alternativas.'
            )

        # Verifica se as letras são A, B, C, D e E.
        if letras != ['A', 'B', 'C', 'D', 'E']:

            problemas.append(
                f'Questão {numero}: '
                f'alternativas encontradas: {letras}.'
            )

        # Verifica se existe gabarito para a questão.
        if numero not in gabarito:

            problemas.append(
                f'Questão {numero}: '
                f'gabarito não encontrado.'
            )

        # Se existe gabarito, verifica a letra.
        elif gabarito[numero] not in letras:

            problemas.append(
                f'Questão {numero}: '
                f'gabarito {gabarito[numero]} '
                f'não corresponde às alternativas.'
            )

    # Verifica se alguma questão possui conteúdo vazio.
    for questao in questoes:

        # Número da questão.
        numero = questao['numero']

        # Conteúdo extraído.
        conteudo = questao['conteudo'].strip()

        # Verifica se o conteúdo está vazio.
        if not conteudo:

            problemas.append(
                f'Questão {numero}: '
                f'conteúdo vazio.'
            )

    # Retorna todos os problemas encontrados.
    return problemas

def preparar_questoes_para_importacao(questoes, gabarito):
    """
    Prepara as questões extraídas para futura gravação no banco.

    Nesta etapa nenhum dado é salvo.
    A função apenas separa o enunciado,
    as alternativas e a resposta correta.
    """

    # Lista que armazenará as questões preparadas.
    resultado = []

    # Percorre todas as questões extraídas.
    for questao in questoes:

        # Obtém o número da questão.
        numero = questao['numero']

        # Obtém as alternativas encontradas.
        alternativas = questao['alternativas']

        # Verifica se existem alternativas.
        if not alternativas:
            continue

        # O enunciado começa no início do conteúdo.
        conteudo = questao['conteudo']

        # A primeira alternativa marca o início
        # da parte que não pertence ao enunciado.
        primeira_alternativa = alternativas[0]

        # Procura a posição do marcador da primeira alternativa.
        marcador = re.search(
            r'(?m)^[ \t]*A(?:[ \t]*[\.\)])?(?=[ \t]+|\n|$)',
            conteudo
        )

        # Se encontrou o marcador A,
        # separa tudo antes dele como enunciado.
        if marcador:

            # Extrai somente o enunciado.
            enunciado = conteudo[
                :marcador.start()
            ].strip()

        else:

            # Caso excepcional:
            # usa o conteúdo completo.
            enunciado = conteudo.strip()

        # Cria a estrutura da questão.
        questao_preparada = {
            'numero': numero,
            'enunciado': enunciado,
            'alternativas': alternativas,
            'correta': gabarito[numero],
        }

        # Adiciona à lista final.
        resultado.append(
            questao_preparada
        )

    # Ordena as questões pelo número.
    resultado.sort(
        key=lambda questao: questao['numero']
    )

    # Retorna os dados preparados.
    return resultado

from django.db import transaction

from .models import Alternativa, Disciplina, Questao


def importar_questoes_no_banco(prova, questoes_preparadas):
    """
    Salva as questões preparadas no banco de dados.

    A operação é feita dentro de uma transação:
    se qualquer questão apresentar erro,
    nenhuma alteração parcial será mantida.
    """

    # Inicia uma transação segura.
    with transaction.atomic():

        # Remove questões que já pertencem a esta prova.
        #
        # Isso evita duplicação caso a mesma prova
        # seja processada novamente.
        Questao.objects.filter(
            prova=prova
        ).delete()

        # Cria ou recupera a disciplina de Linguagens.
        disciplina_linguagens, _ = Disciplina.objects.get_or_create(
            nome='Linguagens, Códigos e suas Tecnologias'
        )

        # Cria ou recupera a disciplina de Ciências Humanas.
        disciplina_humanas, _ = Disciplina.objects.get_or_create(
            nome='Ciências Humanas e suas Tecnologias'
        )

        # Percorre todas as questões preparadas.
        for dados in questoes_preparadas:

            # Obtém o número da questão.
            numero = dados['numero']

            # Questões 1 a 45 pertencem a Linguagens.
            if numero <= 45:

                disciplina = disciplina_linguagens

            # Questões 46 a 90 pertencem a Ciências Humanas.
            else:

                disciplina = disciplina_humanas

            # Cria a questão no banco.
            questao = Questao.objects.create(
                prova=prova,
                disciplina=disciplina,
                numero=numero,
                enunciado=dados['enunciado'],
                ativa=True
            )

            # Percorre as cinco alternativas.
            for alternativa in dados['alternativas']:

                # Obtém a letra da alternativa.
                letra = alternativa['letra']

                # Verifica se esta é a resposta correta.
                correta = (
                    letra == dados['correta']
                )

                # Cria a alternativa no banco.
                Alternativa.objects.create(
                    questao=questao,
                    letra=letra,
                    texto=alternativa['texto'],
                    correta=correta
                )

        # Atualiza o status da prova.
        prova.status_importacao = 'processada'

        # Limpa uma mensagem de erro anterior.
        prova.mensagem_importacao = ''

        # Registra a data do processamento.
        from django.utils import timezone

        prova.data_processamento = timezone.now()

        # Salva as alterações da prova.
        prova.save(
            update_fields=[
                'status_importacao',
                'mensagem_importacao',
                'data_processamento'
            ]
        )

    # Retorna a quantidade importada.
    return len(questoes_preparadas)