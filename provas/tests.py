from django.db import IntegrityError, transaction
from django.test import TestCase

from .importador import (
    detectar_idioma_secao,
    extrair_gabarito_enem,
    importar_questoes_no_banco,
    preparar_questoes,
    separar_questoes_enem,
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
