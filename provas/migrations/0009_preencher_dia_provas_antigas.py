"""Preenche o dia das provas antigas que ficaram sem informação.

O campo ``Prova.dia`` já existe desde a migração 0008, mas somente as
provas vindas do catálogo oficial o preenchiam. Esta migração de dados
usa a mesma regra compartilhada em ``provas.dias`` para classificar as
provas manuais já cadastradas, sem tocar em enunciados, alternativas,
gabaritos, usuários, resultados ou em qualquer outro campo.
"""

from django.db import migrations

from provas.dias import inferir_dia


def preencher_dia(apps, schema_editor):
    Prova = apps.get_model('provas', 'Prova')
    Questao = apps.get_model('provas', 'Questao')

    # Lista as chaves antes de atualizar para evitar cursor aberto
    # sobre a mesma tabela que está sendo alterada (SQLite).
    ids = list(
        Prova.objects.filter(
            tipo='enem',
            dia__isnull=True,
        ).values_list('pk', flat=True)
    )

    for prova_id in ids:
        prova = Prova.objects.get(pk=prova_id)

        numeros = list(
            Questao.objects.filter(
                prova_id=prova_id,
            ).values_list('numero', flat=True)
        )

        dia = inferir_dia(prova, numeros)

        if dia in (1, 2):
            # Apenas o campo "dia" é alterado.
            Prova.objects.filter(pk=prova_id).update(dia=dia)


class Migration(migrations.Migration):

    dependencies = [
        ('provas', '0008_importacaolote_prova_acessibilidade_and_more'),
    ]

    operations = [
        # Reverso explícito como não-operação: desfazer a migração não
        # deve apagar uma informação válida do cadastro.
        migrations.RunPython(preencher_dia, migrations.RunPython.noop),
    ]
