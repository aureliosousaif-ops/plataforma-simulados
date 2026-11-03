import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.db.models import Count, Q
from provas.models import Prova, Questao, Disciplina, Alternativa
nome = 'TESTE ENEM TEMPORARIO'
provas = Prova.objects.filter(nome=nome)
print({'provas_com_nome': provas.count(), 'ids': list(provas.values_list('id', flat=True))})
for prova in provas:
    print({'prova_id': prova.id, 'questoes': prova.questoes.count(), 'alternativas': Alternativa.objects.filter(questao__prova=prova).count(), 'corretas': Alternativa.objects.filter(questao__prova=prova, correta=True).count(), 'disciplinas': list(Disciplina.objects.filter(questoes__prova=prova).values_list('nome', flat=True).distinct())})
print({'disciplinas_teste': list(Disciplina.objects.filter(nome__in=['Inglês', 'Espanhol', 'Não classificada']).values_list('nome', flat=True))})
