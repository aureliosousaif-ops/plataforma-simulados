from django.db import IntegrityError, transaction
from django.test import TestCase

from .importador import (
    _encontrar_marcadores_alternativas,
    detectar_idioma_secao,
    extrair_gabarito_enem,
    extrair_alternativas_generico,
    importar_questoes_no_banco,
    limpar_texto,
    limpar_texto_alternativa,
    preparar_questoes,
    separar_questoes_enem,
    validar_estrutura_questoes,
)
from .models import Disciplina, Prova, Questao


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
