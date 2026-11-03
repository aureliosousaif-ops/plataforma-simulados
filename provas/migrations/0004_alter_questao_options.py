from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('provas', '0003_questao_idioma'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='questao',
            options={
                'ordering': ['prova', 'numero', 'idioma'],
            },
        ),
    ]
