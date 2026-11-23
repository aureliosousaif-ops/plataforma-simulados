import os
import re
import sys
import traceback
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

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


LETRAS_ESPERADAS = ['A', 'B', 'C', 'D', 'E']
ARTEFATO_IMPRESSAO = re.compile(
    r'ENEM\s*2024|\*?\d{6}[A-Z]{2}\d+\*?',
    re.IGNORECASE,
)


def validar_estrutura_questoes(questoes, prefixo=''):
    problemas = []
    validas = 0

    for questao in questoes:
        numero = questao.get('numero')
        alternativas = questao.get('alternativas', [])
        letras = [alternativa.get('letra') for alternativa in alternativas]

        if letras != LETRAS_ESPERADAS:
            problemas.append(
                f'{prefixo}Questão {numero}: letras encontradas {letras!r}; '
                f'esperado {LETRAS_ESPERADAS!r}.'
            )
            continue

        problemas_questao = []
        for alternativa in alternativas:
            texto = (alternativa.get('texto') or '').strip()
            letra = alternativa.get('letra')
            if not texto:
                problemas_questao.append(f'alternativa {letra} sem texto')
            if ARTEFATO_IMPRESSAO.search(texto):
                problemas_questao.append(
                    f'alternativa {letra} contém artefato de impressão'
                )

        corretas = [
            alternativa for alternativa in alternativas
            if alternativa.get('correta') is True
        ]
        if len(corretas) != 1:
            problemas_questao.append(
                f'{len(corretas)} alternativas marcadas como corretas'
            )

        if problemas_questao:
            problemas.append(
                f'{prefixo}Questão {numero}: ' + '; '.join(problemas_questao)
            )
        else:
            validas += 1

    return validas, problemas


def main():
    prova_id = None
    relatorio = {}
    erro = None

    try:
        with transaction.atomic():
            prova = Prova.objects.create(
                nome='TESTE ENEM TEMPORARIO',
                tipo='enem',
                ano=2024,
                arquivo_pdf='provas/2024_PV_impresso_D1_CD1.pdf',
                arquivo_gabarito='gabaritos/2024_GB_impresso_D1_CD1.pdf',
                ativa=False,
            )
            prova_id = prova.id

            texto_prova = extrair_texto_pdf(prova.arquivo_pdf.path)
            texto_gabarito = extrair_texto_pdf(prova.arquivo_gabarito.path)
            questoes = separar_questoes_enem(texto_prova)
            gabarito = extrair_gabarito_enem(texto_gabarito)

            problemas = validar_questoes_com_gabarito(questoes, gabarito)
            validas_extraidas, problemas_estrutura = validar_estrutura_questoes(
                [
                    {
                        **questao,
                        'alternativas': [
                            {
                                **alternativa,
                                'correta': alternativa.get('letra') == (
                                    gabarito.get(
                                        (questao.get('_idioma'), questao['numero'])
                                    )
                                    if questao.get('_idioma')
                                    else gabarito.get(questao['numero'])
                                ),
                            }
                            for alternativa in questao['alternativas']
                        ],
                    }
                    for questao in questoes
                ],
                prefixo='Extração: ',
            )
            problemas.extend(problemas_estrutura)

            if len(questoes) != 95:
                problemas.append(
                    f'Quantidade de questões extraídas: {len(questoes)}; esperado 95.'
                )
            if len(gabarito) != 95:
                problemas.append(
                    f'Quantidade de respostas extraídas: {len(gabarito)}; esperado 95.'
                )

            if problemas:
                raise RuntimeError('\n'.join(problemas[:50]))

            preparadas = preparar_questoes_para_importacao(questoes, gabarito)
            quantidade = importar_questoes_no_banco(prova, preparadas, gabarito)
            questoes_banco = list(
                prova.questoes.prefetch_related('alternativas').all()
            )
            validas_banco, problemas_banco = validar_estrutura_questoes(
                [
                    {
                        'numero': questao.numero,
                        'alternativas': [
                            {
                                'letra': alternativa.letra,
                                'texto': alternativa.texto,
                                'correta': alternativa.correta,
                            }
                            for alternativa in questao.alternativas.all()
                        ],
                    }
                    for questao in questoes_banco
                ],
                prefixo='Banco temporário: ',
            )
            if problemas_banco:
                raise RuntimeError('\n'.join(problemas_banco[:50]))

            corretas_preparadas = sum(
                alternativa.get('correta', False)
                for questao in preparadas
                for alternativa in questao['alternativas']
            )
            corretas_banco = sum(
                alternativa.correta
                for questao in questoes_banco
                for alternativa in questao.alternativas.all()
            )

            relatorio = {
                'questoes_extraidas': len(questoes),
                'gabarito_extraido': len(gabarito),
                'questoes_importadas': quantidade,
                'questoes_com_5_alternativas_validas_extraidas': validas_extraidas,
                'questoes_com_5_alternativas_validas_banco': validas_banco,
                'problemas_encontrados': problemas,
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
                'disciplinas_importadas': sorted(
                    set(
                        questao.disciplina.nome
                        for questao in questoes_banco
                    )
                ),
                'questoes_por_disciplina': dict(
                    Counter(
                        questao.disciplina.nome
                        for questao in questoes_banco
                    )
                ),
            }

            print(relatorio)
            print('ROLLBACK_SOLICITADO: True')
            transaction.set_rollback(True)

    except Exception as exc:
        erro = exc
        print('IMPORTACAO_TESTE_ERRO: True')
        print(f'{type(exc).__name__}: {exc}')
        traceback.print_exc()

    rollback_confirmado = (
        prova_id is not None
        and not Prova.objects.filter(pk=prova_id).exists()
    )
    print({
        'prova_temporaria_id': prova_id,
        'rollback_confirmado': rollback_confirmado,
        'erro': type(erro).__name__ if erro else None,
    })

    if erro is not None:
        raise erro
    if not rollback_confirmado:
        raise RuntimeError('Rollback não confirmado para a prova temporária.')


if __name__ == '__main__':
    main()
