"""
Conta os registros principais do banco configurado no ambiente.

Uso:
    python scripts/contar_dados.py

Respeita DATABASE_URL e DEBUG, exatamente como o site.
Serve para conferir a migração local -> Render sem abrir o admin.
"""

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
os.chdir(RAIZ)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django  # noqa: E402

django.setup()

from django.contrib.auth.models import User  # noqa: E402

from provas.models import (  # noqa: E402
    Alternativa,
    Disciplina,
    ImagemProva,
    ImagemQuestao,
    Prova,
    Questao,
    QuestaoTextoBase,
    TextoBase,
)
from simulados.models import RespostaSimulado, Simulado  # noqa: E402


def main():
    banco = os.environ.get('DATABASE_URL')

    print('Banco:', 'DATABASE_URL (PostgreSQL)' if banco else 'SQLite local')
    print('DEBUG:', os.environ.get('DEBUG', 'False'))
    print()

    print('Usuarios........:', User.objects.count())
    print('Superusuarios...:', User.objects.filter(is_superuser=True).count())
    print('Disciplinas.....:', Disciplina.objects.count())
    print('Provas..........:', Prova.objects.count())
    print('Questoes........:', Questao.objects.count())
    print('Alternativas....:', Alternativa.objects.count())
    print('Imagens da prova:', ImagemProva.objects.count())
    print('Imagens de quest:', ImagemQuestao.objects.count())
    print('Textos-base.....:', TextoBase.objects.count())
    print('Vinculos texto..:', QuestaoTextoBase.objects.count())
    print('Simulados.......:', Simulado.objects.count())
    print('Respostas.......:', RespostaSimulado.objects.count())


if __name__ == '__main__':
    main()
