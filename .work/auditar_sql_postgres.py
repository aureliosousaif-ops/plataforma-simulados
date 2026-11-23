"""Gera o SQL do PostgreSQL para a migration 0005 sem abrir conexão."""

import os

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'audit_settings_pg')
django.setup()

from django.db import connections  # noqa: E402
from django.db.migrations.loader import MigrationLoader  # noqa: E402
from django.db.migrations.state import ProjectState  # noqa: E402

loader = MigrationLoader(None, ignore_no_migrations=True)

estado = ProjectState()
for chave in [
    ('provas', '0001_initial'),
    ('provas', '0002_prova_arquivo_gabarito_prova_data_processamento_and_more'),
    ('provas', '0003_questao_idioma'),
    ('provas', '0004_alter_questao_options'),
]:
    estado = loader.get_migration(*chave).mutate_state(estado)

migracao = loader.get_migration(
    'provas',
    '0005_imagemprova_imagemquestao_and_more',
)

conexao = connections['default']
print('backend:', conexao.vendor)

editor = conexao.schema_editor(collect_sql=True, atomic=False)
with editor:
    migracao.apply(estado, editor)

for comando in editor.collected_sql:
    print(comando)
    print(';')
