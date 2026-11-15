"""
Catálogo declarativo das provas oficiais do ENEM.

Os dados foram levantados nas páginas oficiais do INEP:

    https://www.gov.br/inep/pt-br/areas-de-atuacao/
    avaliacao-e-exames-educacionais/enem/provas-e-gabaritos/{ano}

O módulo é a fonte única da verdade para o comando de importação em
lote. Nenhum PDF é armazenado no repositório: apenas os links oficiais
são registrados.
"""

from dataclasses import dataclass, field


# Endereço base dos arquivos oficiais.
BASE_ARQUIVOS = (
    'https://download.inep.gov.br/enem/provas_e_gabaritos/'
)

# Endereço da página oficial de cada ano.
BASE_PAGINA = (
    'https://www.gov.br/inep/pt-br/areas-de-atuacao/'
    'avaliacao-e-exames-educacionais/enem/provas-e-gabaritos/'
)

# Anos com aplicação regular disponível.
ANOS_REGULARES = (2020, 2021, 2022, 2023, 2024, 2025)

# Anos com arquivos oficiais da aplicação digital.
# O INEP não publicou cadernos digitais de 2023 em diante.
ANOS_DIGITAIS = (2020, 2021, 2022)

# Cadernos padrão de cada dia.
CADERNOS_DIA_1 = (1, 2, 3, 4)
CADERNOS_DIA_2 = (5, 6, 7, 8)

# Cadernos de acessibilidade de cada dia.
CADERNOS_ACESSIBILIDADE_DIA_1 = (9, 10)
CADERNOS_ACESSIBILIDADE_DIA_2 = (11, 12)

# Cor oficial de cada caderno por ano.
CORES = {
    2020: {
        1: 'Azul',
        2: 'Amarelo',
        3: 'Branco',
        4: 'Rosa',
        5: 'Amarelo',
        6: 'Cinza',
        7: 'Azul',
        8: 'Rosa',
        9: 'Laranja',
        10: 'Verde',
        11: 'Laranja',
        12: 'Verde',
    },
    2021: {
        1: 'Azul',
        2: 'Amarelo',
        3: 'Branco',
        4: 'Rosa',
        5: 'Amarelo',
        6: 'Cinza',
        7: 'Azul',
        8: 'Rosa',
        9: 'Laranja',
        10: 'Verde',
        11: 'Laranja',
        12: 'Verde',
    },
    2022: {
        1: 'Azul',
        2: 'Amarelo',
        3: 'Branco',
        4: 'Rosa',
        5: 'Amarelo',
        6: 'Cinza',
        7: 'Azul',
        8: 'Rosa',
        9: 'Laranja',
        10: 'Verde',
        11: 'Laranja',
        12: 'Verde',
    },
    2023: {
        1: 'Azul',
        2: 'Amarelo',
        3: 'Branco',
        4: 'Rosa',
        5: 'Amarelo',
        6: 'Cinza',
        7: 'Azul',
        8: 'Rosa',
        9: 'Laranja',
        10: 'Verde',
        11: 'Laranja',
        12: 'Verde',
    },
    2024: {
        1: 'Azul',
        2: 'Amarelo',
        3: 'Branco',
        4: 'Verde',
        5: 'Amarelo',
        6: 'Cinza',
        7: 'Azul',
        8: 'Verde',
        9: 'Laranja',
        10: 'Roxo',
        11: 'Laranja',
        12: 'Roxo',
    },
    2025: {
        1: 'Azul',
        2: 'Amarelo',
        3: 'Branco',
        4: 'Verde',
        5: 'Amarelo',
        6: 'Cinza',
        7: 'Azul',
        8: 'Verde',
        9: 'Laranja',
        10: 'Roxo',
        11: 'Laranja',
        12: 'Roxo',
    },
}

# Formato de acessibilidade de cada caderno especial.
ACESSIBILIDADES = {
    9: 'braile_ledor',
    10: 'libras',
    11: 'braile_ledor',
    12: 'libras',
}

# Rótulos usados nas descrições dos cadernos de acessibilidade.
ACESSIBILIDADES_DESCRICAO = {
    'braile_ledor': 'Braille/Ledor',
    'libras': 'Libras',
}

# Áreas avaliadas em cada dia.
AREAS = {
    1: (
        'Linguagens, Códigos e suas Tecnologias e '
        'Ciências Humanas e suas Tecnologias'
    ),
    2: (
        'Ciências da Natureza e suas Tecnologias e '
        'Matemática e suas Tecnologias'
    ),
}


@dataclass(frozen=True)
class ProvaCatalogo:
    """Representa uma prova oficial do catálogo."""

    chave: str
    ano: int
    modalidade: str
    dia: int
    caderno: int
    cor: str
    nome: str
    descricao: str
    url_prova: str
    url_gabarito: str
    acessibilidade: str = 'padrao'
    idioma: str = ''
    url_prova_espanhol: str = ''
    url_gabarito_espanhol: str = ''
    quantidade_questoes: int | None = None
    importar_questoes: bool = True
    fonte_url: str = field(default='')

    @property
    def area(self):
        return AREAS[self.dia]

    @property
    def dia_display(self):
        return f'{self.dia}º dia'

    @property
    def modalidade_display(self):
        return 'Regular' if self.modalidade == 'regular' else 'Digital'

    @property
    def e_digital_dia_1(self):
        return self.modalidade == 'digital' and self.dia == 1

    @property
    def arquivos(self):
        """
        Devolve os pares (prova, gabarito) que devem ser baixados.

        Cadernos digitais do primeiro dia têm um par por idioma.
        """
        if self.e_digital_dia_1:
            return [
                {
                    'idioma': 'Inglês',
                    'url_prova': self.url_prova,
                    'url_gabarito': self.url_gabarito,
                },
                {
                    'idioma': 'Espanhol',
                    'url_prova': self.url_prova_espanhol,
                    'url_gabarito': self.url_gabarito_espanhol,
                },
            ]

        return [
            {
                'idioma': '',
                'url_prova': self.url_prova,
                'url_gabarito': self.url_gabarito,
            }
        ]


def _pagina_do_ano(ano):
    return f'{BASE_PAGINA}{ano}'


def _url_impresso(ano, dia, caderno, tipo):
    return (
        f'{BASE_ARQUIVOS}{ano}_{tipo}_impresso_D{dia}_'
        f'CD{caderno}.pdf'
    )


def _url_digital(ano, dia, caderno, tipo, idioma=None):
    sufixo = f'_{idioma}' if idioma else ''
    return (
        f'{BASE_ARQUIVOS}{ano}_{tipo}_digital_D{dia}_'
        f'CD{caderno}{sufixo}.pdf'
    )


def _nome_regular(ano, dia, caderno, cor, acessibilidade):
    partes = [
        f'ENEM {ano}',
        'Regular',
        f'{dia}º dia',
        f'Caderno {caderno} ({cor}',
    ]

    if acessibilidade != 'padrao':
        partes[-1] += f', {ACESSIBILIDADES_DESCRICAO[acessibilidade]}'

    partes[-1] += ')'

    return ' - '.join(partes)


def _nome_digital(ano, dia, caderno, cor, idioma):
    partes = [
        f'ENEM {ano}',
        'Digital',
        f'{dia}º dia',
        f'Caderno {caderno} ({cor})',
    ]

    if idioma:
        partes.append(idioma)

    return ' - '.join(partes)


def _descricao_regular(ano, dia, caderno, cor, acessibilidade):
    if acessibilidade != 'padrao':
        formato = ACESSIBILIDADES_DESCRICAO[acessibilidade]
        return (
            f'Versão de acessibilidade ({formato}) do caderno '
            f'{caderno} ({cor}) do ENEM {ano}, aplicação regular, '
            f'{dia}º dia. Área: {AREAS[dia]}. O conteúdo é equivalente '
            'ao caderno regular e fica disponível para consulta, sem '
            'importação de questões.'
        )

    return (
        f'Prova oficial do ENEM {ano}, aplicação regular, {dia}º dia, '
        f'caderno {caderno} ({cor}). Área: {AREAS[dia]}. '
        'Gabarito oficial vinculado ao mesmo caderno.'
    )


def _descricao_digital(ano, dia, caderno, cor, idioma):
    if dia == 1:
        return (
            f'Prova oficial do ENEM {ano}, aplicação digital, 1º dia, '
            f'caderno {caderno} ({cor}), com variantes em Inglês e '
            f'Espanhol. Área: {AREAS[1]}. O aluno escolhe o idioma e '
            'o sistema apresenta as questões correspondentes, com o '
            'gabarito do mesmo idioma.'
        )

    return (
        f'Prova oficial do ENEM {ano}, aplicação digital, 2º dia, '
        f'caderno {caderno} ({cor}). Área: {AREAS[2]}. '
        'Gabarito oficial vinculado ao mesmo caderno.'
    )


def _montar_regular(ano):
    provas = []

    for dia, cadernos in (
        (1, CADERNOS_DIA_1 + CADERNOS_ACESSIBILIDADE_DIA_1),
        (2, CADERNOS_DIA_2 + CADERNOS_ACESSIBILIDADE_DIA_2),
    ):
        for caderno in cadernos:
            cor = CORES[ano][caderno]
            acessibilidade = ACESSIBILIDADES.get(caderno, 'padrao')
            importar = acessibilidade == 'padrao'

            provas.append(
                ProvaCatalogo(
                    chave=f'enem-{ano}-regular-d{dia}-cd{caderno}',
                    ano=ano,
                    modalidade='regular',
                    dia=dia,
                    caderno=caderno,
                    cor=cor,
                    nome=_nome_regular(
                        ano,
                        dia,
                        caderno,
                        cor,
                        acessibilidade,
                    ),
                    descricao=_descricao_regular(
                        ano,
                        dia,
                        caderno,
                        cor,
                        acessibilidade,
                    ),
                    url_prova=_url_impresso(
                        ano,
                        dia,
                        caderno,
                        'PV',
                    ),
                    url_gabarito=_url_impresso(
                        ano,
                        dia,
                        caderno,
                        'GB',
                    ),
                    acessibilidade=acessibilidade,
                    quantidade_questoes=90 if importar else None,
                    importar_questoes=importar,
                    fonte_url=_pagina_do_ano(ano),
                )
            )

    return provas


def _montar_digital(ano):
    provas = []

    for caderno in CADERNOS_DIA_1:
        cor = CORES[ano][caderno]

        provas.append(
            ProvaCatalogo(
                chave=f'enem-{ano}-digital-d1-cd{caderno}',
                ano=ano,
                modalidade='digital',
                dia=1,
                caderno=caderno,
                cor=cor,
                nome=_nome_digital(
                    ano,
                    1,
                    caderno,
                    cor,
                    'Inglês e Espanhol',
                ),
                descricao=_descricao_digital(
                    ano,
                    1,
                    caderno,
                    cor,
                    'Inglês e Espanhol',
                ),
                url_prova=_url_digital(
                    ano,
                    1,
                    caderno,
                    'PV',
                    'ingles',
                ),
                url_gabarito=_url_digital(
                    ano,
                    1,
                    caderno,
                    'GB',
                    'ingles',
                ),
                idioma='Inglês e Espanhol',
                url_prova_espanhol=_url_digital(
                    ano,
                    1,
                    caderno,
                    'PV',
                    'espanhol',
                ),
                url_gabarito_espanhol=_url_digital(
                    ano,
                    1,
                    caderno,
                    'GB',
                    'espanhol',
                ),
                quantidade_questoes=90,
                fonte_url=_pagina_do_ano(ano),
            )
        )

    for caderno in CADERNOS_DIA_2:
        cor = CORES[ano][caderno]

        provas.append(
            ProvaCatalogo(
                chave=f'enem-{ano}-digital-d2-cd{caderno}',
                ano=ano,
                modalidade='digital',
                dia=2,
                caderno=caderno,
                cor=cor,
                nome=_nome_digital(
                    ano,
                    2,
                    caderno,
                    cor,
                    '',
                ),
                descricao=_descricao_digital(
                    ano,
                    2,
                    caderno,
                    cor,
                    '',
                ),
                url_prova=_url_digital(
                    ano,
                    2,
                    caderno,
                    'PV',
                ),
                url_gabarito=_url_digital(
                    ano,
                    2,
                    caderno,
                    'GB',
                ),
                quantidade_questoes=90,
                fonte_url=_pagina_do_ano(ano),
            )
        )

    return provas


def construir_catalogo():
    """Monta a lista completa de provas oficiais."""
    provas = []

    for ano in ANOS_REGULARES:
        provas.extend(_montar_regular(ano))

    for ano in ANOS_DIGITAIS:
        provas.extend(_montar_digital(ano))

    return tuple(provas)


# Catálogo carregado uma única vez por processo.
CATALOGO = construir_catalogo()


def obter(chave):
    """Busca uma prova pela chave oficial."""
    for prova in CATALOGO:
        if prova.chave == chave:
            return prova

    return None


def filtrar(
    ano=None,
    modalidade=None,
    dia=None,
    caderno=None,
    acessibilidade=None,
    apenas_importaveis=False,
):
    """
    Filtra o catálogo pelos critérios informados.

    ``ano`` e ``dia`` podem ser inteiros ou listas de inteiros.
    """

    def _normalizar(valor):
        if valor is None:
            return None

        if isinstance(valor, (list, tuple, set)):
            return {int(item) for item in valor}

        return {int(valor)}

    anos = _normalizar(ano)
    dias = _normalizar(dia)

    resultado = []

    for prova in CATALOGO:
        if anos is not None and prova.ano not in anos:
            continue

        if modalidade and prova.modalidade != modalidade:
            continue

        if dias is not None and prova.dia not in dias:
            continue

        if caderno is not None and prova.caderno != int(caderno):
            continue

        if acessibilidade and prova.acessibilidade != acessibilidade:
            continue

        if apenas_importaveis and not prova.importar_questoes:
            continue

        resultado.append(prova)

    return resultado


def resumo():
    """Devolve os totais do catálogo por modalidade e dia."""
    totais = {
        'total': len(CATALOGO),
        'importaveis': 0,
        'acessibilidade': 0,
        'regular': {},
        'digital': {},
    }

    for prova in CATALOGO:
        if prova.importar_questoes:
            totais['importaveis'] += 1
        else:
            totais['acessibilidade'] += 1

        chave_dia = f'd{prova.dia}'
        grupo = totais[prova.modalidade]
        grupo[chave_dia] = grupo.get(chave_dia, 0) + 1

    return totais
