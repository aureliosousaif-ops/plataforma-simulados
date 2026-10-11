from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('provas', '0002_prova_arquivo_gabarito_prova_data_processamento_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='questao',
            name='idioma',
            field=models.CharField(
                blank=True,
                choices=[
                    ('Inglês', 'Inglês'),
                    ('Espanhol', 'Espanhol'),
                ],
                max_length=20,
                null=True,
            ),
        ),
        migrations.RemoveConstraint(
            model_name='questao',
            name='numero_unico_por_prova',
        ),
        migrations.AddConstraint(
            model_name='questao',
            constraint=models.UniqueConstraint(
                fields=('prova', 'numero', 'idioma'),
                name='numero_unico_por_prova_idioma',
            ),
        ),
        migrations.AddConstraint(
            model_name='questao',
            constraint=models.UniqueConstraint(
                condition=models.Q(('idioma__isnull', True)),
                fields=('prova', 'numero'),
                name='numero_unico_por_prova_sem_idioma',
            ),
        ),
    ]
