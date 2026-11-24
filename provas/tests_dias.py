"""Testes da organização das provas por dia (1º / 2º dia do ENEM)."""

from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from usuarios.models import Perfil

from .dias import inferir_dia, normalizar_dia
from .forms import ProvaForm
from .models import Disciplina, Prova, Questao


class InferenciaDiaTestCase(TestCase):
    """A regra mais confiável sempre vence o nome da prova."""

    def _criar_prova(self, **kwargs):
        dados = {
            'nome': 'enem',
            'tipo': 'enem',
            'ano': 2025,
            'status_importacao': 'processada',
        }
        dados.update(kwargs)
        return Prova.objects.create(**dados)

    def _criar_questoes(self, prova, numeros):
        disciplina, _ = Disciplina.objects.get_or_create(
            nome='Não classificada'
        )

        for numero in numeros:
            Questao.objects.create(
                prova=prova,
                disciplina=disciplina,
                numero=numero,
                enunciado=f'Questão {numero}',
            )

    def test_campo_do_banco_tem_prioridade_sobre_o_nome(self):
        prova = self._criar_prova(
            nome='ENEM 2025 — 1º Dia',
            dia=2,
        )

        self.assertEqual(inferir_dia(prova, [1, 2, 3]), 2)

    def test_chave_oficial_tem_prioridade_sobre_numeros_e_nome(self):
        prova = self._criar_prova(
            nome='ENEM 2025 — 1º Dia',
            chave_oficial='enem-2025-regular-d2-cd5',
        )

        self.assertEqual(inferir_dia(prova, list(range(1, 91))), 2)

    def test_nome_do_arquivo_oficial_identifica_o_dia(self):
        prova = self._criar_prova(
            arquivo_pdf='provas/2025_PV_impresso_D1_CD1.pdf',
        )

        self.assertEqual(inferir_dia(prova, []), 1)

    def test_faixa_de_questoes_identifica_o_segundo_dia(self):
        prova = self._criar_prova()

        self.assertEqual(
            inferir_dia(prova, list(range(91, 180))),
            2,
        )

    def test_faixa_de_questoes_identifica_o_primeiro_dia(self):
        prova = self._criar_prova()

        self.assertEqual(
            inferir_dia(prova, list(range(1, 91))),
            1,
        )

    def test_nome_e_usado_apenas_quando_nao_ha_dado_melhor(self):
        prova = self._criar_prova(
            nome='ENEM 2024 — 2º Dia',
        )

        self.assertEqual(inferir_dia(prova, []), 2)

    def test_sem_informacao_retorna_none(self):
        prova = self._criar_prova()

        self.assertIsNone(inferir_dia(prova, []))

    def test_normalizar_dia_aceita_aliases(self):
        self.assertEqual(normalizar_dia('1'), 1)
        self.assertEqual(normalizar_dia('d2'), 2)
        self.assertEqual(normalizar_dia('D1'), 1)
        self.assertIsNone(normalizar_dia('todas'))
        self.assertIsNone(normalizar_dia('qualquer'))


class ComandoAtualizarDiasTestCase(TestCase):
    def test_comando_preenche_apenas_provas_sem_dia(self):
        alvo = Prova.objects.create(
            nome='enem',
            tipo='enem',
            ano=2025,
            chave_oficial='enem-2025-regular-d2-cd5',
        )
        ja_classificada = Prova.objects.create(
            nome='ENEM 2025 — 1º Dia',
            tipo='enem',
            ano=2025,
            dia=1,
        )
        sem_pista = Prova.objects.create(
            nome='Prova sem identificação',
            tipo='enem',
            ano=2024,
        )

        saida = StringIO()
        call_command('atualizar_dias_provas', stdout=saida)

        alvo.refresh_from_db()
        ja_classificada.refresh_from_db()
        sem_pista.refresh_from_db()

        self.assertEqual(alvo.dia, 2)
        self.assertEqual(ja_classificada.dia, 1)
        self.assertIsNone(sem_pista.dia)
        self.assertIn('Sem identificação automática', saida.getvalue())

        # O comando é idempotente.
        call_command('atualizar_dias_provas', stdout=StringIO())
        alvo.refresh_from_db()
        self.assertEqual(alvo.dia, 2)

    def test_dry_run_nao_altera_o_banco(self):
        prova = Prova.objects.create(
            nome='enem',
            tipo='enem',
            ano=2025,
            arquivo_pdf='provas/2025_PV_impresso_D1_CD1.pdf',
        )

        saida = StringIO()
        call_command(
            'atualizar_dias_provas',
            '--dry-run',
            stdout=saida,
        )

        prova.refresh_from_db()
        self.assertIsNone(prova.dia)
        self.assertIn('Nenhum dado foi alterado', saida.getvalue())


class FormularioProvaDiaTestCase(TestCase):
    def _dados(self, **substituicoes):
        dados = {
            'nome': 'ENEM 2025',
            'tipo': 'enem',
            'ano': 2025,
            'dia': '',
            'descricao': '',
        }
        dados.update(substituicoes)
        return dados

    def test_formulario_cadastra_com_dia_escolhido(self):
        form = ProvaForm(data=self._dados(dia='2'))

        self.assertTrue(form.is_valid(), form.errors)
        prova = form.save()

        self.assertEqual(prova.dia, 2)

    def test_formulario_infere_dia_quando_nao_informado(self):
        form = ProvaForm(
            data=self._dados(
                nome='ENEM 2025 — 1º Dia',
                dia='',
            )
        )

        self.assertTrue(form.is_valid(), form.errors)
        prova = form.save()

        self.assertEqual(prova.dia, 1)

    def test_edicao_sem_dia_preserva_o_dia_cadastrado(self):
        prova = Prova.objects.create(
            nome='ENEM 2025',
            tipo='enem',
            ano=2025,
            dia=2,
        )

        form = ProvaForm(
            data=self._dados(dia=''),
            instance=prova,
        )

        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        prova.refresh_from_db()
        self.assertEqual(prova.dia, 2)

    def test_template_do_formulario_exibe_o_campo_dia(self):
        usuario = User.objects.create_user(
            username='dev-dias',
            password='SenhaTeste123!',
        )
        Perfil.objects.get_or_create(
            usuario=usuario,
            defaults={'tipo': 'desenvolvedor'},
        )
        perfil = usuario.perfil
        perfil.tipo = 'desenvolvedor'
        perfil.save()
        self.client.login(
            username='dev-dias',
            password='SenhaTeste123!',
        )

        response = self.client.get(reverse('provas:criar'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Dia da prova')
        self.assertContains(response, 'name="dia"')


class FiltroAdministrativoDiaTestCase(TestCase):
    def setUp(self):
        usuario = User.objects.create_user(
            username='dev-filtro',
            password='SenhaTeste123!',
        )
        Perfil.objects.get_or_create(
            usuario=usuario,
            defaults={'tipo': 'desenvolvedor'},
        )
        perfil = usuario.perfil
        perfil.tipo = 'desenvolvedor'
        perfil.save()
        self.client.login(
            username='dev-filtro',
            password='SenhaTeste123!',
        )

        self.d1_visivel = Prova.objects.create(
            nome='ENEM 2025 — 1º Dia',
            tipo='enem',
            ano=2025,
            dia=1,
        )
        self.d1_oculta = Prova.objects.create(
            nome='ENEM 2024 — 1º Dia',
            tipo='enem',
            ano=2024,
            dia=1,
            ativa=False,
        )
        self.d2_visivel = Prova.objects.create(
            nome='ENEM 2025 — 2º Dia',
            tipo='enem',
            ano=2025,
            dia=2,
        )

    def test_filtro_por_dia(self):
        response = self.client.get(
            reverse('provas:lista'),
            {'dia': '1'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(response.context['provas']),
            [self.d1_visivel, self.d1_oculta],
        )
        self.assertContains(response, '1º Dia')

    def test_filtro_por_dia_alias_d2(self):
        response = self.client.get(
            reverse('provas:lista'),
            {'dia': 'd2'},
        )

        self.assertEqual(
            list(response.context['provas']),
            [self.d2_visivel],
        )

    def test_filtros_de_dia_e_visibilidade_sao_combinados(self):
        response = self.client.get(
            reverse('provas:lista'),
            {'dia': '1', 'visibilidade': 'ocultas'},
        )

        self.assertEqual(
            list(response.context['provas']),
            [self.d1_oculta],
        )
        self.assertContains(response, '?visibilidade=visiveis&amp;dia=1')
        self.assertContains(response, '?dia=2&amp;visibilidade=ocultas')

    def test_sem_filtro_mostra_todas_as_provas(self):
        response = self.client.get(reverse('provas:lista'))

        self.assertEqual(
            response.context['provas'].count(),
            3,
        )
