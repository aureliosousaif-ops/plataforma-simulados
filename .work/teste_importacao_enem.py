import os
from collections import Counter

os.environ.setdefault(
    'DJANGO_SETTINGS_MODULE',
    'config.settings'
)

import django

django.setup()

from django.db import transaction

from provas.importador import (
    extrair_gabarito_enem,
    extrair_texto_pdf,
    importar_questoes_no_banco,
    preparar_questoes_para_importacao,
    separar_questoes_enem,
    validar_questoes_com_gabarito,
)
from provas.models import Prova


with transaction.atomic():
    prova = Prova.objects.create(
        nome='TESTE ENEM TEMPORARIO',
        tipo='enem',
        ano=2024,
        arquivo_pdf='provas/2024_PV_impresso_D1_CD1.pdf',
        arquivo_gabarito='gabaritos/2024_GB_impresso_D1_CD1.pdf',
        ativa=False,
    )

    texto_prova = extrair_texto_pdf(prova.arquivo_pdf.path)
    texto_gabarito = extrair_texto_pdf(prova.arquivo_gabarito.path)
    questoes = separar_questoes_enem(texto_prova)
    gabarito = extrair_gabarito_enem(texto_gabarito)
    problemas = validar_questoes_com_gabarito(questoes, gabarito)

    if problemas:
        raise RuntimeError('\n'.join(problemas[:20]))

    preparadas = preparar_questoes_para_importacao(questoes, gabarito)
    quantidade = importar_questoes_no_banco(prova, preparadas, gabarito)
    corretas_preparadas = sum(
        alternativa.get('correta', False)
        for questao in preparadas
        for alternativa in questao['alternativas']
    )
    corretas_banco = sum(
        alternativa.correta
        for questao in prova.questoes.all()
        for alternativa in questao.alternativas.all()
    )

    texto_normalizado = texto_prova.upper()
    print({
        'questoes_extraidas': len(questoes),
        'gabarito_extraido': len(gabarito),
        'questoes_importadas': quantidade,
        'questoes_por_idioma': dict(
            Counter(
                questao.get('_idioma') or 'Não identificado'
                for questao in questoes
            )
        ),
        'alternativas_corretas_preparadas': corretas_preparadas,
        'alternativas_corretas_no_banco': corretas_banco,
        'idiomas_extraidos_questoes_01_05': [
            questao.get('_idioma')
            for questao in questoes
            if questao['numero'] in range(1, 6)
        ],
        'marcadores_QUESTION_no_pdf': texto_normalizado.count('QUESTION'),
        'marcadores_PREGUNTA_no_pdf': texto_normalizado.count('PREGUNTA'),
        'marcadores_QUESTAO_no_pdf': texto_normalizado.count('QUESTAO'),
        'disciplinas_importadas': sorted(
            set(prova.questoes.values_list('disciplina__nome', flat=True))
        ),
        'questoes_por_disciplina': dict(
            Counter(
                prova.questoes.values_list(
                    'disciplina__nome',
                    flat=True
                )
            )
        ),
    })

    transaction.set_rollback(True)
