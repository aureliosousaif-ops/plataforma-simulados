from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('simulados', '0001_initial'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='respostasimulado',
            options={
                'ordering': ['questao__numero', 'questao__idioma'],
            },
        ),
    ]
