"""Testes da navegação por categorias (1º dia / 2º dia) dos simulados."""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from provas.models import Disciplina, Prova, Questao
from usuarios.models import Perfil

from .models import Simulado


class OrganizacaoDiasSimuladoTestCase(TestCase):
    def setUp(self):
        self.lista_url = reverse('simulados:lista')

    def _criar_prova(
        self,
        nome,
        ano,
        dia=None,
        ativa=True,
        status='processada',
        arquivo_pdf='',
        primeiro_numero=1,
    ):
        prova = Prova.objects.create(
            nome=nome,
            tipo='enem',
            ano=ano,
            dia=dia,
            ativa=ativa,
            status_importacao=status,
            arquivo_pdf=arquivo_pdf,
        )

        disciplina, _ = Disciplina.objects.get_or_create(
            nome='Não classificada'
        )

        Questao.objects.create(
            prova=prova,
            disciplina=disciplina,
            numero=primeiro_numero,
            enunciado='Questão de teste',
        )

        return prova

    def test_pagina_inicial_mostra_as_duas_categorias(self):
        self._criar_prova('ENEM 2025 — 1º Dia', 2025, dia=1)
        self._criar_prova('ENEM 2024 — 2º Dia', 2024, dia=2)

        response = self.client.get(self.lista_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['categorias']), 2)
        self.assertContains(response, '1º Dia')
        self.assertContains(response, '2º Dia')
        self.assertContains(
            response,
            'Linguagens, Códigos e Ciências Humanas.',
        )
        self.assertContains(
            response,
            'Ciências da Natureza e Matemática.',
        )
        # Os anos das provas disponíveis aparecem no card da categoria.
        self.assertContains(response, 'ENEM 2025')
        self.assertContains(response, 'ENEM 2024')
        self.assertContains(response, '?dia=1')
        self.assertContains(response, '?dia=2')

    def test_filtro_exibe_apenas_o_dia_em_ordem_decrescente_de_ano(self):
        self._criar_prova('ENEM 2022 — 1º Dia', 2022, dia=1)
        self._criar_prova('ENEM 2024 — 1º Dia', 2024, dia=1)
        self._criar_prova('ENEM 2025 — 1º Dia', 2025, dia=1)
        self._criar_prova('ENEM 2023 — 2º Dia', 2023, dia=2)

        response = self.client.get(self.lista_url, {'dia': '1'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [prova.ano for prova in response.context['provas']],
            [2025, 2024, 2022],
        )
        self.assertEqual(
            response.context['dia_selecionado'],
            1,
        )
        self.assertContains(response, 'ENEM 2025 — 1º Dia')
        self.assertNotContains(response, 'ENEM 2023 — 2º Dia')

    def test_prova_antiga_sem_dia_e_classificada_pelos_dados_do_banco(self):
        # O nome não informa o dia; o PDF oficial e a numeração são
        # evidências mais confiáveis.
        self._criar_prova(
            'enem',
            2025,
            arquivo_pdf='provas/2025_PV_impresso_D1_CD1.pdf',
        )
        self._criar_prova(
            'enem 2',
            2024,
            arquivo_pdf='provas/2024_PV_impresso_D2_CD5.pdf',
        )

        d1 = self.client.get(self.lista_url, {'dia': '1'})
        d2 = self.client.get(self.lista_url, {'dia': '2'})

        self.assertEqual(len(d1.context['provas']), 1)
        self.assertEqual(d1.context['provas'][0].ano, 2025)
        self.assertEqual(len(d2.context['provas']), 1)
        self.assertEqual(d2.context['provas'][0].ano, 2024)

    def test_indicador_de_prova_disponivel_e_indisponivel(self):
        disponivel = self._criar_prova(
            'ENEM 2025 — 1º Dia',
            2025,
            dia=1,
        )
        pendente = self._criar_prova(
            'ENEM 2024 — 1º Dia',
            2024,
            dia=1,
            status='pendente',
        )
        self._criar_prova(
            'ENEM 2023 — 1º Dia (oculta)',
            2023,
            dia=1,
            ativa=False,
        )

        response = self.client.get(self.lista_url, {'dia': '1'})

        self.assertContains(response, 'Disponível')
        self.assertContains(response, 'Indisponível')
        self.assertContains(response, 'Importação pendente')
        # Provas ocultas continuam invisíveis para o aluno.
        self.assertNotContains(response, 'ENEM 2023 — 1º Dia (oculta)')
        self.assertContains(
            response,
            reverse('simulados:iniciar', args=[disponivel.id]),
        )
        self.assertNotContains(
            response,
            reverse('simulados:iniciar', args=[pendente.id]),
        )

    def test_navegacao_volta_para_selecao_e_troca_de_dia(self):
        self._criar_prova('ENEM 2025 — 1º Dia', 2025, dia=1)
        self._criar_prova('ENEM 2025 — 2º Dia', 2025, dia=2)

        response = self.client.get(self.lista_url, {'dia': '2'})

        self.assertContains(response, '← Todas as categorias')
        self.assertContains(response, self.lista_url)
        self.assertContains(response, '?dia=1')
        self.assertContains(response, '?dia=2')

    def test_filtro_invalido_volta_para_as_categorias(self):
        response = self.client.get(self.lista_url, {'dia': 'inexistente'})

        self.assertIsNone(response.context['dia_selecionado'])
        self.assertEqual(len(response.context['categorias']), 2)

    def test_iniciar_e_historico_continuam_funcionando(self):
        usuario = User.objects.create_user(
            username='aluno-dias',
            password='SenhaTeste123!',
        )
        Perfil.objects.get_or_create(usuario=usuario)
        self.client.login(
            username='aluno-dias',
            password='SenhaTeste123!',
        )

        prova = self._criar_prova('ENEM 2025 — 2º Dia', 2025, dia=2)
        historico = Simulado.objects.create(
            usuario=usuario,
            prova=prova,
            status='finalizado',
            acertos=42,
            erros=48,
            percentual=46.67,
        )

        response = self.client.post(
            reverse('simulados:iniciar', args=[prova.id]),
        )

        self.assertEqual(response.status_code, 302)

        novo_simulado = Simulado.objects.exclude(pk=historico.pk).get()
        self.assertEqual(
            response.url,
            reverse(
                'simulados:responder',
                kwargs={'simulado_id': novo_simulado.id},
            ),
        )
        self.assertTrue(
            Simulado.objects.filter(
                pk=historico.pk,
                status='finalizado',
                percentual=46.67,
            ).exists()
        )
