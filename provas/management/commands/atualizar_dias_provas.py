"""Preenche o dia das provas que ainda não possuem essa informação.

Útil depois de carregar um dump antigo (``dados_producao.json``), pois
a migração de dados só roda uma vez e o dump não traz o campo ``dia``.

Uso:
    python manage.py atualizar_dias_provas
    python manage.py atualizar_dias_provas --dry-run
"""

from django.core.management.base import BaseCommand

from provas.dias import inferir_dia
from provas.models import Prova


class Command(BaseCommand):
    help = (
        'Identifica o dia (1º/2º) das provas antigas sem alterar '
        'enunciados, alternativas, gabaritos ou resultados.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostra o que seria alterado sem salvar no banco.',
        )

    def handle(self, *args, **options):
        seco = options['dry_run']

        provas = Prova.objects.filter(
            dia__isnull=True,
        ).order_by('id')

        preenchidas = 0
        sem_identificacao = []

        for prova in provas:
            numeros = list(
                prova.questoes.values_list('numero', flat=True)
            )

            dia = inferir_dia(prova, numeros)

            if dia not in (1, 2):
                sem_identificacao.append(prova)
                continue

            if not seco:
                # Atualização cirúrgica: nenhum outro campo é tocado.
                Prova.objects.filter(pk=prova.pk).update(dia=dia)

            preenchidas += 1

            self.stdout.write(
                f'{prova.id}: {prova.nome} ({prova.ano}) -> '
                f'{dia}º dia'
                + (' [simulação]' if seco else '')
            )

        if sem_identificacao:
            self.stdout.write(
                self.style.WARNING(
                    'Sem identificação automática (defina o dia no '
                    'cadastro administrativo): '
                    + ', '.join(
                        f'{prova.id}: {prova.nome}'
                        for prova in sem_identificacao
                    )
                )
            )

        if seco:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Simulação concluída: {preenchidas} prova(s) '
                    'seriam preenchidas. Nenhum dado foi alterado.'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Concluído: {preenchidas} prova(s) preenchidas.'
                )
            )
