"""Inspeção do schema SQLite e das constraints no banco temporário."""

import os

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'audit_settings')
django.setup()

from django.db import IntegrityError, connection, transaction  # noqa: E402

from provas.models import (  # noqa: E402
    Disciplina,
    ImagemProva,
    ImagemQuestao,
    Prova,
    Questao,
)


def imprimir_schema():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE name LIKE 'provas_imagem%' "
            "ORDER BY type DESC, name"
        )
        for nome, sql in cursor.fetchall():
            print(f'--- {nome} ---')
            print(sql)

        for tabela in ('provas_imagemprova', 'provas_imagemquestao'):
            cursor.execute(f'PRAGMA index_list("{tabela}")')
            print(f'--- PRAGMA index_list({tabela}) ---')
            for linha in cursor.fetchall():
                print(linha)

            cursor.execute(f'PRAGMA foreign_key_list("{tabela}")')
            print(f'--- PRAGMA foreign_key_list({tabela}) ---')
            for linha in cursor.fetchall():
                print(linha)


def main():
    imprimir_schema()

    disciplina = Disciplina.objects.create(nome='Auditoria')
    prova = Prova.objects.create(
        nome='Auditoria constraints',
        tipo='enem',
        ano=2024,
    )
    questao_1 = Questao.objects.create(
        prova=prova,
        disciplina=disciplina,
        numero=1,
        enunciado='Q1',
    )
    questao_2 = Questao.objects.create(
        prova=prova,
        disciplina=disciplina,
        numero=2,
        enunciado='Q2',
    )

    def criar_imagem(indice):
        return ImagemProva.objects.create(
            prova=prova,
            arquivo=f'provas/imagens/auditoria/{indice}.png',
            hash_sha256=f'{indice:064d}',
            pagina=1,
            indice_pagina=indice,
        )

    imagem = criar_imagem(0)

    # 1) Várias associações NÃO confirmadas para a mesma imagem são aceitas.
    ImagemQuestao.objects.create(
        imagem=imagem,
        questao=questao_1,
        confirmada=False,
        origem='automatica',
    )
    ImagemQuestao.objects.create(
        imagem=imagem,
        questao=questao_2,
        confirmada=False,
        origem='automatica',
    )
    print('varias_nao_confirmadas: OK')

    # 2) Duas confirmações para a mesma imagem são bloqueadas.
    ImagemQuestao.objects.filter(
        imagem=imagem,
        questao=questao_1,
    ).update(confirmada=True)

    try:
        with transaction.atomic():
            ImagemQuestao.objects.filter(
                imagem=imagem,
                questao=questao_2,
            ).update(confirmada=True)
    except IntegrityError as erro:
        print(f'duas_confirmadas_bloqueadas: OK ({erro})')
    else:
        print('duas_confirmadas_bloqueadas: FALHOU')

    # 3) Associação duplicada imagem/questão é bloqueada.
    try:
        with transaction.atomic():
            ImagemQuestao.objects.create(
                imagem=imagem,
                questao=questao_1,
                confirmada=False,
                origem='manual',
            )
    except IntegrityError as erro:
        print(f'associacao_duplicada_bloqueada: OK ({erro})')
    else:
        print('associacao_duplicada_bloqueada: FALHOU')

    # 4) Deduplicação de imagem por prova/hash/página/índice.
    try:
        with transaction.atomic():
            criar_imagem(0)
    except IntegrityError as erro:
        print(f'imagem_duplicada_bloqueada: OK ({erro})')
    else:
        print('imagem_duplicada_bloqueada: FALHOU')

    # 5) CASCADE ao remover a questão e a imagem.
    print(
        'associacoes_antes:',
        ImagemQuestao.objects.count(),
    )
    questao_2.delete()
    print(
        'apos_remover_questao_2:',
        ImagemQuestao.objects.count(),
    )
    imagem.delete()
    print(
        'apos_remover_imagem:',
        ImagemQuestao.objects.count(),
    )

    # 6) CASCADE da prova para as imagens.
    outra = criar_imagem(1)
    prova.delete()
    print(
        'imagens_apos_remover_prova:',
        ImagemProva.objects.filter(id=outra.id).exists(),
    )


if __name__ == '__main__':
    main()
