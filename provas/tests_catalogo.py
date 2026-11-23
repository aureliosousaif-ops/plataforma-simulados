"""
Testes do catálogo oficial do ENEM e do comando de importação em lote.
"""

import json
import tempfile
from pathlib import Path

from django.contrib import admin
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase
from django.urls import reverse

from provas import catalogo_enem
from provas.importador import extrair_gabarito_enem
from provas.management.commands.importar_catalogo_enem import (
    montar_gabarito_digital,
    montar_questoes_digital,
    numeros_anulados,
    validar_cobertura,
    validar_variantes_idioma,
)
from provas.models import (
    ImportacaoItem,
    ImportacaoLote,
    Prova,
)


def _questao(numero, idioma=None):
    return {
        'numero': numero,
        'texto': f'Enunciado {numero}',
        'alternativas': [],
        '_idioma': idioma,
    }


class CatalogoIntegridadeTestCase(TestCase):
    """Valida a estrutura declarativa do catálogo."""

    def test_totais_do_catalogo(self):
        self.assertEqual(len(catalogo_enem.CATALOGO), 96)

        resumo = catalogo_enem.resumo()
        self.assertEqual(resumo['importaveis'], 72)
        self.assertEqual(resumo['acessibilidade'], 24)
        self.assertEqual(resumo['regular']['d1'], 36)
        self.assertEqual(resumo['regular']['d2'], 36)
        self.assertEqual(resumo['digital']['d1'], 12)
        self.assertEqual(resumo['digital']['d2'], 12)

    def test_chaves_sao_unicas(self):
        chaves = [prova.chave for prova in catalogo_enem.CATALOGO]
        self.assertEqual(len(chaves), len(set(chaves)))

    def test_cadernos_regulares_por_ano(self):
        for ano in catalogo_enem.ANOS_REGULARES:
            provas = catalogo_enem.filtrar(
                ano=ano,
                modalidade='regular',
            )
            self.assertEqual(len(provas), 12)

            self.assertEqual(
                {prova.caderno for prova in provas},
                set(range(1, 13)),
            )

            for dia in (1, 2):
                cadernos = {
                    prova.caderno
                    for prova in provas
                    if prova.dia == dia
                }
                esperados = (
                    {1, 2, 3, 4, 9, 10}
                    if dia == 1
                    else {5, 6, 7, 8, 11, 12}
                )
                self.assertEqual(cadernos, esperados)

    def test_digital_somente_nos_anos_com_arquivos(self):
        provas = catalogo_enem.filtrar(modalidade='digital')
        self.assertEqual(len(provas), 24)
        self.assertEqual(
            {prova.ano for prova in provas},
            {2020, 2021, 2022},
        )

    def test_nenhuma_prova_de_reaplicacao_ou_ppl(self):
        for prova in catalogo_enem.CATALOGO:
            texto = (prova.url_prova + prova.url_gabarito).lower()
            self.assertNotIn('ppl', texto)
            self.assertNotIn('re aplica', texto)
            self.assertNotIn('_d3', texto)

    def test_provas_importaveis_tem_links_e_quantidade(self):
        for prova in catalogo_enem.filtrar(apenas_importaveis=True):
            self.assertTrue(prova.url_prova.startswith('https://'))
            self.assertTrue(prova.url_gabarito.startswith('https://'))
            self.assertEqual(prova.quantidade_questoes, 90)
            self.assertTrue(prova.importar_questoes)

    def test_acessibilidade_fica_sem_questoes(self):
        provas = catalogo_enem.filtrar(apenas_importaveis=False)
        acessiveis = [
            prova for prova in provas
            if prova.acessibilidade != 'padrao'
        ]

        self.assertEqual(len(acessiveis), 24)

        for prova in acessiveis:
            self.assertFalse(prova.importar_questoes)
            self.assertIsNone(prova.quantidade_questoes)

    def test_cores_mudam_a_partir_de_2024(self):
        self.assertEqual(
            catalogo_enem.obter(
                'enem-2023-regular-d1-cd4'
            ).cor,
            'Rosa',
        )
        self.assertEqual(
            catalogo_enem.obter(
                'enem-2024-regular-d1-cd4'
            ).cor,
            'Verde',
        )
        self.assertEqual(
            catalogo_enem.obter(
                'enem-2021-regular-d1-cd10'
            ).cor,
            'Verde',
        )
        self.assertEqual(
            catalogo_enem.obter(
                'enem-2025-regular-d1-cd10'
            ).cor,
            'Roxo',
        )

    def test_digital_primeiro_dia_tem_dois_idiomas(self):
        prova = catalogo_enem.obter('enem-2022-digital-d1-cd1')

        self.assertTrue(prova.e_digital_dia_1)
        self.assertTrue(prova.url_prova_espanhol)
        self.assertTrue(prova.url_gabarito_espanhol)

        idiomas = {par['idioma'] for par in prova.arquivos}
        self.assertEqual(idiomas, {'Inglês', 'Espanhol'})

    def test_digital_segundo_dia_nao_tem_idioma(self):
        prova = catalogo_enem.obter('enem-2022-digital-d2-cd5')

        self.assertFalse(prova.e_digital_dia_1)
        self.assertEqual(prova.url_prova_espanhol, '')
        self.assertEqual(len(prova.arquivos), 1)

    def test_filtros_combinados(self):
        provas = catalogo_enem.filtrar(
            ano=[2024, 2025],
            modalidade='regular',
            dia=2,
            acessibilidade='padrao',
        )

        self.assertEqual(len(provas), 8)
        self.assertTrue(all(prova.dia == 2 for prova in provas))
        self.assertTrue(all(prova.ano in (2024, 2025) for prova in provas))


class MergeDigitalTestCase(TestCase):
    """Valida a agregação dos dois idiomas do ENEM Digital."""

    def test_monta_95_questoes_com_dois_idiomas(self):
        ingles = [_questao(numero) for numero in range(1, 91)]
        espanhol = [_questao(numero) for numero in range(1, 91)]

        questoes = montar_questoes_digital(ingles, espanhol)

        self.assertEqual(len(questoes), 95)
        self.assertEqual(
            len([q for q in questoes if q['numero'] == 1]),
            2,
        )

        idiomas = {
            q['_idioma']
            for q in questoes
            if q['numero'] in range(1, 6)
        }
        self.assertEqual(idiomas, {'Inglês', 'Espanhol'})

        compartilhadas = [
            q for q in questoes if q['numero'] > 5
        ]
        self.assertEqual(len(compartilhadas), 85)
        self.assertTrue(
            all(q['_idioma'] is None for q in compartilhadas)
        )

    def test_gabarito_respeita_o_idioma(self):
        gabarito_ingles = {numero: 'A' for numero in range(1, 91)}
        gabarito_espanhol = {numero: 'B' for numero in range(1, 91)}

        gabarito, anuladas = montar_gabarito_digital(
            gabarito_ingles,
            gabarito_espanhol,
        )

        self.assertEqual(gabarito[('Inglês', 1)], 'A')
        self.assertEqual(gabarito[('Espanhol', 1)], 'B')
        self.assertEqual(gabarito[('Inglês', 5)], 'A')
        self.assertEqual(gabarito[('Espanhol', 5)], 'B')
        self.assertEqual(gabarito[6], 'A')
        self.assertEqual(gabarito[90], 'A')
        self.assertEqual(anuladas, set())

    def test_gabarito_com_chaves_de_idioma(self):
        gabarito_ingles = {
            **{numero: 'C' for numero in range(1, 91)},
            ('Inglês', 1): 'D',
        }
        gabarito_espanhol = {
            **{numero: 'E' for numero in range(1, 91)},
            ('Espanhol', 2): 'A',
        }

        gabarito, _ = montar_gabarito_digital(
            gabarito_ingles,
            gabarito_espanhol,
        )

        self.assertEqual(gabarito[('Inglês', 1)], 'D')
        self.assertEqual(gabarito[('Espanhol', 2)], 'A')
        self.assertEqual(gabarito[('Inglês', 3)], 'C')
        self.assertEqual(gabarito[('Espanhol', 3)], 'E')

    def test_anuladas_dos_dois_idiomas(self):
        _, anuladas = montar_gabarito_digital(
            {numero: 'A' for numero in range(1, 91)},
            {numero: 'B' for numero in range(1, 91)},
            {42},
            {43, ('Espanhol', 4)},
        )

        self.assertEqual(numeros_anulados(anuladas), {4, 42, 43})

    def test_cobertura_bloqueia_prova_incompleta(self):
        questoes = [
            _questao(numero)
            for numero in range(1, 91)
            if numero != 42
        ]

        self.assertEqual(validar_cobertura(questoes), [42])

        self.assertEqual(
            validar_cobertura(questoes, anuladas={42}),
            [],
        )

    def test_cobertura_do_segundo_dia_usa_faixa_91_180(self):
        questoes = [
            _questao(numero)
            for numero in range(91, 181)
            if numero != 115
        ]

        self.assertEqual(
            validar_cobertura(questoes, anuladas={115}, inicio=91),
            [],
        )

        ausentes = validar_cobertura(
            [_questao(numero) for numero in range(1, 91)],
            inicio=91,
        )
        self.assertEqual(ausentes[:3], [91, 92, 93])
        self.assertEqual(len(ausentes), 90)

    def test_variantes_de_idioma_ausentes_sao_detectadas(self):
        # Só uma variante (Inglês) das questões 1–5: a cobertura por
        # número não detecta, mas a por idioma sim.
        questoes = [
            _questao(numero, idioma=idioma)
            for idioma in ('Inglês', 'Espanhol')
            for numero in range(1, 6)
        ] + [_questao(numero) for numero in range(6, 91)]

        self.assertEqual(validar_variantes_idioma(questoes), [])

        sem_espanhol = [
            questao
            for questao in questoes
            if questao.get('_idioma') != 'Espanhol'
        ]
        ausentes = validar_variantes_idioma(sem_espanhol)
        self.assertEqual(
            ausentes,
            [f'Espanhol: {numero}' for numero in range(1, 6)],
        )


class GabaritoSeparadoPorIdiomaTestCase(TestCase):
    """Gabaritos separados por idioma do ENEM Digital 1º dia."""

    def test_gabarito_sem_cabecalho_usa_idioma_padrao(self):
        # O gabarito em Espanhol do digital não tem cabeçalho de
        # seção: sem o idioma informado, as questões 1–5 seriam
        # rotuladas como Inglês pelo fallback do formato bilíngue.
        texto = '\n'.join([
            'Azul',
            'QUESTÃO GABARITO',
            '46 D',
            '47 E',
        ])

        self.assertEqual(
            extrair_gabarito_enem(texto, idioma_padrao='Espanhol'),
            {46: 'D', 47: 'E'},
        )

    def test_gabarito_espanhol_do_digital_chaveia_o_idioma(self):
        texto = '\n'.join([
            'QUESTÃO GABARITO',
            '1 E',
            '2 D',
            '3 C',
            '4 A',
            '5 A',
        ])

        gabarito = extrair_gabarito_enem(
            texto,
            idioma_padrao='Espanhol',
        )
        self.assertEqual(
            gabarito,
            {
                ('Espanhol', 1): 'E',
                ('Espanhol', 2): 'D',
                ('Espanhol', 3): 'C',
                ('Espanhol', 4): 'A',
                ('Espanhol', 5): 'A',
            },
        )

    def test_flujo_digital_d1_completa_as_duas_variantes(self):
        ingles = extrair_gabarito_enem(
            '\n'.join([
                'QUESTÃO GABARITO',
                '1 A',
                '2 B',
                '3 C',
                '4 D',
                '5 E',
                '6 A',
            ]),
            idioma_padrao='Inglês',
        )
        espanhol = extrair_gabarito_enem(
            '\n'.join([
                'QUESTÃO GABARITO',
                '1 E',
                '2 D',
                '3 C',
                '4 B',
                '5 A',
            ]),
            idioma_padrao='Espanhol',
        )

        gabarito, _ = montar_gabarito_digital(ingles, espanhol)

        self.assertEqual(gabarito[('Inglês', 1)], 'A')
        self.assertEqual(gabarito[('Espanhol', 1)], 'E')
        self.assertEqual(gabarito[('Espanhol', 5)], 'A')
        self.assertEqual(gabarito[6], 'A')


class ModeloCatalogoTestCase(TestCase):

    def test_propriedades_de_apresentacao(self):
        prova = Prova(
            nome='ENEM 2025 - Regular - 1º dia',
            tipo='enem',
            ano=2025,
            dia=1,
            caderno=1,
            cor_caderno='Azul',
            modalidade='regular',
            acessibilidade='padrao',
            origem='catalogo_oficial',
        )

        self.assertTrue(
            prova.area_conhecimento.startswith('Linguagens')
        )
        self.assertEqual(prova.dia_display, '1º dia')
        self.assertEqual(prova.modalidade_display, 'Regular')
        self.assertEqual(
            prova.caderno_display,
            ' (Caderno 1, Azul)',
        )

    def test_chave_oficial_unica(self):
        Prova.objects.create(
            nome='Prova A',
            tipo='enem',
            ano=2025,
            chave_oficial='enem-2025-regular-d1-cd1',
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Prova.objects.create(
                    nome='Prova B',
                    tipo='enem',
                    ano=2025,
                    chave_oficial='enem-2025-regular-d1-cd1',
                )


class ComandoCatalogoTestCase(TestCase):

    def setUp(self):
        super().setUp()

        # Relatórios da suíte vão para pasta temporária: o comando
        # grava em outputs/relatorios quando --relatorio não é
        # informado, e isso poluiria os relatórios reais.
        self._temporario = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporario.cleanup)

    def _executar(self, *argumentos):
        from io import StringIO

        # Sem --relatorio explícito, o relatório da execução de teste
        # é redirecionado para a pasta temporária do teste.
        if '--relatorio' not in argumentos:
            argumentos = argumentos + (
                '--relatorio',
                str(Path(self._temporario.name) / 'relatorio.json'),
            )

        saida = StringIO()

        saida = StringIO()
        call_command(
            'importar_catalogo_enem',
            *argumentos,
            stdout=saida,
            stderr=saida,
        )
        return saida.getvalue()

    def test_dry_run_nao_altera_o_banco(self):
        antes = Prova.objects.count()

        saida = self._executar(
            '--ano', '2020',
            '--modalidade', 'regular',
            '--dry-run',
        )

        self.assertIn('Planejamento', saida)
        self.assertEqual(Prova.objects.count(), antes)
        self.assertEqual(ImportacaoLote.objects.count(), 0)
        self.assertEqual(ImportacaoItem.objects.count(), 0)

    def test_cadastro_em_lote_e_idempotente(self):
        self._executar(
            '--ano', '2020',
            '--modalidade', 'regular',
            '--somente-cadastrar',
        )

        self.assertEqual(Prova.objects.count(), 12)
        self.assertEqual(
            Prova.objects.filter(origem='catalogo_oficial').count(),
            12,
        )

        prova = Prova.objects.get(
            chave_oficial='enem-2020-regular-d1-cd1'
        )
        self.assertEqual(prova.ano, 2020)
        self.assertEqual(prova.dia, 1)
        self.assertEqual(prova.caderno, 1)
        self.assertEqual(prova.cor_caderno, 'Azul')
        self.assertEqual(prova.modalidade, 'regular')
        self.assertEqual(prova.quantidade_questoes, 90)
        self.assertEqual(prova.status_importacao, 'pendente')
        self.assertTrue(prova.url_prova.endswith('2020_PV_impresso_D1_CD1.pdf'))
        self.assertTrue(
            prova.url_gabarito.endswith('2020_GB_impresso_D1_CD1.pdf')
        )
        self.assertEqual(prova.questoes.count(), 0)

        self._executar(
            '--ano', '2020',
            '--modalidade', 'regular',
            '--somente-cadastrar',
        )

        self.assertEqual(Prova.objects.count(), 12)

    def test_nao_sobrescreve_prova_manual(self):
        manual = Prova.objects.create(
            nome='Minha prova manual',
            tipo='enem',
            ano=2020,
            descricao='Cadastrada à mão',
            origem='manual',
        )

        self._executar(
            '--ano', '2020',
            '--modalidade', 'regular',
            '--somente-cadastrar',
        )

        manual.refresh_from_db()
        self.assertEqual(manual.nome, 'Minha prova manual')
        self.assertEqual(manual.descricao, 'Cadastrada à mão')
        self.assertIsNone(manual.chave_oficial)
        self.assertEqual(Prova.objects.count(), 13)

    def test_recusa_sobrescrever_chave_manual(self):
        Prova.objects.create(
            nome='Prova manual com chave',
            tipo='enem',
            ano=2020,
            chave_oficial='enem-2020-regular-d1-cd1',
            origem='manual',
        )

        self._executar(
            '--ano', '2020',
            '--modalidade', 'regular',
            '--dia', '1',
            '--caderno', '1',
            '--somente-cadastrar',
        )

        item = ImportacaoItem.objects.get(
            chave_oficial='enem-2020-regular-d1-cd1'
        )
        self.assertEqual(item.status, 'erro')
        self.assertIn('manual', item.mensagem)

        prova = Prova.objects.get(
            chave_oficial='enem-2020-regular-d1-cd1'
        )
        self.assertEqual(prova.nome, 'Prova manual com chave')

    def test_acessibilidade_apenas_cadastra(self):
        self._executar(
            '--ano', '2023',
            '--modalidade', 'regular',
            '--acessibilidade', 'braile_ledor',
        )

        provas = Prova.objects.filter(
            origem='catalogo_oficial'
        )

        self.assertEqual(provas.count(), 2)
        self.assertTrue(
            all(prova.quantidade_questoes is None for prova in provas)
        )
        self.assertTrue(
            all(prova.status_importacao == 'pendente' for prova in provas)
        )

    def test_retoma_itens_com_erro(self):
        self._executar(
            '--ano', '2020',
            '--modalidade', 'regular',
            '--somente-cadastrar',
        )

        item = ImportacaoItem.objects.get(
            chave_oficial='enem-2020-regular-d1-cd3'
        )
        item.status = 'erro'
        item.mensagem = 'falha simulada'
        item.save(update_fields=['status', 'mensagem'])

        self._executar(
            '--ano', '2020',
            '--modalidade', 'regular',
            '--somente-cadastrar',
            '--retomar',
        )

        item.refresh_from_db()
        self.assertEqual(item.status, 'cadastrado')
        self.assertEqual(item.prova.chave_oficial, item.chave_oficial)

    def test_limite_e_relatorio(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / 'relatorio.json'

            self._executar(
                '--ano', '2021',
                '--modalidade', 'regular',
                '--somente-cadastrar',
                '--limite', '3',
                '--relatorio', str(caminho),
            )

            self.assertEqual(Prova.objects.count(), 3)
            self.assertTrue(caminho.exists())

            dados = json.loads(caminho.read_text(encoding='utf-8'))
            self.assertEqual(dados['total'], 3)
            self.assertEqual(dados['cadastrados'], 3)
            self.assertEqual(len(dados['itens']), 3)
            self.assertIn('duracao_s', dados)

    def test_lote_registra_resumo(self):
        self._executar(
            '--ano', '2022',
            '--modalidade', 'digital',
            '--somente-cadastrar',
        )

        lote = ImportacaoLote.objects.latest('criado_em')
        self.assertEqual(lote.status, 'concluido')
        self.assertEqual(lote.resumo['total'], 8)
        self.assertEqual(lote.resumo['cadastrados'], 8)
        self.assertEqual(lote.itens.count(), 8)

    def test_filtro_apenas_importaveis(self):
        self._executar(
            '--ano', '2024',
            '--modalidade', 'regular',
            '--apenas-importaveis',
            '--somente-cadastrar',
        )

        self.assertEqual(Prova.objects.count(), 8)


class AdminCatalogoTestCase(TestCase):
    """Consulta dos dados do catálogo no Django Admin."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth import get_user_model

        cls.admin = get_user_model().objects.create_superuser(
            username='admin-catalogo',
            password='teste-admin-123',
            email='admin@exemplo.com',
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def _prova_do_catalogo(self):
        return Prova.objects.create(
            nome='ENEM 2020 Regular 1º dia CD1',
            tipo='enem',
            ano=2020,
            chave_oficial='enem-2020-regular-d1-cd1',
            modalidade='regular',
            dia=1,
            caderno=1,
            acessibilidade='padrao',
            origem='catalogo_oficial',
            status_importacao='pendente',
        )

    def test_prova_do_catalogo_e_listada_com_campos(self):
        prova = self._prova_do_catalogo()

        resposta = self.client.get(
            reverse('admin:provas_prova_changelist')
        )

        self.assertEqual(resposta.status_code, 200)
        conteudo = resposta.content.decode('utf-8')
        self.assertIn(prova.chave_oficial, conteudo)
        self.assertIn('Catálogo oficial', conteudo)

    def test_prova_do_catalogo_e_somente_leitura_nos_campos_de_origem(self):
        prova = self._prova_do_catalogo()

        resposta = self.client.get(
            reverse('admin:provas_prova_change', args=[prova.id])
        )

        self.assertEqual(resposta.status_code, 200)
        conteudo = resposta.content.decode('utf-8')
        # Campos de origem aparecem como somente leitura.
        self.assertIn('chave_oficial', conteudo)
        self.assertIn('readonly', conteudo)

    def test_filtros_da_listagem_de_provas(self):
        self._prova_do_catalogo()
        Prova.objects.create(
            nome='Prova manual',
            tipo='enem',
            ano=2024,
            origem='manual',
        )

        for filtros in (
            {'ano__exact': '2020'},
            {'modalidade__exact': 'regular'},
            {'origem__exact': 'catalogo_oficial'},
            {'status_importacao__exact': 'pendente'},
            {'dia__exact': '1'},
        ):
            resposta = self.client.get(
                reverse('admin:provas_prova_changelist'),
                filtros,
            )

            self.assertEqual(resposta.status_code, 200)
            conteudo = resposta.content.decode('utf-8')
            self.assertIn('enem-2020-regular-d1-cd1', conteudo)

    def test_lote_e_listado_com_itens(self):
        lote = ImportacaoLote.objects.create(
            identificador='enem-catalogo-teste',
            ano=2020,
            modalidade='regular',
            status='concluido',
        )
        ImportacaoItem.objects.create(
            lote=lote,
            chave_oficial='enem-2020-regular-d1-cd1',
            status='erro',
            etapa='download',
            mensagem='Não foi possível baixar o PDF.',
        )

        resposta_lote = self.client.get(
            reverse('admin:provas_importacaolote_changelist')
        )
        self.assertEqual(resposta_lote.status_code, 200)
        self.assertIn('enem-catalogo-teste', resposta_lote.content.decode('utf-8'))

        resposta_item = self.client.get(
            reverse('admin:provas_importacaoitem_changelist'),
            {'status__exact': 'erro'},
        )
        self.assertEqual(resposta_item.status_code, 200)
        conteudo = resposta_item.content.decode('utf-8')
        self.assertIn('enem-2020-regular-d1-cd1', conteudo)
        self.assertIn('Não foi possível baixar o PDF.', conteudo)

    def test_item_de_erro_e_visivel_no_detalhe(self):
        item = ImportacaoItem.objects.create(
            chave_oficial='enem-2020-digital-d2-cd5',
            status='erro',
            etapa='download',
            mensagem='Não foi possível baixar o PDF.',
        )

        resposta = self.client.get(
            reverse('admin:provas_importacaoitem_change', args=[item.id])
        )

        self.assertEqual(resposta.status_code, 200)
        conteudo = resposta.content.decode('utf-8')
        self.assertIn('Não foi possível baixar o PDF.', conteudo)
        self.assertIn('Download', conteudo)

    def test_lote_e_item_nao_podem_ser_criados_pelo_admin(self):
        from provas.admin import ImportacaoItemAdmin, ImportacaoLoteAdmin

        self.assertFalse(
            ImportacaoLoteAdmin(
                ImportacaoLote, admin.site
            ).has_add_permission(request=RequestFactory().get('/'))
        )
        self.assertFalse(
            ImportacaoItemAdmin(
                ImportacaoItem, admin.site
            ).has_add_permission(request=RequestFactory().get('/'))
        )
