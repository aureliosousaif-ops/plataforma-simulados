import hashlib
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image
from pypdf import PdfWriter

from usuarios.models import Perfil

from .imagens import (
    associar_imagem,
    confirmar_associacao,
    extrair_e_registrar_imagens,
    extrair_imagens_pdf,
    gerar_sugestoes_associacao,
    remover_associacao,
    sincronizar_imagem_principal,
    sugerir_questao_para_imagem,
)
from .importador import (
    _encontrar_marcadores_alternativas,
    detectar_idioma_secao,
    dividir_questoes_validas,
    extrair_gabarito_enem,
    extrair_alternativas_generico,
    extrair_texto_pdf,
    importar_questoes_no_banco,
    limpar_texto,
    limpar_texto_alternativa,
    preparar_questoes,
    separar_questoes_enem,
    validar_estrutura_questoes,
)
from .models import (
    Alternativa,
    Disciplina,
    ImagemProva,
    ImagemQuestao,
    Prova,
    Questao,
    QuestaoTextoBase,
    TextoBase,
    distribuir_textos_base,
)
from .paginas import (
    localizar_pagina_questao,
    obter_indice_paginas,
    renderizar_pagina,
    total_paginas,
)
from .templatetags.examix_texto import normalizar_enunciado


def criar_bloco_questao(numero, idioma=''):
    linhas = []

    if idioma:
        linhas.append(
            f'Questões de 01 a 05 (opção {idioma})'
        )

    linhas.extend([
        f'QUESTÃO {numero:02d}',
        f'Enunciado da questão {numero}.',
        'A',
        'Alternativa A.',
        'B',
        'Alternativa B.',
        'C',
        'Alternativa C.',
        'D',
        'Alternativa D.',
        'E',
        'Alternativa E.',
    ])

    return '\n'.join(linhas)


class ParserEnemTestCase(TestCase):
    def texto_com_duas_opcoes(self):
        blocos = [
            criar_bloco_questao(numero, 'inglês')
            for numero in range(1, 6)
        ]
        blocos.extend(
            criar_bloco_questao(numero, 'espanhol')
            for numero in range(1, 6)
        )
        blocos.extend(
            criar_bloco_questao(numero)
            for numero in range(6, 91)
        )
        return '\n'.join(blocos)

    def test_detecta_cabecalho_de_ingles(self):
        linhas = [
            'Questões de 01 a 05 (opção inglês)',
            'QUESTÃO 01',
        ]

        self.assertEqual(
            detectar_idioma_secao(linhas, 1),
            'Inglês'
        )

    def test_detecta_cabecalho_de_espanhol(self):
        linhas = [
            'Questões de 01 a 05 (opção espanhol)',
            'QUESTÃO 01',
        ]

        self.assertEqual(
            detectar_idioma_secao(linhas, 1),
            'Espanhol'
        )

    def test_nao_classifica_por_palavra_isolada(self):
        linhas = [
            'Este texto contém a palavra inglês.',
            'QUESTÃO 01',
        ]

        self.assertIsNone(
            detectar_idioma_secao(linhas, 1)
        )

    def test_remove_apenas_linhas_de_impressao(self):
        texto = '\n'.join([
            'ENEM2024',
            '010175AZ3',
            'El virus de la cancelación apareció en ENEM2024.',
            'O código 010175AZ3 aparece no enunciado legítimo.',
        ])

        limpo = limpar_texto(texto)

        self.assertNotIn('\nENEM2024\n', f'\n{limpo}\n')
        self.assertNotIn('\n010175AZ3\n', f'\n{limpo}\n')
        self.assertIn('El virus de la cancelación apareció en ENEM2024.', limpo)
        self.assertIn('O código 010175AZ3 aparece no enunciado legítimo.', limpo)

    def test_remove_codigo_no_final_sem_apagar_texto_da_alternativa(self):
        texto = 'Alternativa legítima em espanhol. *010175AZ3* ENEM2024'

        self.assertEqual(
            limpar_texto_alternativa(texto),
            'Alternativa legítima em espanhol.'
        )

    def test_alternativas_separam_questoes_consecutivas(self):
        texto = '\n'.join([
            'Enunciado em espanhol sobre cultura.',
            'A', 'dar una mano',
            'B', 'cancelar una cuenta',
            'C', 'ignorar el problema',
            'D', 'buscar ayuda',
            'E', 'cambiar de opinión',
        ])

        alternativas = extrair_alternativas_generico(texto)

        self.assertEqual(
            [alternativa['letra'] for alternativa in alternativas],
            ['A', 'B', 'C', 'D', 'E']
        )
        self.assertEqual(alternativas[0]['texto'], 'dar una mano')
        self.assertEqual(alternativas[4]['texto'], 'cambiar de opinión')

    def test_alternativas_extraidas_de_uma_linha(self):
        texto = (
            'Enunciado sobre El virus de la cancelación. '
            'A) dar una mano B) cancelar una cuenta '
            'C) ignorar el problema D) buscar ayuda E) cambiar de opinión'
        )

        alternativas = extrair_alternativas_generico(texto)

        self.assertEqual(
            [alternativa['letra'] for alternativa in alternativas],
            ['A', 'B', 'C', 'D', 'E']
        )
        self.assertEqual(alternativas[0]['texto'], 'dar una mano')
        self.assertEqual(alternativas[4]['texto'], 'cambiar de opinión')

    def test_marcadores_separados_com_espacos_e_pontuacao(self):
        texto = '\n'.join([
            'Enunciado da questão.',
            'A )', 'Primeira alternativa.',
            'B.', 'Segunda alternativa.',
            '(C)', 'Terceira alternativa.',
            'D -', 'Quarta alternativa.',
            'E:', 'Quinta alternativa.',
        ])

        alternativas = extrair_alternativas_generico(texto)

        self.assertEqual(
            [alternativa['letra'] for alternativa in alternativas],
            ['A', 'B', 'C', 'D', 'E']
        )
        self.assertEqual(
            alternativas[0]['texto'],
            'Primeira alternativa.'
        )

    def test_marcadores_sem_pontuacao_nao_confundem_inicio_de_frase(self):
        texto = '\n'.join([
            'A alternativa correta depende do texto.',
            'B exemplo aparece no enunciado.',
            'A', 'Primeira alternativa iniciada por A.',
            'B', 'Segunda alternativa.',
            'C', 'Terceira alternativa.',
            'D', 'Quarta alternativa.',
            'E', 'Quinta alternativa.',
        ])

        alternativas = extrair_alternativas_generico(texto)

        self.assertEqual(
            [alternativa['letra'] for alternativa in alternativas],
            ['A', 'B', 'C', 'D', 'E']
        )
        self.assertEqual(
            alternativas[0]['texto'],
            'Primeira alternativa iniciada por A.'
        )

    def test_reconhece_apenas_marcadores_validos(self):
        linhas = [
            'A',
            'A)',
            '(A)',
            'A.',
            'A:',
            'A alternativa correta depende do texto.',
            'B exemplo aparece no enunciado.',
        ]

        marcadores = _encontrar_marcadores_alternativas(linhas)

        self.assertEqual(
            [linha['letra'] for linha in marcadores],
            ['A', 'A', 'A', 'A', 'A']
        )

    def test_expansao_inline_preserva_pontuacao_das_alternativas(self):
        texto = (
            'Enunciado. '
            'A) primeira, com vírgula. '
            'B. segunda? '
            'C: terceira; '
            'D- quarta! '
            'E) quinta.'
        )

        alternativas = extrair_alternativas_generico(texto)

        self.assertEqual(alternativas[0]['texto'], 'primeira, com vírgula.')
        self.assertEqual(alternativas[1]['texto'], 'segunda?')
        self.assertEqual(alternativas[2]['texto'], 'terceira;')
        self.assertEqual(alternativas[3]['texto'], 'quarta!')
        self.assertEqual(alternativas[4]['texto'], 'quinta.')

    def test_marcador_junto_sem_pontuacao_no_formato_real(self):
        texto = '\n'.join([
            'Enunciado da questão 1.',
            'A', 'identificar ameaças.',
            'B identificar contextos que podem representar perigo.',
            'C', 'ignorar os sinais.',
            'D', 'avaliar o cenário.',
            'E', 'procurar ajuda.',
        ])

        alternativas = extrair_alternativas_generico(texto)

        self.assertEqual(
            [alternativa['letra'] for alternativa in alternativas],
            ['A', 'B', 'C', 'D', 'E']
        )
        self.assertEqual(
            alternativas[1]['texto'],
            'identificar contextos que podem representar perigo.'
        )

    def test_remove_cauda_repetida_do_rodape_na_alternativa_e(self):
        texto = '\n'.join([
            'Enunciado da questão 8.',
            'A', 'Primeira.',
            'B', 'Segunda.',
            'C', 'Terceira.',
            'D', 'Quarta.',
            'E', 'Quinta com acento e pontuação! ENEM2024ENEM2024',
            '010175AZ3 informação de impressão e paginação.',
        ])

        alternativas = extrair_alternativas_generico(texto)

        self.assertEqual(
            alternativas[4]['texto'],
            'Quinta com acento e pontuação!'
        )
        self.assertNotIn('ENEM2024', alternativas[4]['texto'])

    def test_questao_8_com_sequencia_restrita_abced(self):
        texto = '\n'.join([
            'Enunciado da questão 8.',
            'A', 'Alternativa A, com acento.',
            'B', 'Alternativa B.',
            'C', 'Alternativa C.',
            'D', 'Alternativa D.',
            'E', 'Alternativa E! ENEM2024ENEM2024',
        ])

        alternativas = extrair_alternativas_generico(texto)

        self.assertEqual(
            [alternativa['letra'] for alternativa in alternativas],
            ['A', 'B', 'C', 'D', 'E']
        )
        self.assertEqual(alternativas[0]['texto'], 'Alternativa A, com acento.')
        self.assertEqual(alternativas[4]['texto'], 'Alternativa E!')

    def test_prioriza_bloco_isolado_antes_de_bloco_inline_seguinte(self):
        texto = '\n'.join([
            'Enunciado da questão 1.',
            'A', 'Alternativa correta da questão 1.',
            'B', 'Outra alternativa da questão 1.',
            'C', 'Terceira alternativa da questão 1.',
            'D', 'Quarta alternativa da questão 1.',
            'E', 'Quinta alternativa da questão 1.',
            'A) alternativa da questão 2. B) segunda. C) terceira. '
            'D) quarta. E) quinta.',
        ])

        alternativas = extrair_alternativas_generico(texto)

        self.assertEqual(
            [alternativa['texto'] for alternativa in alternativas],
            [
                'Alternativa correta da questão 1.',
                'Outra alternativa da questão 1.',
                'Terceira alternativa da questão 1.',
                'Quarta alternativa da questão 1.',
                'Quinta alternativa da questão 1.',
            ],
        )

    def test_questao_1_real_nao_recebe_alternativas_da_questao_seguinte(self):
        texto = '\n'.join([
            'El vírus de la cancelación',
            '¿De qué se trata este fenómeno?',
            'Na argumentação apresentada sobre cultura do cancelamento, '
            'esse texto objetiva',
            'A',
            'apresentar o conceito desse tipo de prática.',
            'B',
            'mostrar a contrariedade das mídias com relação a essa atitude.',
            'C',
            'criticar o impacto dessa cultura sobre a vida representada nas redes.',
            'D',
            'evidenciar a democratização dessa prática na sociedade virtual.',
            'E',
            'discorrer historicamente sobre a origem e as causas dessa cultura.',
            '*010175AZ3*',
            'ENEM2024ENEM2024ENEM2024',
            'A) dar oportunidade a pessoas que parecem necessitadas. '
            'B) identificar contextos que podem representar perigo. '
            'C) tirar proveito de situações que podem ser adversas. '
            'D) evitar dificuldades que parecem ser intransponíveis. '
            'E) contestar circunstâncias que parecem ser harmônicas.',
        ])

        questoes = separar_questoes_enem(
            'QUESTÃO 01\n' + texto + '\nQUESTÃO 02\nPróximo enunciado'
        )
        questao = questoes[0]

        self.assertIn('El vírus de la cancelación', questao['texto'])
        self.assertEqual(
            [alternativa['texto'] for alternativa in questao['alternativas']],
            [
                'apresentar o conceito desse tipo de prática.',
                'mostrar a contrariedade das mídias com relação a essa atitude.',
                'criticar o impacto dessa cultura sobre a vida representada nas redes.',
                'evidenciar a democratização dessa prática na sociedade virtual.',
                'discorrer historicamente sobre a origem e as causas dessa cultura.',
            ],
        )

    def test_questao_1_real_ignora_bloco_linha_a_linha_apos_rodape(self):
        texto = '\n'.join([
            'El vírus de la cancelación',
            'Na argumentação apresentada sobre cultura do cancelamento, esse texto objetiva',
            'A', 'apresentar o conceito desse tipo de prática.',
            'B', 'mostrar a contrariedade das mídias com relação a essa atitude.',
            'C', 'criticar o impacto dessa cultura sobre a vida representada nas redes.',
            'D', 'evidenciar a democratização dessa prática na sociedade virtual.',
            'E', 'discorrer historicamente sobre a origem e as causas dessa cultura.',
            '*010175AZ3*',
            'ENEM2024ENEM2024ENEM2024',
            'A)', 'dar oportunidade a pessoas que parecem necessitadas.',
            'B)', 'identificar contextos que podem representar perigo.',
            'C)', 'tirar proveito de situações que podem ser adversas.',
            'D)', 'evitar dificuldades que parecem ser intransponíveis.',
            'E)', 'contestar circunstâncias que parecem ser harmônicas.',
        ])

        alternativas = extrair_alternativas_generico(texto)

        self.assertEqual(
            [alternativa['texto'] for alternativa in alternativas],
            [
                'apresentar o conceito desse tipo de prática.',
                'mostrar a contrariedade das mídias com relação a essa atitude.',
                'criticar o impacto dessa cultura sobre a vida representada nas redes.',
                'evidenciar a democratização dessa prática na sociedade virtual.',
                'discorrer historicamente sobre a origem e as causas dessa cultura.',
            ],
        )

    def test_questao_16_ignora_a_interno_antes_de_d(self):
        texto = '\n'.join([
            'A', 'Alternativa A.',
            'B', 'Alternativa B.',
            'C', 'Alternativa C. A superação depende do contexto.',
            'A superação não é um marcador isolado.',
            'D', 'Alternativa D.',
            'E', 'Alternativa E.',
        ])

        alternativas = extrair_alternativas_generico(texto)

        self.assertEqual(
            [alternativa['letra'] for alternativa in alternativas],
            ['A', 'B', 'C', 'D', 'E']
        )
        self.assertIn('A superação', alternativas[2]['texto'])

    def test_questao_66_ignora_a_interno_antes_de_c(self):
        texto = '\n'.join([
            'A', 'Alternativa A.',
            'B', 'Alternativa B.',
            'A ampliação aparece no texto da alternativa.',
            'C', 'Alternativa C.',
            'D', 'Alternativa D.',
            'E', 'Alternativa E.',
        ])

        alternativas = extrair_alternativas_generico(texto)

        self.assertEqual(
            [alternativa['letra'] for alternativa in alternativas],
            ['A', 'B', 'C', 'D', 'E']
        )
        self.assertIn('A ampliação', alternativas[1]['texto'])

    def test_separa_questoes_e_alternativas_sem_duplicacao(self):
        questoes = separar_questoes_enem(
            self.texto_com_duas_opcoes()
        )

        self.assertEqual(
            [questao['numero'] for questao in questoes],
            list(range(1, 6))
            + list(range(1, 6))
            + list(range(6, 91))
        )
        self.assertEqual(
            len({
                (questao['numero'], questao['_idioma'])
                for questao in questoes
            }),
            len(questoes)
        )
        self.assertTrue(
            all(
                [alternativa['letra'] for alternativa in questao['alternativas']]
                == ['A', 'B', 'C', 'D', 'E']
                for questao in questoes
            )
        )
        self.assertEqual(
            [questao['_idioma'] for questao in questoes[:5]],
            ['Inglês'] * 5
        )
        self.assertEqual(
            [questao['_idioma'] for questao in questoes[5:10]],
            ['Espanhol'] * 5
        )
        self.assertEqual(
            len(questoes[10:]),
            85
        )
        self.assertTrue(
            all(
                questao['_idioma'] is None
                for questao in questoes[10:]
            )
        )

    def test_reconhece_marcadores_quebrados_em_linhas_diferentes(self):
        blocos = [
            criar_bloco_questao(1),
            criar_bloco_questao(2),
            criar_bloco_questao(3),
        ]
        texto = '\n'.join(blocos)
        texto = texto.replace('QUESTÃO 01', 'QU\nESTãO 01')
        texto = texto.replace('QUESTÃO 02', 'QU EST ãO 02 ')
        texto = texto.replace('QUESTÃO 03', 'Questão 03')

        questoes = separar_questoes_enem(texto)

        self.assertEqual(
            [questao['numero'] for questao in questoes],
            [1, 2, 3],
        )
        self.assertTrue(
            all(
                [alternativa['letra'] for alternativa in questao['alternativas']]
                == ['A', 'B', 'C', 'D', 'E']
                for questao in questoes
            )
        )

    def test_fragmentos_de_palavra_nao_viram_marcadores_de_alternativa(self):
        texto = '\n'.join([
            'QUESTÃO 20',
            'A característica fundamental é o processo iniciático.',
            'A', ' apresen', 'tar uma carga semântica mítica.',
            'B', ' c', 'onservar elementos dos falares dos escravizados.',
            'C', ' r', 'esgatar expressões portuguesas do período colonial.',
            'D', ' de', 'codificar o ritual religioso dos antepassados.',
            'E', 'favorecer a compreensão do léxico africano.',
        ])

        questoes = separar_questoes_enem(texto)

        self.assertEqual(len(questoes), 1)
        self.assertEqual(
            [alternativa['texto'] for alternativa in questoes[0]['alternativas']],
            [
                'apresentar uma carga semântica mítica.',
                'conservar elementos dos falares dos escravizados.',
                'resgatar expressões portuguesas do período colonial.',
                'decodificar o ritual religioso dos antepassados.',
                'favorecer a compreensão do léxico africano.',
            ],
        )

    def test_separa_questoes_de_6_a_90_com_gabarito_especifico(self):
        blocos = [
            criar_bloco_questao(numero)
            for numero in range(46, 91)
        ]
        texto = '\n'.join(blocos)

        questoes = separar_questoes_enem(texto)
        gabarito = {
            numero: 'ABCDE'[numero % 5]
            for numero in range(46, 91)
        }

        self.assertEqual(
            [questao['numero'] for questao in questoes],
            list(range(46, 91)),
        )

        validas, problemas = dividir_questoes_validas(questoes, gabarito)

        self.assertEqual(problemas, [])
        self.assertEqual(len(validas), 45)

        preparadas = preparar_questoes(validas, gabarito)
        corretas = {
            questao['numero']: next(
                alternativa['letra']
                for alternativa in questao['alternativas']
                if alternativa['correta']
            )
            for questao in preparadas
        }
        self.assertEqual(corretas, gabarito)

    def test_separa_idiomas_em_blocos_repetidos_de_1_a_5(self):
        blocos = [
            criar_bloco_questao(numero, 'inglês')
            for numero in range(1, 6)
        ]
        blocos.extend(
            criar_bloco_questao(numero, 'espanhol')
            for numero in range(1, 6)
        )
        blocos.extend(
            criar_bloco_questao(numero)
            for numero in range(6, 11)
        )
        texto = '\n'.join(blocos)
        texto = texto.replace('QUESTÃO 01', 'QU\nESTãO 01', 2)
        texto = texto.replace('QUESTÃO 02', 'QU EST ãO 02 ', 2)

        questoes = separar_questoes_enem(texto)

        self.assertEqual(
            [questao['numero'] for questao in questoes],
            list(range(1, 6)) + list(range(1, 6)) + list(range(6, 11)),
        )
        self.assertEqual(
            [questao['_idioma'] for questao in questoes[:5]],
            ['Inglês'] * 5,
        )
        self.assertEqual(
            [questao['_idioma'] for questao in questoes[5:10]],
            ['Espanhol'] * 5,
        )
        self.assertTrue(
            all(
                questao['_idioma'] is None
                for questao in questoes[10:]
            )
        )

    def test_associa_gabarito_a_alternativa_correta(self):
        questoes = [
            {
                'numero': 1,
                'texto': 'Enunciado',
                '_idioma': 'Inglês',
                'alternativas': [
                    {'letra': letra, 'texto': letra}
                    for letra in 'ABCDE'
                ],
            },
            {
                'numero': 1,
                'texto': 'Enunciado em espanhol',
                '_idioma': 'Espanhol',
                'alternativas': [
                    {'letra': letra, 'texto': letra}
                    for letra in 'ABCDE'
                ],
            },
        ]

        preparadas = preparar_questoes(
            questoes,
            {
                ('Inglês', 1): 'C',
                ('Espanhol', 1): 'D',
            }
        )

        corretas = [
            alternativa['letra']
            for questao in preparadas
            for alternativa in questao['alternativas']
            if alternativa['correta']
        ]

        self.assertEqual(corretas, ['C', 'D'])

    def test_preparacao_garante_cinco_alternativas_uma_correta_e_texto_limpo(self):
        questoes = [
            {
                'numero': numero,
                'texto': f'Enunciado {numero}.',
                '_idioma': None,
                'alternativas': [
                    {
                        'letra': letra,
                        'texto': (
                            f'Texto {letra} da questão {numero}.'
                            + (' ENEM2024ENEM2024' if letra == 'E' else '')
                        ),
                    }
                    for letra in 'ABCDE'
                ],
            }
            for numero in range(1, 4)
        ]
        gabarito = {1: 'A', 2: 'C', 3: 'E'}

        preparadas = preparar_questoes(questoes, gabarito)

        self.assertEqual(len(preparadas), 3)
        for questao in preparadas:
            alternativas = questao['alternativas']
            self.assertEqual(
                [alternativa['letra'] for alternativa in alternativas],
                ['A', 'B', 'C', 'D', 'E']
            )
            self.assertTrue(all(alternativa['texto'] for alternativa in alternativas))
            self.assertEqual(
                sum(alternativa['correta'] for alternativa in alternativas),
                1
            )
            self.assertTrue(
                all('ENEM2024' not in alternativa['texto'] for alternativa in alternativas)
            )

    def test_validacao_estrutural_aceita_questao_completa_e_gabarito(self):
        questao = {
            'numero': 1,
            'texto': 'Enunciado completo.',
            '_idioma': 'Inglês',
            'alternativas': [
                {'letra': letra, 'texto': f'Texto {letra}.'}
                for letra in 'ABCDE'
            ],
        }

        self.assertEqual(
            validar_estrutura_questoes(
                [questao],
                {('Inglês', 1): 'C'},
            ),
            [],
        )

    def test_validacao_estrutural_rejeita_letras_texto_vazio_e_artefato(self):
        questao = {
            'numero': 8,
            'texto': 'Enunciado completo.',
            'alternativas': [
                {'letra': 'A', 'texto': 'Texto A.'},
                {'letra': 'B', 'texto': ''},
                {'letra': 'C', 'texto': 'Texto C.'},
                {'letra': 'D', 'texto': 'Texto D.'},
                {'letra': 'E', 'texto': 'Texto E ENEM2024.'},
            ],
        }

        erros = validar_estrutura_questoes([questao], {8: 'A'})

        self.assertFalse(any('letras encontradas' in erro for erro in erros))
        self.assertIn('alternativa B sem texto', '\n'.join(erros))
        self.assertIn('artefato de impressão', '\n'.join(erros))

    def test_validacao_estrutural_rejeita_alternativa_vazia_em_sequencia_valida(self):
        questao = {
            'numero': 9,
            'texto': 'Enunciado completo.',
            'alternativas': [
                {'letra': 'A', 'texto': 'Texto A.'},
                {'letra': 'B', 'texto': 'Texto B.'},
                {'letra': 'C', 'texto': 'Texto C.'},
                {'letra': 'D', 'texto': 'Texto D.'},
                {'letra': 'E', 'texto': ''},
            ],
        }

        erros = validar_estrutura_questoes([questao], {9: 'E'})

        self.assertIn('alternativa E sem texto', '\n'.join(erros))

    def test_gabarito_preserva_respostas_diferentes_das_duas_opcoes(self):
        texto = '\n'.join([
            '01 A',
            '02 B',
            '03 C',
            '04 D',
            '05 E',
            '01 B',
            '02 C',
            '03 D',
            '04 E',
            '05 A',
            '06 C',
        ])

        gabarito = extrair_gabarito_enem(texto)

        self.assertEqual(len(gabarito), 11)
        self.assertEqual(gabarito[('Inglês', 1)], 'A')
        self.assertEqual(gabarito[('Espanhol', 1)], 'B')
        self.assertEqual(gabarito[6], 'C')

    def test_gabarito_em_duas_colunas_na_mesma_linha(self):
        texto = '\n'.join([
            '01 A B',
            '02 B C',
            '03 C D',
            '04 D E',
            '05 E A',
            '06 C',
        ])

        gabarito = extrair_gabarito_enem(texto)

        self.assertEqual(len(gabarito), 11)
        self.assertEqual(gabarito[('Inglês', 1)], 'A')
        self.assertEqual(gabarito[('Espanhol', 1)], 'B')
        self.assertEqual(gabarito[('Inglês', 5)], 'E')
        self.assertEqual(gabarito[('Espanhol', 5)], 'A')
        self.assertEqual(gabarito[6], 'C')

    def test_importa_idioma_somente_nas_questoes_de_lingua(self):
        prova = Prova.objects.create(
            nome='ENEM teste',
            tipo='enem',
            ano=2024,
        )
        questoes = [
            {
                'numero': 1,
                'texto': 'Inglês',
                'idioma': 'Inglês',
                'alternativas': [
                    {'letra': 'A', 'texto': 'A', 'correta': True},
                ],
            },
            {
                'numero': 1,
                'texto': 'Espanhol',
                'idioma': 'Espanhol',
                'alternativas': [
                    {'letra': 'B', 'texto': 'B', 'correta': True},
                ],
            },
            {
                'numero': 6,
                'texto': 'Geral',
                'idioma': 'Espanhol',
                'alternativas': [
                    {'letra': 'A', 'texto': 'A', 'correta': True},
                ],
            },
        ]

        importar_questoes_no_banco(
            prova,
            questoes,
            {('Inglês', 1): 'A', ('Espanhol', 1): 'B', 6: 'A'}
        )

        nomes = {
            (numero, idioma): disciplina
            for numero, idioma, disciplina in Questao.objects.filter(
                prova=prova
            ).values_list('numero', 'idioma', 'disciplina__nome')
        }

        self.assertEqual(nomes[(1, 'Inglês')], 'Inglês')
        self.assertEqual(nomes[(1, 'Espanhol')], 'Espanhol')
        self.assertEqual(nomes[(6, None)], 'Não classificada')

        importar_questoes_no_banco(
            prova,
            questoes,
            {('Inglês', 1): 'A', ('Espanhol', 1): 'B', 6: 'A'}
        )
        self.assertEqual(
            Questao.objects.filter(prova=prova).count(),
            3
        )

    def test_unicidade_geral_e_variantes_de_idioma(self):
        prova = Prova.objects.create(
            nome='ENEM unicidade',
            tipo='enem',
            ano=2024,
        )
        disciplina, _ = Disciplina.objects.get_or_create(
            nome='Não classificada'
        )

        Questao.objects.create(
            prova=prova,
            disciplina=disciplina,
            numero=1,
            idioma=None,
            enunciado='Geral',
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Questao.objects.create(
                    prova=prova,
                    disciplina=disciplina,
                    numero=1,
                    idioma=None,
                    enunciado='Geral duplicada',
                )

        Questao.objects.create(
            prova=prova,
            disciplina=disciplina,
            numero=1,
            idioma='Inglês',
            enunciado='Inglês',
        )
        Questao.objects.create(
            prova=prova,
            disciplina=disciplina,
            numero=1,
            idioma='Espanhol',
            enunciado='Espanhol',
        )

    def test_rollback_remove_prova_questoes_alternativas_e_disciplinas(self):
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                prova = Prova.objects.create(
                    nome='ENEM rollback',
                    tipo='enem',
                    ano=2024,
                )
                questao = {
                    'numero': 1,
                    'texto': 'Teste',
                    'idioma': 'Inglês',
                    'alternativas': [
                        {'letra': 'A', 'texto': 'A', 'correta': True},
                    ],
                }
                importar_questoes_no_banco(
                    prova,
                    [questao],
                    {1: 'A'}
                )
                raise RuntimeError('rollback esperado')

        self.assertFalse(
            Prova.objects.filter(nome='ENEM rollback').exists()
        )
        self.assertFalse(
            Questao.objects.exists()
        )
        self.assertFalse(
            Disciplina.objects.exists()
        )

    def test_validacao_estrutural_detecta_numero_idioma_duplicado(self):
        questao = {
            'numero': 1,
            'texto': 'Enunciado completo.',
            '_idioma': 'Inglês',
            'alternativas': [
                {'letra': letra, 'texto': f'Texto {letra}.'}
                for letra in 'ABCDE'
            ],
        }

        erros = validar_estrutura_questoes(
            [questao, dict(questao)],
            {('Inglês', 1): 'A'},
        )

        self.assertIn('duplicada no PDF', '\n'.join(erros))

    def test_validacao_estrutural_detecta_questao_do_gabarito_nao_extraida(self):
        questao = {
            'numero': 2,
            'texto': 'Enunciado completo.',
            'alternativas': [
                {'letra': letra, 'texto': f'Texto {letra}.'}
                for letra in 'ABCDE'
            ],
        }

        erros = validar_estrutura_questoes(
            [questao],
            {1: 'A', 2: 'B'},
        )

        self.assertIn(
            'Gabarito contém a questão 1, mas ela não foi extraída da prova.',
            '\n'.join(erros),
        )

    def test_validacao_estrutural_reconhece_artefato_de_outro_ano(self):
        questao = {
            'numero': 8,
            'texto': 'Enunciado completo.',
            'alternativas': [
                {'letra': 'A', 'texto': 'Texto A.'},
                {'letra': 'B', 'texto': 'Texto B.'},
                {'letra': 'C', 'texto': 'Texto C.'},
                {'letra': 'D', 'texto': 'Texto D.'},
                {'letra': 'E', 'texto': 'Texto E ENEM2023.'},
            ],
        }

        erros = validar_estrutura_questoes([questao], {8: 'A'})

        self.assertIn('artefato de impressão', '\n'.join(erros))

    def test_importacao_prioriza_gabarito_sobre_correta_preparada(self):
        prova = Prova.objects.create(
            nome='ENEM prioridade do gabarito',
            tipo='enem',
            ano=2024,
        )
        questao = {
            'numero': 1,
            'texto': 'Enunciado.',
            'idioma': None,
            'alternativas': [
                {
                    'letra': letra,
                    'texto': f'Texto {letra}.',
                    'correta': letra == 'A',
                }
                for letra in 'ABCDE'
            ],
        }

        importar_questoes_no_banco(
            prova,
            [questao],
            {1: 'C'},
        )

        corretas = list(
            Alternativa.objects.filter(
                questao__prova=prova,
                correta=True,
            ).values_list('letra', flat=True)
        )

        self.assertEqual(corretas, ['C'])

    def test_pdf_sem_texto_orienta_aplicar_ocr(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / 'digitalizado.pdf'
            writer = PdfWriter()
            writer.add_blank_page(width=595, height=842)
            with open(caminho, 'wb') as arquivo:
                writer.write(arquivo)

            with self.assertRaisesMessage(ValueError, 'OCR'):
                extrair_texto_pdf(caminho)

    def test_remove_artefato_de_ano_anterior_na_alternativa(self):
        texto = 'Alternativa legítima. *010175AZ3* ENEM2023'

        self.assertEqual(
            limpar_texto_alternativa(texto),
            'Alternativa legítima.',
        )


class TextosBaseCompartilhadosTestCase(TestCase):
    """Testa a extração e a associação de textos-base compartilhados."""

    def _texto_compartilhado(self):
        blocos = [
            criar_bloco_questao(numero)
            for numero in range(1, 6)
        ]

        blocos.append('\n'.join([
            'Texto para as Questões de 06 a 10.',
            'De próprio punho',
            'Este é o primeiro parágrafo do texto compartilhado,',
            'que ocupa a página inteira e continua depois do rodapé.',
            '1', '2', '3', '4', '5',
            '6', '7', '8', '9', '10',
            'ENEM2025ENEM2025ENEM2025',
            '010175AZ.indb 6 010175AZ.indb 6',
            'LINGUAGENS, CÓDIGOS E SUAS TECNOLOGIAS E REDAÇÃO | '
            '1º DIA | CADERNO 1 | AZUL 7',
            'Este é o segundo parágrafo, que continua na página seguinte',
            'e prova que o texto-base não foi cortado no rodapé.',
            'Fonte: autor fictício (adaptado).',
        ]))

        blocos.extend(
            criar_bloco_questao(numero)
            for numero in range(6, 12)
        )

        return '\n'.join(blocos)

    def _questoes_por_numero(self, questoes):
        return {
            questao['numero']: questao
            for questao in questoes
        }

    def test_extrai_texto_base_compartilhado_entre_6_e_10(self):
        questoes = separar_questoes_enem(self._texto_compartilhado())
        mapa = self._questoes_por_numero(questoes)

        for numero in range(6, 11):
            self.assertEqual(len(mapa[numero]['textos_base']), 1)

        texto_base = mapa[6]['textos_base'][0]

        self.assertEqual(texto_base['inicio'], 6)
        self.assertEqual(texto_base['fim'], 10)
        self.assertEqual(texto_base['titulo'], 'De próprio punho')
        self.assertIn(
            'Texto para as Questões de 06 a 10.',
            texto_base['identificador'],
        )

        # O texto inteiro é preservado, inclusive a continuação após
        # o rodapé e o cabeçalho da página seguinte.
        self.assertIn('primeiro parágrafo', texto_base['texto'])
        self.assertIn('segundo parágrafo', texto_base['texto'])
        self.assertIn(
            'não foi cortado no rodapé',
            texto_base['texto'],
        )

        # Artefatos de impressão e a numeração de linhas são removidos.
        self.assertNotIn('ENEM2025', texto_base['texto'])
        self.assertNotIn('.indb', texto_base['texto'])
        self.assertNotIn('CADERNO', texto_base['texto'])
        self.assertNotIn('\n1\n2\n3\n', texto_base['texto'])

        # Questões fora do intervalo não recebem o texto-base e a
        # questão anterior não é contaminada pelo conteúdo.
        self.assertEqual(mapa[5]['textos_base'], [])
        self.assertEqual(mapa[11]['textos_base'], [])
        self.assertNotIn('primeiro parágrafo', mapa[5]['texto'])

    def test_texto_base_longo_de_pagina_inteira_nao_e_truncado(self):
        paragrafos = [
            f'Parágrafo {numero} do texto-base longo.'
            for numero in range(1, 41)
        ]

        blocos = [
            criar_bloco_questao(numero)
            for numero in range(1, 6)
        ]
        blocos.append('\n'.join([
            'Texto para as Questões de 06 a 10.',
            'De próprio punho',
            *paragrafos,
        ]))
        blocos.extend(
            criar_bloco_questao(numero)
            for numero in range(6, 11)
        )

        questoes = separar_questoes_enem('\n'.join(blocos))
        mapa = self._questoes_por_numero(questoes)
        texto_base = mapa[6]['textos_base'][0]

        for paragrafo in paragrafos:
            self.assertIn(paragrafo, texto_base['texto'])

        self.assertGreater(len(texto_base['texto']), 1000)

    def test_preparacao_mantem_o_mesmo_texto_base_no_grupo(self):
        questoes = separar_questoes_enem(self._texto_compartilhado())
        preparadas = preparar_questoes(questoes)

        mapa = self._questoes_por_numero(preparadas)
        chaves = {
            mapa[numero]['textos_base'][0]['chave']
            for numero in range(6, 11)
        }

        self.assertEqual(len(chaves), 1)
        self.assertEqual(mapa[5]['textos_base'], [])
        self.assertEqual(mapa[11]['textos_base'], [])

    def test_importacao_persiste_um_texto_base_para_o_grupo(self):
        prova = Prova.objects.create(
            nome='ENEM texto-base',
            tipo='enem',
            ano=2025,
        )
        questoes = separar_questoes_enem(self._texto_compartilhado())
        gabarito = {
            numero: 'A'
            for numero in range(1, 12)
        }
        validas, problemas = dividir_questoes_validas(
            questoes,
            gabarito,
        )
        self.assertEqual(problemas, [])

        importar_questoes_no_banco(
            prova,
            preparar_questoes(validas, gabarito),
            gabarito,
        )

        self.assertEqual(
            TextoBase.objects.filter(prova=prova).count(),
            1,
        )

        texto_base = TextoBase.objects.get(prova=prova)

        self.assertEqual(
            set(
                texto_base.questoes_vinculadas.values_list(
                    'questao__numero',
                    flat=True,
                )
            ),
            set(range(6, 11)),
        )
        self.assertEqual(
            QuestaoTextoBase.objects.filter(
                texto_base=texto_base
            ).count(),
            5,
        )

        # O texto-base não vira parte do enunciado individual.
        questao_6 = Questao.objects.get(prova=prova, numero=6)
        self.assertNotIn('primeiro parágrafo', questao_6.enunciado)

        # Na impressão/resultado, o texto-base aparece apenas antes da
        # primeira questão do grupo.
        questoes_banco = list(
            Questao.objects.filter(prova=prova).order_by('numero')
        )
        distribuir_textos_base(questoes_banco)
        exibicao = {
            questao.numero: len(questao.textos_base_para_exibir)
            for questao in questoes_banco
        }

        self.assertEqual(exibicao[5], 0)
        self.assertEqual(exibicao[6], 1)
        self.assertEqual(exibicao[7], 0)
        self.assertEqual(exibicao[10], 0)
        self.assertEqual(exibicao[11], 0)


class ImportacaoPdfRealTestCase(TestCase):
    """
    Testa a importação com os PDFs reais do ENEM 2025 (dia 1, caderno 1).

    Os PDFs ficam em media/; se não estiverem presentes, o teste é
    ignorado para não quebrar ambientes sem os arquivos.
    """

    pasta_media = Path(settings.BASE_DIR) / 'media'
    pdf_prova = pasta_media / 'provas' / '2025_PV_impresso_D1_CD1.pdf'
    pdf_gabarito = pasta_media / 'gabaritos' / '2025_GB_impresso_D1_CD1.pdf'

    @unittest.skipUnless(
        pdf_prova.exists() and pdf_gabarito.exists(),
        'PDFs reais do ENEM 2025 não estão disponíveis.',
    )
    def test_importa_95_questoes_com_idiomas_e_gabarito(self):
        texto_prova = extrair_texto_pdf(self.pdf_prova)
        texto_gabarito = extrair_texto_pdf(self.pdf_gabarito)

        questoes = separar_questoes_enem(texto_prova)
        gabarito = extrair_gabarito_enem(texto_gabarito)

        self.assertEqual(len(questoes), 95)
        self.assertEqual(len(gabarito), 95)

        self.assertEqual(
            [questao['numero'] for questao in questoes[:5]],
            [1, 2, 3, 4, 5],
        )
        self.assertEqual(
            [questao['_idioma'] for questao in questoes[:5]],
            ['Inglês'] * 5,
        )
        self.assertEqual(
            [questao['_idioma'] for questao in questoes[5:10]],
            ['Espanhol'] * 5,
        )
        self.assertEqual(
            [questao['numero'] for questao in questoes[10:]],
            list(range(6, 91)),
        )

        validas, problemas = dividir_questoes_validas(questoes, gabarito)

        self.assertEqual(problemas, [])
        self.assertEqual(len(validas), 95)

        preparadas = preparar_questoes(validas, gabarito)
        corretas = {
            (
                (questao['idioma'], questao['numero'])
                if questao['idioma']
                else questao['numero']
            ): next(
                alternativa['letra']
                for alternativa in questao['alternativas']
                if alternativa['correta']
            )
            for questao in preparadas
        }

        self.assertEqual(corretas[('Inglês', 1)], 'D')
        self.assertEqual(corretas[('Espanhol', 1)], 'B')
        self.assertEqual(corretas[20], 'B')
        self.assertEqual(corretas[46], 'E')
        self.assertEqual(corretas[90], 'A')

        for questao in questoes:
            self.assertEqual(
                [alternativa['letra'] for alternativa in questao['alternativas']],
                ['A', 'B', 'C', 'D', 'E'],
            )
            self.assertTrue(
                all(
                    alternativa['texto'].strip()
                    for alternativa in questao['alternativas']
                )
            )

        # Casos que falhavam antes da correção.
        questao_20 = next(
            questao for questao in questoes
            if questao['numero'] == 20
        )
        self.assertEqual(
            questao_20['alternativas'][1]['texto'],
            'conservar elementos dos falares dos escravizados.',
        )

        questao_46 = next(
            questao for questao in questoes
            if questao['numero'] == 46
        )
        self.assertTrue(
            all(
                alternativa['texto'].strip()
                for alternativa in questao_46['alternativas']
            )
        )

    @unittest.skipUnless(
        pdf_prova.exists() and pdf_gabarito.exists(),
        'PDFs reais do ENEM 2025 não estão disponíveis.',
    )
    def test_extrai_texto_base_real_das_questoes_6_a_10(self):
        questoes = separar_questoes_enem(
            extrair_texto_pdf(self.pdf_prova)
        )
        por_numero = {}

        for questao in questoes:
            por_numero.setdefault(
                questao['numero'],
                [],
            ).append(questao)

        for numero in range(6, 11):
            self.assertEqual(
                len(por_numero[numero][0]['textos_base']),
                1,
            )

        texto_base = por_numero[6][0]['textos_base'][0]

        self.assertEqual(texto_base['inicio'], 6)
        self.assertEqual(texto_base['fim'], 10)
        self.assertIn(
            'Texto para as Questões de 06 a 10.',
            texto_base['identificador'],
        )
        self.assertEqual(texto_base['titulo'], 'De próprio punho')
        self.assertGreater(len(texto_base['texto']), 3000)
        self.assertIn(
            'A escrita e suas tecnologias sofrem interessantes metamorfoses',
            texto_base['texto'],
        )
        self.assertIn('o punho e o pixel', texto_base['texto'])
        self.assertNotIn('ENEM2025', texto_base['texto'])
        self.assertNotIn('.indb', texto_base['texto'])

        self.assertEqual(por_numero[5][0]['textos_base'], [])
        self.assertEqual(por_numero[11][0]['textos_base'], [])
        self.assertNotIn(
            'A escrita e suas tecnologias',
            por_numero[5][0]['texto'],
        )

    @unittest.skipUnless(
        pdf_prova.exists() and pdf_gabarito.exists(),
        'PDFs reais do ENEM 2025 não estão disponíveis.',
    )
    def test_grava_95_questoes_no_banco_de_teste_com_resposta_correta(self):
        questoes = separar_questoes_enem(
            extrair_texto_pdf(self.pdf_prova)
        )
        gabarito = extrair_gabarito_enem(
            extrair_texto_pdf(self.pdf_gabarito)
        )
        validas, problemas = dividir_questoes_validas(questoes, gabarito)
        self.assertEqual(problemas, [])

        prova = Prova.objects.create(
            nome='ENEM 2025 real',
            tipo='enem',
            ano=2025,
        )

        quantidade = importar_questoes_no_banco(
            prova,
            preparar_questoes(validas, gabarito),
            gabarito,
        )

        self.assertEqual(quantidade, 95)
        self.assertEqual(
            Questao.objects.filter(prova=prova).count(),
            95,
        )

        for questao in Questao.objects.filter(prova=prova):
            self.assertEqual(
                questao.alternativas.count(),
                5,
            )
            self.assertEqual(
                questao.alternativas.filter(correta=True).count(),
                1,
            )

        questao_20 = Questao.objects.get(prova=prova, numero=20)
        self.assertEqual(
            questao_20.alternativas.get(correta=True).letra,
            'B',
        )
        self.assertEqual(
            questao_20.alternativas.get(letra='B').texto,
            'conservar elementos dos falares dos escravizados.',
        )

        questao_46 = Questao.objects.get(prova=prova, numero=46)
        self.assertEqual(
            questao_46.alternativas.get(correta=True).letra,
            'E',
        )

    @unittest.skipUnless(
        pdf_prova.exists() and pdf_gabarito.exists(),
        'PDFs reais do ENEM 2025 não estão disponíveis.',
    )
    def test_grava_idiomas_ingles_e_espanhol_no_banco_de_teste(self):
        questoes = separar_questoes_enem(
            extrair_texto_pdf(self.pdf_prova)
        )
        gabarito = extrair_gabarito_enem(
            extrair_texto_pdf(self.pdf_gabarito)
        )
        validas, _ = dividir_questoes_validas(questoes, gabarito)
        prova = Prova.objects.create(
            nome='ENEM 2025 idiomas',
            tipo='enem',
            ano=2025,
        )

        importar_questoes_no_banco(
            prova,
            preparar_questoes(validas, gabarito),
            gabarito,
        )

        idiomas = list(
            Questao.objects.filter(
                prova=prova,
                numero__in=range(1, 6),
            ).values_list('numero', 'idioma')
        )
        self.assertEqual(
            sorted(idiomas),
            sorted(
                [(numero, 'Inglês') for numero in range(1, 6)]
                + [(numero, 'Espanhol') for numero in range(1, 6)]
            ),
        )


class ProcessarProvaViewTestCase(TestCase):
    def setUp(self):
        self.desenvolvedor = User.objects.create_user(
            username='dev_teste',
            password='SenhaTeste123!',
        )
        Perfil.objects.update_or_create(
            usuario=self.desenvolvedor,
            defaults={'tipo': 'desenvolvedor'},
        )
        self.prova = Prova.objects.create(
            nome='ENEM processamento',
            tipo='enem',
            ano=2024,
            arquivo_pdf='provas/fake.pdf',
            arquivo_gabarito='gabaritos/fake.pdf',
        )
        self.url = reverse(
            'provas:processar',
            kwargs={'prova_id': self.prova.id},
        )
        self.client.login(
            username='dev_teste',
            password='SenhaTeste123!',
        )

    def _questao(self, numero, idioma=None):
        return {
            'numero': numero,
            'texto': f'Enunciado {numero}.',
            '_idioma': idioma,
            'alternativas': [
                {
                    'letra': letra,
                    'texto': f'Texto {letra}.',
                    'correta': False,
                }
                for letra in 'ABCDE'
            ],
        }

    def test_processar_importa_questoes_e_respeita_gabarito(self):
        questoes = [
            self._questao(1, 'Inglês'),
            self._questao(6),
        ]
        gabarito = {
            ('Inglês', 1): 'C',
            6: 'B',
        }

        with (
            patch(
                'provas.views.extrair_texto_pdf',
                return_value='texto',
            ),
            patch(
                'provas.views.separar_questoes_enem',
                return_value=questoes,
            ),
            patch(
                'provas.views.extrair_gabarito_enem',
                return_value=gabarito,
            ),
        ):
            response = self.client.post(self.url)

        self.assertRedirects(
            response,
            reverse(
                'provas:detalhe',
                kwargs={'prova_id': self.prova.id},
            ),
        )

        self.prova.refresh_from_db()
        self.assertEqual(self.prova.status_importacao, 'processada')
        self.assertIsNotNone(self.prova.data_processamento)
        self.assertEqual(
            Questao.objects.filter(prova=self.prova).count(),
            2,
        )

        corretas = {
            questao.numero: questao.alternativas.get(
                correta=True
            ).letra
            for questao in Questao.objects.filter(prova=self.prova)
        }
        self.assertEqual(corretas, {1: 'C', 6: 'B'})

    def test_processar_parcial_importa_questoes_validas_e_relata_problemas(self):
        questoes = [
            self._questao(1, 'Inglês'),
            self._questao(2, 'Inglês'),
        ]
        gabarito = {
            ('Inglês', 1): 'A',
            ('Inglês', 3): 'B',
        }

        with (
            patch(
                'provas.views.extrair_texto_pdf',
                return_value='texto',
            ),
            patch(
                'provas.views.separar_questoes_enem',
                return_value=questoes,
            ),
            patch(
                'provas.views.extrair_gabarito_enem',
                return_value=gabarito,
            ),
        ):
            response = self.client.post(self.url)

        self.assertRedirects(
            response,
            reverse(
                'provas:detalhe',
                kwargs={'prova_id': self.prova.id},
            ),
        )

        self.prova.refresh_from_db()
        self.assertEqual(self.prova.status_importacao, 'processada')
        self.assertIn(
            'Questão Inglês: 2: gabarito não encontrado.',
            self.prova.mensagem_importacao,
        )
        self.assertIn(
            'Gabarito contém a questão Inglês: 3',
            self.prova.mensagem_importacao,
        )

        # A questão válida é preservada; apenas a inválida é ignorada.
        questoes_importadas = Questao.objects.filter(prova=self.prova)
        self.assertEqual(questoes_importadas.count(), 1)
        self.assertEqual(questoes_importadas.get().numero, 1)
        self.assertEqual(
            questoes_importadas.get().alternativas.get(correta=True).letra,
            'A',
        )

        resposta_detalhe = self.client.get(
            reverse(
                'provas:detalhe',
                kwargs={'prova_id': self.prova.id},
            )
        )
        self.assertContains(resposta_detalhe, 'Importação com avisos')
        self.assertContains(
            resposta_detalhe,
            'Gabarito contém a questão Inglês: 3',
        )

    def test_processar_falha_quando_nenhuma_questao_e_valida(self):
        questoes = [
            {
                'numero': 2,
                'texto': '',
                '_idioma': 'Inglês',
                'alternativas': [],
            },
        ]
        gabarito = {('Inglês', 2): 'A'}

        with (
            patch(
                'provas.views.extrair_texto_pdf',
                return_value='texto',
            ),
            patch(
                'provas.views.separar_questoes_enem',
                return_value=questoes,
            ),
            patch(
                'provas.views.extrair_gabarito_enem',
                return_value=gabarito,
            ),
        ):
            response = self.client.post(self.url)

        self.assertRedirects(
            response,
            reverse(
                'provas:detalhe',
                kwargs={'prova_id': self.prova.id},
            ),
        )

        self.prova.refresh_from_db()
        self.assertEqual(self.prova.status_importacao, 'erro')
        self.assertIn(
            'enunciado sem texto',
            self.prova.mensagem_importacao,
        )
        self.assertFalse(
            Questao.objects.filter(prova=self.prova).exists()
        )

    def test_processar_preserva_importacao_quando_imagem_falha(self):
        questoes = [self._questao(1, 'Inglês')]
        gabarito = {('Inglês', 1): 'A'}

        with (
            patch(
                'provas.views.extrair_texto_pdf',
                return_value='texto',
            ),
            patch(
                'provas.views.separar_questoes_enem',
                return_value=questoes,
            ),
            patch(
                'provas.views.extrair_gabarito_enem',
                return_value=gabarito,
            ),
            patch(
                'provas.views.extrair_e_registrar_imagens',
                side_effect=RuntimeError('falha simulada'),
            ),
        ):
            response = self.client.post(self.url)

        self.assertRedirects(
            response,
            reverse(
                'provas:detalhe',
                kwargs={'prova_id': self.prova.id},
            ),
        )

        self.prova.refresh_from_db()
        self.assertEqual(self.prova.status_importacao, 'processada')
        self.assertIn(
            'imagens não puderam ser processadas',
            self.prova.mensagem_importacao,
        )
        self.assertEqual(
            Questao.objects.filter(prova=self.prova).count(),
            1,
        )


def criar_pdf_com_imagens(caminho, imagens):
    """
    Cria um PDF de teste com uma imagem por página.
    """
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)

    primeira = imagens[0]

    if len(imagens) == 1:
        primeira.save(caminho, 'PDF')
    else:
        primeira.save(
            caminho,
            'PDF',
            save_all=True,
            append_images=imagens[1:],
        )


def criar_imagem_prova(
    prova,
    pagina=1,
    indice_pagina=0,
    tamanho=(120, 60),
    cor=(30, 90, 180),
):
    """
    Cria um registro de imagem de prova com um PNG real.
    """
    buffer = BytesIO()
    Image.new('RGB', tamanho, cor).save(buffer, 'PNG')
    conteudo = buffer.getvalue()
    hash_sha256 = hashlib.sha256(conteudo).hexdigest()

    return ImagemProva.objects.create(
        prova=prova,
        arquivo=SimpleUploadedFile(
            f'{hash_sha256[:10]}.png',
            conteudo,
            content_type='image/png',
        ),
        hash_sha256=hash_sha256,
        pagina=pagina,
        indice_pagina=indice_pagina,
        nome_original=f'imagem-{pagina}-{indice_pagina}.png',
        largura=tamanho[0],
        altura=tamanho[1],
        exibida=True,
        x=50,
        y=500,
    )


class ImpressaoTextoBaseViewTestCase(TestCase):
    """Verifica a deduplicação do texto-base na impressão da prova."""

    def setUp(self):
        desenvolvedor = User.objects.create_user(
            username='dev_impressao',
            password='SenhaTeste123!',
        )
        Perfil.objects.update_or_create(
            usuario=desenvolvedor,
            defaults={'tipo': 'desenvolvedor'},
        )

        self.prova = Prova.objects.create(
            nome='ENEM impressão',
            tipo='enem',
            ano=2025,
        )
        disciplina = Disciplina.objects.create(
            nome='Não classificada'
        )

        for numero in (6, 7):
            questao = Questao.objects.create(
                prova=self.prova,
                disciplina=disciplina,
                numero=numero,
                enunciado=f'Enunciado da questão {numero}.',
            )

            for letra in 'ABCDE':
                Alternativa.objects.create(
                    questao=questao,
                    letra=letra,
                    texto=f'Alternativa {letra}.',
                )

        texto_base = TextoBase.objects.create(
            prova=self.prova,
            chave='b' * 64,
            identificador='Texto para as Questões de 06 a 10.',
            titulo='De próprio punho',
            texto='Conteúdo compartilhado do texto-base.',
            ordem=0,
        )

        for questao in self.prova.questoes.all():
            QuestaoTextoBase.objects.create(
                texto_base=texto_base,
                questao=questao,
                ordem=0,
            )

        self.client.login(
            username='dev_impressao',
            password='SenhaTeste123!',
        )

        self.url = reverse(
            'provas:imprimir',
            kwargs={'prova_id': self.prova.id},
        )

    def test_impressao_exibe_texto_base_uma_vez_antes_do_grupo(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)

        html = response.content.decode()
        self.assertContains(
            response,
            'Texto para as Questões de 06 a 10.',
        )
        self.assertEqual(html.count('De próprio punho'), 1)
        self.assertEqual(
            html.count('Conteúdo compartilhado do texto-base.'),
            1,
        )
        self.assertLess(
            html.index('De próprio punho'),
            html.index('Enunciado da questão 6.'),
        )


class ExtracaoImagensPdfTestCase(TestCase):
    def test_extrai_imagens_preservando_dimensoes_e_posicao(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / 'prova.pdf'

            criar_pdf_com_imagens(caminho, [
                Image.new('RGB', (120, 60), (200, 30, 40)),
                Image.new('RGB', (80, 40), (20, 130, 60)),
            ])

            imagens = extrair_imagens_pdf(caminho)

        self.assertEqual(len(imagens), 2)
        self.assertEqual(
            (imagens[0]['largura'], imagens[0]['altura']),
            (120, 60),
        )
        self.assertEqual(
            (imagens[1]['largura'], imagens[1]['altura']),
            (80, 40),
        )
        self.assertEqual(imagens[0]['pagina'], 1)
        self.assertEqual(imagens[1]['pagina'], 2)
        self.assertTrue(imagens[0]['exibida'])
        self.assertTrue(imagens[1]['exibida'])
        self.assertIsNotNone(imagens[0]['x'])
        self.assertIsNotNone(imagens[0]['y'])
        self.assertTrue(imagens[0]['dados'])

    def test_reprocessar_pdf_nao_duplica_imagens(self):
        with tempfile.TemporaryDirectory() as pasta:
            with self.settings(MEDIA_ROOT=pasta):
                caminho = Path(pasta) / 'provas' / 'prova.pdf'

                criar_pdf_com_imagens(caminho, [
                    Image.new('RGB', (120, 60), (200, 30, 40)),
                    Image.new('RGB', (80, 40), (20, 130, 60)),
                ])

                prova = Prova.objects.create(
                    nome='ENEM imagens',
                    tipo='enem',
                    ano=2024,
                    arquivo_pdf='provas/prova.pdf',
                )

                primeiro = extrair_e_registrar_imagens(prova)
                segundo = extrair_e_registrar_imagens(prova)

                imagens = list(
                    ImagemProva.objects.filter(prova=prova)
                )

                self.assertEqual(primeiro['criadas'], 2)
                self.assertEqual(segundo['criadas'], 0)
                self.assertEqual(segundo['reutilizadas'], 2)
                self.assertEqual(len(imagens), 2)

                for imagem in imagens:
                    self.assertTrue(
                        (Path(pasta) / imagem.arquivo.name).exists()
                    )
                    self.assertEqual(
                        imagem.hash_sha256,
                        hashlib.sha256(
                            (
                                Path(pasta)
                                / imagem.arquivo.name
                            ).read_bytes()
                        ).hexdigest(),
                    )

    def test_imagem_repetida_em_paginas_diferentes_nao_e_perdida(self):
        with tempfile.TemporaryDirectory() as pasta:
            with self.settings(MEDIA_ROOT=pasta):
                caminho = Path(pasta) / 'provas' / 'repetida.pdf'
                imagem = Image.new('RGB', (60, 30), (10, 10, 10))
                criar_pdf_com_imagens(caminho, [imagem, imagem])

                prova = Prova.objects.create(
                    nome='ENEM imagem repetida',
                    tipo='enem',
                    ano=2024,
                    arquivo_pdf='provas/repetida.pdf',
                )

                extrair_e_registrar_imagens(prova)

                registros = list(
                    ImagemProva.objects.filter(prova=prova)
                )

                self.assertEqual(len(registros), 2)
                self.assertEqual(
                    {registro.pagina for registro in registros},
                    {1, 2},
                )
                self.assertEqual(
                    {registro.hash_sha256 for registro in registros},
                    {registros[0].hash_sha256},
                )


class SugestaoAssociacaoImagemTestCase(TestCase):
    def _marcador(
        self,
        pagina,
        numero,
        x=50,
        y=700,
        idioma=None,
        altura_pagina=842,
    ):
        return {
            'pagina': pagina,
            'numero': numero,
            'idioma': idioma,
            'x': x,
            'y': y,
            'altura_pagina': altura_pagina,
            'ordem': 0,
        }

    def test_escolhe_ultimo_marcador_acima_da_imagem(self):
        questoes = [
            SimpleNamespace(numero=1, idioma=None),
            SimpleNamespace(numero=2, idioma=None),
        ]
        marcadores = [
            self._marcador(1, 1, y=700),
            self._marcador(1, 2, y=400),
        ]

        imagem = SimpleNamespace(pagina=1, x=50, y=500)

        self.assertIs(
            sugerir_questao_para_imagem(
                imagem,
                marcadores,
                questoes,
            ),
            questoes[0],
        )

        imagem.y = 300

        self.assertIs(
            sugerir_questao_para_imagem(
                imagem,
                marcadores,
                questoes,
            ),
            questoes[1],
        )

    def test_respeita_coluna_da_imagem(self):
        questoes = [
            SimpleNamespace(numero=1, idioma=None),
            SimpleNamespace(numero=2, idioma=None),
        ]
        marcadores = [
            self._marcador(1, 1, x=50, y=700),
            self._marcador(1, 2, x=320, y=700),
        ]

        imagem = SimpleNamespace(pagina=1, x=320, y=600)

        self.assertIs(
            sugerir_questao_para_imagem(
                imagem,
                marcadores,
                questoes,
            ),
            questoes[1],
        )

    def test_imagem_no_topo_pertence_a_questao_da_pagina_anterior(self):
        questoes = [
            SimpleNamespace(numero=1, idioma=None),
            SimpleNamespace(numero=2, idioma=None),
        ]
        marcadores = [
            self._marcador(1, 1, y=700),
            self._marcador(1, 2, y=200),
        ]

        imagem = SimpleNamespace(pagina=2, x=50, y=700)

        self.assertIs(
            sugerir_questao_para_imagem(
                imagem,
                marcadores,
                questoes,
            ),
            questoes[1],
        )

    def test_imagem_fora_do_topo_em_pagina_sem_marcadores_nao_sugere(self):
        questoes = [
            SimpleNamespace(numero=1, idioma=None),
            SimpleNamespace(numero=2, idioma=None),
        ]
        marcadores = [
            self._marcador(1, 1, y=700),
            self._marcador(1, 2, y=200),
        ]

        # Página sem marcadores e imagem no meio da página: não há
        # segurança para dizer que continua a questão anterior.
        imagem = SimpleNamespace(
            pagina=2,
            x=50,
            y=270,
            altura_exibicao=94,
        )

        self.assertIsNone(
            sugerir_questao_para_imagem(
                imagem,
                marcadores,
                questoes,
            )
        )

    def test_pagina_com_marcadores_nao_usa_questao_anterior(self):
        questoes = [
            SimpleNamespace(numero=1, idioma=None),
            SimpleNamespace(numero=2, idioma=None),
        ]
        marcadores = [
            self._marcador(1, 1, y=700),
            self._marcador(2, 2, y=300),
        ]

        # A imagem está acima do único marcador da página 2. Mesmo
        # assim não deve ser ligada à questão da página 1.
        imagem = SimpleNamespace(pagina=2, x=50, y=600)

        self.assertIsNone(
            sugerir_questao_para_imagem(
                imagem,
                marcadores,
                questoes,
            )
        )

    def test_nao_sugere_quando_idioma_e_ambiguo(self):
        questoes = [
            SimpleNamespace(numero=1, idioma='Inglês'),
            SimpleNamespace(numero=1, idioma='Espanhol'),
        ]
        marcadores = [self._marcador(1, 1, y=700, idioma=None)]
        imagem = SimpleNamespace(pagina=1, x=50, y=500)

        self.assertIsNone(
            sugerir_questao_para_imagem(
                imagem,
                marcadores,
                questoes,
            )
        )

    def test_usa_idioma_do_marcador(self):
        questoes = [
            SimpleNamespace(numero=1, idioma='Inglês'),
            SimpleNamespace(numero=1, idioma='Espanhol'),
        ]
        marcadores = [
            self._marcador(1, 1, y=700, idioma='Espanhol'),
        ]
        imagem = SimpleNamespace(pagina=1, x=50, y=500)

        self.assertIs(
            sugerir_questao_para_imagem(
                imagem,
                marcadores,
                questoes,
            ),
            questoes[1],
        )

    def test_sem_posicao_e_varios_marcadores_nao_sugere(self):
        questoes = [
            SimpleNamespace(numero=1, idioma=None),
            SimpleNamespace(numero=2, idioma=None),
        ]
        marcadores = [
            self._marcador(1, 1, y=None),
            self._marcador(1, 2, y=None),
        ]
        imagem = SimpleNamespace(pagina=1, x=None, y=None)

        self.assertIsNone(
            sugerir_questao_para_imagem(
                imagem,
                marcadores,
                questoes,
            )
        )


class PersistenciaAssociacaoImagemTestCase(TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)

        self.configuracao = override_settings(
            MEDIA_ROOT=self.pasta.name
        )
        self.configuracao.enable()
        self.addCleanup(self.configuracao.disable)

        self.prova = Prova.objects.create(
            nome='ENEM associação de imagens',
            tipo='enem',
            ano=2024,
            arquivo_pdf='provas/prova.pdf',
        )
        self.disciplina = Disciplina.objects.create(
            nome='Não classificada'
        )
        self.questao = Questao.objects.create(
            prova=self.prova,
            disciplina=self.disciplina,
            numero=1,
            enunciado='Enunciado com imagem.',
        )

    def _marcadores(self):
        return [
            {
                'pagina': 1,
                'numero': 1,
                'idioma': None,
                'x': 50,
                'y': 700,
                'ordem': 0,
            }
        ]

    def test_sugestao_nao_preenche_imagem_antes_de_confirmar(self):
        imagem = criar_imagem_prova(self.prova, pagina=1)

        with patch(
            'provas.imagens.mapear_marcadores_pdf',
            return_value=self._marcadores(),
        ):
            quantidade = gerar_sugestoes_associacao(self.prova)

        associacao = ImagemQuestao.objects.get(imagem=imagem)

        self.assertEqual(quantidade, 1)
        self.assertFalse(associacao.confirmada)
        self.assertEqual(associacao.origem, 'automatica')

        self.questao.refresh_from_db()
        self.assertFalse(self.questao.imagem)

    def test_confirmar_preenche_campo_legado_e_remover_limpa(self):
        imagem = criar_imagem_prova(self.prova, pagina=1)

        with patch(
            'provas.imagens.mapear_marcadores_pdf',
            return_value=self._marcadores(),
        ):
            gerar_sugestoes_associacao(self.prova)

        associacao = ImagemQuestao.objects.get(imagem=imagem)
        confirmar_associacao(associacao)

        self.questao.refresh_from_db()
        self.assertEqual(
            self.questao.imagem.name,
            imagem.arquivo.name,
        )

        remover_associacao(associacao)

        self.questao.refresh_from_db()
        self.assertFalse(self.questao.imagem)

    def test_permite_multiplas_imagens_na_mesma_questao(self):
        primeira = criar_imagem_prova(
            self.prova,
            pagina=1,
            cor=(10, 20, 30),
        )
        segunda = criar_imagem_prova(
            self.prova,
            pagina=2,
            cor=(40, 50, 60),
        )

        marcadores = [
            {
                'pagina': 1,
                'numero': 1,
                'idioma': None,
                'x': 50,
                'y': 700,
                'ordem': 0,
            },
            {
                'pagina': 2,
                'numero': 1,
                'idioma': None,
                'x': 50,
                'y': 700,
                'ordem': 1,
            },
        ]

        with patch(
            'provas.imagens.mapear_marcadores_pdf',
            return_value=marcadores,
        ):
            gerar_sugestoes_associacao(self.prova)

        for associacao in ImagemQuestao.objects.filter(
            questao=self.questao
        ):
            confirmar_associacao(associacao)

        self.assertEqual(
            len(self.questao.imagens_exibicao),
            2,
        )

        self.questao.refresh_from_db()
        self.assertEqual(
            self.questao.imagem.name,
            primeira.arquivo.name,
        )
        self.assertTrue(
            any(
                imagem.name == segunda.arquivo.name
                for imagem in self.questao.imagens_exibicao
            )
        )

    def test_associacao_manual_move_imagem_entre_questoes(self):
        segunda_questao = Questao.objects.create(
            prova=self.prova,
            disciplina=self.disciplina,
            numero=2,
            enunciado='Outra questão.',
        )
        imagem = criar_imagem_prova(self.prova, pagina=1)

        associar_imagem(imagem, self.questao)
        associar_imagem(imagem, segunda_questao)

        self.questao.refresh_from_db()
        segunda_questao.refresh_from_db()

        self.assertFalse(self.questao.imagem)
        self.assertEqual(
            segunda_questao.imagem.name,
            imagem.arquivo.name,
        )
        self.assertFalse(
            ImagemQuestao.objects.filter(
                imagem=imagem,
                questao=self.questao,
            ).exists()
        )

    def test_sincronizacao_preserva_imagem_legada_de_questoes(self):
        buffer = BytesIO()
        Image.new('RGB', (50, 50), (90, 90, 90)).save(buffer, 'PNG')
        self.questao.imagem = SimpleUploadedFile(
            'legado.png',
            buffer.getvalue(),
            content_type='image/png',
        )
        self.questao.save(update_fields=['imagem'])

        sincronizar_imagem_principal(self.questao)

        self.questao.refresh_from_db()
        self.assertTrue(self.questao.imagem)

    def test_exibicao_oculta_associacao_automatica_insegura(self):
        imagem = criar_imagem_prova(self.prova, pagina=2)
        ImagemQuestao.objects.create(
            imagem=imagem,
            questao=self.questao,
            confirmada=True,
            origem='automatica',
        )

        marcadores = [
            {
                'pagina': 1,
                'numero': 1,
                'idioma': None,
                'x': 50,
                'y': 700,
                'altura_pagina': 842,
                'ordem': 0,
            }
        ]

        with patch(
            'provas.imagens.mapear_marcadores_pdf',
            return_value=marcadores,
        ):
            self.assertEqual(self.questao.imagens_exibicao, [])

    def test_exibicao_mantem_associacao_automatica_segura(self):
        imagem = criar_imagem_prova(self.prova, pagina=2)
        ImagemQuestao.objects.create(
            imagem=imagem,
            questao=self.questao,
            confirmada=True,
            origem='automatica',
        )

        marcadores = [
            {
                'pagina': 2,
                'numero': 1,
                'idioma': None,
                'x': 50,
                'y': 700,
                'altura_pagina': 842,
                'ordem': 0,
            }
        ]

        with patch(
            'provas.imagens.mapear_marcadores_pdf',
            return_value=marcadores,
        ):
            self.assertEqual(
                self.questao.imagens_exibicao,
                [imagem.arquivo],
            )

    def test_exibicao_oculta_imagem_legada_extraida_insegura(self):
        imagem = criar_imagem_prova(self.prova, pagina=2)
        self.questao.imagem.name = imagem.arquivo.name
        self.questao.save(update_fields=['imagem'])

        marcadores = [
            {
                'pagina': 1,
                'numero': 1,
                'idioma': None,
                'x': 50,
                'y': 700,
                'altura_pagina': 842,
                'ordem': 0,
            }
        ]

        with patch(
            'provas.imagens.mapear_marcadores_pdf',
            return_value=marcadores,
        ):
            self.assertEqual(self.questao.imagens_exibicao, [])


class RevisaoImagensViewTestCase(TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)

        self.configuracao = override_settings(
            MEDIA_ROOT=self.pasta.name
        )
        self.configuracao.enable()
        self.addCleanup(self.configuracao.disable)

        self.desenvolvedor = User.objects.create_user(
            username='dev_imagens',
            password='Substituir123!',
        )
        Perfil.objects.update_or_create(
            usuario=self.desenvolvedor,
            defaults={'tipo': 'desenvolvedor'},
        )

        self.prova = Prova.objects.create(
            nome='ENEM revisão de imagens',
            tipo='enem',
            ano=2024,
            status_importacao='processada',
        )
        self.disciplina = Disciplina.objects.create(
            nome='Não classificada'
        )
        self.questao = Questao.objects.create(
            prova=self.prova,
            disciplina=self.disciplina,
            numero=1,
            enunciado='Enunciado da questão 1.',
        )
        self.segunda_questao = Questao.objects.create(
            prova=self.prova,
            disciplina=self.disciplina,
            numero=2,
            enunciado='Enunciado da questão 2.',
        )

        for questao in (self.questao, self.segunda_questao):
            for letra in 'ABCDE':
                Alternativa.objects.create(
                    questao=questao,
                    letra=letra,
                    texto=f'Alternativa {letra}.',
                    correta=letra == 'A',
                )

        self.client.login(
            username='dev_imagens',
            password='Substituir123!',
        )
        self.revisar_url = reverse(
            'provas:revisar_imagens',
            kwargs={'prova_id': self.prova.id},
        )
        self.acao_url = reverse(
            'provas:acao_imagem',
            kwargs={'prova_id': self.prova.id},
        )

    def test_revisao_lista_imagens_e_questoes(self):
        imagem = criar_imagem_prova(self.prova)

        response = self.client.get(self.revisar_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Revisar imagens')
        self.assertContains(response, imagem.arquivo.url)

    def test_associacao_manual_confirma_e_preenche_questao(self):
        imagem = criar_imagem_prova(self.prova)

        response = self.client.post(
            self.acao_url,
            {
                'acao': 'associar',
                'imagem_id': imagem.id,
                'questao_id': self.questao.id,
            },
        )

        self.assertRedirects(response, self.revisar_url)

        associacao = ImagemQuestao.objects.get(
            imagem=imagem,
            questao=self.questao,
        )
        self.assertTrue(associacao.confirmada)

        self.questao.refresh_from_db()
        self.assertEqual(
            self.questao.imagem.name,
            imagem.arquivo.name,
        )

    def test_confirmar_sugestao_pendente(self):
        imagem = criar_imagem_prova(self.prova)
        associacao = ImagemQuestao.objects.create(
            imagem=imagem,
            questao=self.questao,
            confirmada=False,
            origem='automatica',
        )

        response = self.client.post(
            self.acao_url,
            {
                'acao': 'confirmar',
                'associacao_id': associacao.id,
            },
        )

        self.assertRedirects(response, self.revisar_url)

        associacao.refresh_from_db()
        self.assertTrue(associacao.confirmada)

    def test_remover_associacao_limpa_imagem_principal(self):
        imagem = criar_imagem_prova(self.prova)
        associacao = associar_imagem(imagem, self.questao)

        response = self.client.post(
            self.acao_url,
            {
                'acao': 'remover',
                'associacao_id': associacao.id,
            },
        )

        self.assertRedirects(response, self.revisar_url)

        self.questao.refresh_from_db()
        self.assertFalse(self.questao.imagem)
        self.assertFalse(
            ImagemQuestao.objects.filter(id=associacao.id).exists()
        )

    def test_ignorar_e_reativar_imagem_sem_apagar_arquivo(self):
        imagem = criar_imagem_prova(self.prova)
        caminho = Path(self.pasta.name) / imagem.arquivo.name

        response = self.client.post(
            self.acao_url,
            {
                'acao': 'ignorar',
                'imagem_id': imagem.id,
            },
        )

        self.assertRedirects(response, self.revisar_url)
        imagem.refresh_from_db()
        self.assertTrue(imagem.ignorada)
        self.assertTrue(caminho.exists())

        response = self.client.post(
            self.acao_url,
            {
                'acao': 'reativar',
                'imagem_id': imagem.id,
            },
        )

        self.assertRedirects(response, self.revisar_url)
        imagem.refresh_from_db()
        self.assertFalse(imagem.ignorada)

    def test_nao_ignora_imagem_com_associacao_confirmada(self):
        imagem = criar_imagem_prova(self.prova)
        associar_imagem(imagem, self.questao)

        response = self.client.post(
            self.acao_url,
            {
                'acao': 'ignorar',
                'imagem_id': imagem.id,
            },
        )

        self.assertRedirects(response, self.revisar_url)
        imagem.refresh_from_db()
        self.assertFalse(imagem.ignorada)

    def test_confirmar_todas_as_sugestoes(self):
        primeira = criar_imagem_prova(self.prova, pagina=1)
        segunda = criar_imagem_prova(
            self.prova,
            pagina=2,
            cor=(70, 80, 90),
        )

        ImagemQuestao.objects.create(
            imagem=primeira,
            questao=self.questao,
            confirmada=False,
            origem='automatica',
        )
        ImagemQuestao.objects.create(
            imagem=segunda,
            questao=self.segunda_questao,
            confirmada=False,
            origem='automatica',
        )

        response = self.client.post(
            self.acao_url,
            {'acao': 'confirmar_sugestoes'},
        )

        self.assertRedirects(response, self.revisar_url)
        self.assertEqual(
            ImagemQuestao.objects.filter(
                imagem__prova=self.prova,
                confirmada=True,
            ).count(),
            2,
        )

    def test_associa_duas_imagens_a_mesma_questao(self):
        primeira = criar_imagem_prova(self.prova, pagina=1)
        segunda = criar_imagem_prova(
            self.prova,
            pagina=2,
            cor=(5, 15, 25),
        )

        for imagem in (primeira, segunda):
            self.client.post(
                self.acao_url,
                {
                    'acao': 'associar',
                    'imagem_id': imagem.id,
                    'questao_id': self.questao.id,
                },
            )

        self.questao.refresh_from_db()
        self.assertEqual(
            len(self.questao.imagens_exibicao),
            2,
        )
        self.assertEqual(
            self.questao.imagem.name,
            primeira.arquivo.name,
        )

    def test_extrai_imagens_de_prova_ja_processada(self):
        caminho = Path(self.pasta.name) / 'provas' / 'teste.pdf'
        criar_pdf_com_imagens(
            caminho,
            [Image.new('RGB', (100, 50), (1, 2, 3))],
        )
        self.prova.arquivo_pdf = 'provas/teste.pdf'
        self.prova.save(update_fields=['arquivo_pdf'])

        response = self.client.post(
            reverse(
                'provas:extrair_imagens',
                kwargs={'prova_id': self.prova.id},
            )
        )

        self.assertRedirects(response, self.revisar_url)
        self.assertEqual(
            ImagemProva.objects.filter(prova=self.prova).count(),
            1,
        )

    def test_impressao_exibe_enunciado_imagem_e_alternativas(self):
        imagem = criar_imagem_prova(self.prova)
        associar_imagem(imagem, self.questao)

        response = self.client.get(
            reverse(
                'provas:imprimir',
                kwargs={'prova_id': self.prova.id},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Enunciado da questão 1.')
        self.assertContains(response, imagem.arquivo.url)
        self.assertContains(response, 'Alternativa A.')
        self.assertContains(response, 'window.print()')


class NormalizacaoEnunciadoTestCase(unittest.TestCase):
    """Verifica a reorganização das linhas extraídas do PDF."""

    def test_junta_linhas_do_mesmo_paragrafo(self):
        texto = (
            'Margot Robbie foi criticada por "não ser bonita o suficiente"\n'
            'para interpretar a Barbie. Recentemente, Paolla Oliveira foi\n'
            'chamada de gorda.'
        )

        resultado = normalizar_enunciado(texto)

        self.assertEqual(
            resultado,
            'Margot Robbie foi criticada por "não ser bonita o suficiente" '
            'para interpretar a Barbie. Recentemente, Paolla Oliveira foi '
            'chamada de gorda.',
        )

    def test_mantem_titulo_em_paragrafo_proprio(self):
        texto = (
            'TEXTO I\n'
            'Este é o texto que acompanha a questão e ocupa várias linhas '
            'na coluna original do PDF.\n'
            'Ele continua aqui.'
        )

        resultado = normalizar_enunciado(texto)

        self.assertTrue(resultado.startswith('TEXTO I\n\n'))

    def test_junta_referencia_acesso_em(self):
        texto = (
            'KORICH, B. S. Disponível em: www1.folha.uol.com.br. \n'
            'Acesso em: 22\n'
            'jan. 2024 (adaptado).'
        )

        resultado = normalizar_enunciado(texto)

        self.assertNotIn('\n', resultado)
        self.assertIn('Acesso em: 22 jan. 2024 (adaptado).', resultado)

    def test_texto_vazio_retorna_vazio(self):
        self.assertEqual(normalizar_enunciado(''), '')
        self.assertEqual(normalizar_enunciado(None), '')


class PaginasProvaTestCase(TestCase):
    """Verifica a renderização e o cache das páginas originais do PDF."""

    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)

        self.configuracao = override_settings(MEDIA_ROOT=self.pasta.name)
        self.configuracao.enable()
        self.addCleanup(self.configuracao.disable)

        caminho_pdf = Path(self.pasta.name) / 'provas' / 'teste.pdf'
        caminho_pdf.parent.mkdir(parents=True, exist_ok=True)

        escritor = PdfWriter()
        escritor.add_blank_page(width=595, height=842)
        with caminho_pdf.open('wb') as arquivo:
            escritor.write(arquivo)

        self.prova = Prova.objects.create(
            nome='Prova para renderização',
            tipo='enem',
            ano=2024,
            status_importacao='processada',
            arquivo_pdf='provas/teste.pdf',
        )

    def test_total_paginas(self):
        self.assertEqual(total_paginas(self.prova), 1)

    def test_renderiza_pagina_e_reutiliza_cache(self):
        caminho = renderizar_pagina(self.prova, 1)

        self.assertTrue(caminho.exists())
        self.assertGreater(caminho.stat().st_size, 0)

        modificado = caminho.stat().st_mtime_ns
        caminho_repetido = renderizar_pagina(self.prova, 1)

        self.assertEqual(caminho_repetido, caminho)
        self.assertEqual(caminho_repetido.stat().st_mtime_ns, modificado)

    def test_pagina_fora_do_intervalo(self):
        with self.assertRaises(ValueError):
            renderizar_pagina(self.prova, 2)

    def test_prova_sem_pdf_nao_renderiza(self):
        self.prova.arquivo_pdf = None
        self.prova.save(update_fields=['arquivo_pdf'])

        self.assertEqual(total_paginas(self.prova), 0)

        with self.assertRaises(ValueError):
            renderizar_pagina(self.prova, 1)


class IndicePaginaProvaRealTestCase(TestCase):
    """Localiza a página da questão 35 no PDF real do ENEM 2025."""

    pdf_real = (
        Path(settings.BASE_DIR)
        / 'media'
        / 'provas'
        / '2025_PV_impresso_D1_CD1.pdf'
    )

    def setUp(self):
        if not self.pdf_real.exists():
            self.skipTest('PDF real do ENEM 2025 não está disponível.')

        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)

        self.configuracao = override_settings(MEDIA_ROOT=self.pasta.name)
        self.configuracao.enable()
        self.addCleanup(self.configuracao.disable)

        caminho_pdf = Path(self.pasta.name) / 'provas' / self.pdf_real.name
        caminho_pdf.parent.mkdir(parents=True, exist_ok=True)
        caminho_pdf.write_bytes(self.pdf_real.read_bytes())

        self.disciplina = Disciplina.objects.create(nome='Não classificada')
        self.prova = Prova.objects.create(
            nome='ENEM 2025',
            tipo='enem',
            ano=2025,
            status_importacao='processada',
            arquivo_pdf=f'provas/{self.pdf_real.name}',
        )
        self.questao = Questao.objects.create(
            prova=self.prova,
            disciplina=self.disciplina,
            numero=35,
            enunciado=(
                'Margot Robbie foi criticada por "não ser bonita o '
                'suficiente" para interpretar a Barbie.'
            ),
        )

    def test_indice_localiza_questao_35_na_pagina_15(self):
        indice = obter_indice_paginas(self.prova)

        self.assertEqual(indice.get('35'), 15)
        self.assertEqual(
            localizar_pagina_questao(self.prova, self.questao),
            15,
        )
