import os
import sys
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

ALVOS = (8, 16, 66)


def log(*valores):
    print(*valores, flush=True)


def imprimir_rotulo(rotulo, texto):
    log(f'\n===== {rotulo} =====')
    log(texto)


def main():
    log('INICIO: carregando Django')

    import django
    django.setup()

    log('OK: Django carregado')

    from pypdf import PdfReader
    from provas.importador import (
        _encontrar_marcadores_alternativas,
        _expandir_alternativas_inline,
        encontrar_marcadores_questoes,
        extrair_alternativas_generico,
        limpar_conteudo_questao,
        limpar_texto,
    )
    from provas.models import Prova

    log('INICIO: procurando prova existente pelo FileField')
    prova = (
        Prova.objects
        .filter(arquivo_pdf__isnull=False)
        .exclude(arquivo_pdf='')
        .order_by('-id')
        .first()
    )

    if prova is None:
        log('NENHUMA prova com arquivo_pdf foi encontrada no banco.')
        return 2

    caminho_pdf = prova.arquivo_pdf.path
    log({
        'prova_id': prova.id,
        'nome': prova.nome,
        'pdf': caminho_pdf,
    })

    log('INICIO: lendo páginas do PDF com PdfReader')
    reader = PdfReader(caminho_pdf)
    paginas = []
    for indice, pagina in enumerate(reader.pages, start=1):
        texto_pagina = pagina.extract_text() or ''
        paginas.append(texto_pagina)
        log(f'pagina {indice}/{len(reader.pages)}: {len(texto_pagina)} caracteres')

    texto_bruto = '\n'.join(paginas)
    log(f'OK: texto bruto total com {len(texto_bruto)} caracteres')

    log('INICIO: limpando texto geral')
    texto_limpo = limpar_texto(texto_bruto)
    log(f'OK: texto limpo total com {len(texto_limpo)} caracteres')

    linhas_brutas = texto_bruto.splitlines()
    linhas_limpas = texto_limpo.splitlines()
    marcadores_brutos = encontrar_marcadores_questoes(texto_bruto)
    marcadores_limpos = encontrar_marcadores_questoes(texto_limpo)

    log({
        'marcadores_brutos': len(marcadores_brutos),
        'marcadores_limpos': len(marcadores_limpos),
        'alvos': ALVOS,
    })

    for numero in ALVOS:
        log(f'\nINICIO: processando questão {numero}')
        try:
            marcador_bruto = next(
                (item for item in marcadores_brutos if item['numero'] == numero),
                None,
            )
            marcador_limpo = next(
                (item for item in marcadores_limpos if item['numero'] == numero),
                None,
            )

            if marcador_bruto is None:
                log(f'QUESTAO {numero}: marcador não encontrado no texto bruto')
                continue
            if marcador_limpo is None:
                log(f'QUESTAO {numero}: marcador não encontrado no texto limpo')
                continue

            indice_bruto = marcadores_brutos.index(marcador_bruto)
            indice_limpo = marcadores_limpos.index(marcador_limpo)
            fim_bruto = (
                marcadores_brutos[indice_bruto + 1]['linha']
                if indice_bruto + 1 < len(marcadores_brutos)
                else len(linhas_brutas)
            )
            fim_limpo = (
                marcadores_limpos[indice_limpo + 1]['linha']
                if indice_limpo + 1 < len(marcadores_limpos)
                else len(linhas_limpas)
            )

            bloco_bruto = '\n'.join(
                linhas_brutas[marcador_bruto['linha'] + 1:fim_bruto]
            )
            bloco_limpo = '\n'.join(
                linhas_limpas[marcador_limpo['linha'] + 1:fim_limpo]
            )
            bloco_conteudo = limpar_conteudo_questao(bloco_limpo)
            bloco_expandido = _expandir_alternativas_inline(bloco_conteudo)
            linhas_expandido = bloco_expandido.splitlines()
            marcadores_restritos = _encontrar_marcadores_alternativas(
                linhas_expandido
            )
            marcadores_permissivos = _encontrar_marcadores_alternativas(
                linhas_expandido,
                permitir_marcadores_sem_pontuacao=True,
            )
            alternativas = extrair_alternativas_generico(bloco_conteudo)

            log(f'\n######## QUESTAO {numero} ########')
            imprimir_rotulo('TEXTO BRUTO EXTRAIDO', bloco_bruto)
            imprimir_rotulo(
                'TEXTO APOS LIMPEZA',
                bloco_conteudo,
            )
            imprimir_rotulo(
                'TEXTO ENVIADO A EXTRACAO',
                bloco_expandido,
            )
            log('===== MARCADORES =====')
            log({
                'restritos': marcadores_restritos,
                'permissivos': marcadores_permissivos,
            })
            log('===== ALTERNATIVAS RETORNADAS =====')
            log(alternativas)
            log(f'FIM: questão {numero}')
        except Exception:
            log(f'EXCECAO COMPLETA NA QUESTAO {numero}:')
            traceback.print_exc()

    log('FIM: diagnóstico concluído')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        print('EXCECAO FATAL COMPLETA:', flush=True)
        traceback.print_exc()
        raise
