"""Auditoria somente leitura do fluxo importador -> simulado.

Usa um banco SQLite temporario fora do projeto. Nao toca em db.sqlite3
nem em DATABASE_URL.
"""

import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
os.environ['SECRET_KEY'] = 'audit-only-not-a-real-secret'
os.environ['DEBUG'] = 'True'
os.environ.pop('DATABASE_URL', None)

import django
from django.conf import settings

TEMP_DB = Path(tempfile.gettempdir()) / 'examix_audit_integracao.sqlite3'
if TEMP_DB.exists():
    TEMP_DB.unlink()
settings.DATABASES['default']['NAME'] = str(TEMP_DB)
settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ['testserver']

django.setup()

from django.core.management import call_command
from django.test import Client
from django.urls import reverse

call_command('migrate', verbosity=0, interactive=False)

from django.contrib.auth.models import User
from provas.importador import (
    extrair_gabarito_enem,
    importar_questoes_no_banco,
    preparar_questoes_para_importacao,
    separar_questoes_enem,
    validar_estrutura_questoes,
    validar_questoes_com_gabarito,
)
from provas.models import Prova, Questao
from simulados.models import Simulado
from usuarios.models import Perfil


def bloco(numero, idioma=''):
    linhas = []
    if idioma:
        linhas.append(f'Questoes de 01 a 05 (opcao {idioma})')
    linhas.extend([
        f'QUESTAO {numero:02d}',
        f'Enunciado da questao {numero}.',
        'A', 'Alternativa A.',
        'B', 'Alternativa B.',
        'C', 'Alternativa C.',
        'D', 'Alternativa D.',
        'E', 'Alternativa E.',
    ])
    return '\n'.join(linhas)


texto = []
texto.extend(bloco(n, 'ingles') for n in range(1, 6))
texto.extend(bloco(n, 'espanhol') for n in range(1, 6))
texto.extend(bloco(n) for n in range(6, 91))
texto = '\n'.join(texto)

gabarito = {}
for n in range(1, 6):
    gabarito[('Inglês', n)] = 'A'
    gabarito[('Espanhol', n)] = 'B'
for n in range(6, 91):
    gabarito[n] = 'C'

questoes = separar_questoes_enem(texto)
preparadas = preparar_questoes_para_importacao(questoes, gabarito)

print({
    'questoes_extraidas': len(questoes),
    'gabarito_entradas': len(gabarito),
    'questoes_preparadas': len(preparadas),
    'alternativas_corretas_preparadas': sum(
        alt['correta'] for q in preparadas for alt in q['alternativas']
    ),
    'validacao_gabarito': validar_questoes_com_gabarito(questoes, gabarito),
    'validacao_estrutura': validar_estrutura_questoes(questoes, gabarito),
})

usuario = User.objects.create_user('audit_aluno', password='SenhaTeste123!')
Perfil.objects.get_or_create(usuario=usuario)
prova = Prova.objects.create(
    nome='ENEM sintetico',
    tipo='enem',
    ano=2024,
    status_importacao='processada',
    ativa=True,
)
quantidade = importar_questoes_no_banco(prova, preparadas, gabarito)
print({
    'questoes_importadas': quantidade,
    'questoes_no_banco': Questao.objects.filter(prova=prova).count(),
    'corretas_no_banco': sum(
        alt.correta
        for q in prova.questoes.all()
        for alt in q.alternativas.all()
    ),
    'disciplinas': sorted(
        set(prova.questoes.values_list('disciplina__nome', flat=True))
    ),
    'variantes_1_a_5': list(
        prova.questoes.filter(numero__lte=5)
        .order_by('numero', 'idioma')
        .values_list('numero', 'idioma')
    ),
})

client = Client()
client.force_login(usuario)
resposta_inicio = client.post(
    reverse('simulados:iniciar', args=[prova.id])
)
simulado = Simulado.objects.get(usuario=usuario, prova=prova)
print({
    'iniciar_status_http': resposta_inicio.status_code,
    'respostas_criadas_no_simulado': simulado.respostas.count(),
    'questoes_reais_esperadas_enem': 90,
    'respostas_por_idioma': {
        idioma: simulado.respostas.filter(
            questao__idioma=idioma
        ).count()
        for idioma in [None, 'Inglês', 'Espanhol']
    },
})

# Responde 90 questoes (uma variante de cada numero), deixando a variante
# duplicada de lingua estrangeira em branco, como faria um aluno real.
respondidas = 0
for numero in range(1, 91):
    resposta = (
        simulado.respostas
        .filter(questao__numero=numero)
        .order_by('questao__idioma')
        .first()
    )
    correta = resposta.questao.alternativas.get(correta=True)
    resposta.alternativa = correta
    resposta.respondida = True
    resposta.correta = True
    resposta.save(update_fields=['alternativa', 'respondida', 'correta'])
    respondidas += 1

client.post(reverse('simulados:finalizar', args=[simulado.id]))
simulado.refresh_from_db()
print({
    'respostas_marcadas': respondidas,
    'total_respostas_simulado': simulado.respostas.count(),
    'acertos': simulado.acertos,
    'erros': simulado.erros,
    'percentual': str(simulado.percentual),
    'nao_respondidas': simulado.respostas.filter(respondida=False).count(),
})

from django.db import connections

connections.close_all()
TEMP_DB.unlink(missing_ok=True)
