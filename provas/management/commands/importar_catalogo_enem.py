"""
Importa o catálogo oficial do ENEM em lote.

O comando cadastra as provas no banco, importa as questões das provas
selecionadas e registra o resultado individual de cada item. A execução
é idempotente: provas já importadas são ignoradas, a menos que
``--forcar`` seja informado.
"""

import json
import os
import shutil
import tempfile
import time
import urllib.request
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from provas import catalogo_enem
from provas.importador import (
    dividir_questoes_validas,
    extrair_gabarito_enem,
    extrair_questoes_anuladas_gabarito,
    extrair_texto_pdf,
    importar_questoes_no_banco,
    preparar_questoes_para_importacao,
    separar_questoes_enem,
)
from provas.imagens import (
    anotar_alternativas_vetoriais,
    anotar_imagens_nas_alternativas,
    anotar_paginas_questoes,
    capturar_confirmacoes,
    extrair_e_registrar_imagens,
    gerar_sugestoes_associacao,
    restaurar_confirmacoes,
)
from provas.models import (
    ImportacaoItem,
    ImportacaoLote,
    Prova,
)


# Quantidade de questões de cada dia do ENEM.
QUESTOES_ESPERADAS = 90

# Faixa de numeração oficial de cada dia.
# O 1º dia vai de 1 a 90 e o 2º dia de 91 a 180.
FAIXAS = {
    1: (1, 90),
    2: (91, 180),
}


def faixa_questoes(dia):
    """Devolve o primeiro e o último número de questão do dia."""
    return FAIXAS.get(dia, (1, QUESTOES_ESPERADAS))

# Espaço mínimo livre em MEDIA_ROOT antes de iniciar um item.
ESPACO_MINIMO_MB = 100


def montar_questoes_digital(questoes_ingles, questoes_espanhol):
    """
    Agrega as variantes de idioma do caderno digital do 1º dia.

    As questões 1 a 5 são específicas de cada idioma. As demais são
    compartilhadas e vêm do arquivo em inglês. O resultado mantém as
    95 questões internas: 5 de Inglês, 5 de Espanhol e 85 comuns.
    """
    questoes = [
        questao
        for questao in questoes_ingles
        if questao['numero'] > 5
    ]

    for questao in questoes_ingles:
        if 1 <= questao['numero'] <= 5:
            questoes.append(
                {**questao, '_idioma': 'Inglês'}
            )

    for questao in questoes_espanhol:
        if 1 <= questao['numero'] <= 5:
            questoes.append(
                {**questao, '_idioma': 'Espanhol'}
            )

    return questoes


def _resposta_no_gabarito(gabarito, numero, idioma=None):
    """Busca uma resposta aceitando as duas formas de chave."""
    if idioma and (idioma, numero) in gabarito:
        return gabarito[(idioma, numero)]

    return gabarito.get(numero)


def montar_gabarito_digital(
    gabarito_ingles,
    gabarito_espanhol,
    anuladas_ingles=None,
    anuladas_espanhol=None,
):
    """
    Agrega os gabaritos das duas variantes de idioma.

    As questões 1 a 5 usam o gabarito do próprio idioma. Da questão 6
    em diante, o gabarito é o do arquivo em inglês, que representa o
    caderno compartilhado.
    """
    anuladas_ingles = anuladas_ingles or set()
    anuladas_espanhol = anuladas_espanhol or set()

    gabarito = {}
    anuladas = set()

    for numero in range(6, QUESTOES_ESPERADAS + 1):
        resposta = _resposta_no_gabarito(gabarito_ingles, numero)
        if resposta:
            gabarito[numero] = resposta

        if numero in anuladas_ingles or numero in anuladas_espanhol:
            anuladas.add(numero)

    for idioma, gabarito_idioma, anuladas_idioma in (
        ('Inglês', gabarito_ingles, anuladas_ingles),
        ('Espanhol', gabarito_espanhol, anuladas_espanhol),
    ):
        for numero in range(1, 6):
            resposta = _resposta_no_gabarito(
                gabarito_idioma,
                numero,
                idioma,
            )

            if resposta:
                gabarito[(idioma, numero)] = resposta

            if (
                (idioma, numero) in anuladas_idioma
                or numero in anuladas_idioma
            ):
                anuladas.add((idioma, numero))

    return gabarito, anuladas


def numeros_anulados(anuladas):
    """Extrai os números das questões anuladas, ignorando o idioma."""
    numeros = set()

    for chave in anuladas:
        if isinstance(chave, tuple):
            numeros.add(chave[1])
        else:
            numeros.add(chave)

    return numeros


def validar_cobertura(
    questoes,
    anuladas=None,
    esperado=QUESTOES_ESPERADAS,
    inicio=1,
):
    """
    Confere se todas as questões esperadas foram extraídas.

    Devolve a lista de números ausentes. A validação é usada como
    bloqueio: uma prova incompleta não deve entrar no catálogo.
    """
    anuladas = anuladas or set()
    numeros = {questao['numero'] for questao in questoes}
    anulados = numeros_anulados(anuladas)
    ausentes = [
        numero
        for numero in range(inicio, inicio + esperado)
        if numero not in numeros and numero not in anulados
    ]

    return ausentes


def validar_variantes_idioma(questoes):
    """
    Confere se as questões 1–5 têm as duas variantes de idioma.

    A cobertura por número não detecta a falta de uma variante, pois
    Inglês e Espanhol compartilham os mesmos números.
    """
    presentes = {
        (
            questao.get('_idioma') or questao.get('idioma'),
            questao['numero'],
        )
        for questao in questoes
        if questao['numero'] in range(1, 6)
    }

    return [
        f'{idioma}: {numero}'
        for idioma in ('Inglês', 'Espanhol')
        for numero in range(1, 6)
        if (idioma, numero) not in presentes
    ]


class Command(BaseCommand):
    help = (
        'Cadastra e importa as provas oficiais do ENEM 2020-2025 '
        'a partir do catálogo do INEP.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--ano',
            action='append',
            type=int,
            help='Ano a importar. Pode ser repetido.',
        )
        parser.add_argument(
            '--modalidade',
            choices=('regular', 'digital'),
            help='Modalidade a importar.',
        )
        parser.add_argument(
            '--dia',
            action='append',
            type=int,
            choices=(1, 2),
            help='Dia a importar. Pode ser repetido.',
        )
        parser.add_argument(
            '--caderno',
            type=int,
            help='Número do caderno a importar.',
        )
        parser.add_argument(
            '--acessibilidade',
            choices=('padrao', 'braile_ledor', 'libras'),
            help='Formato de acessibilidade a importar.',
        )
        parser.add_argument(
            '--apenas-importaveis',
            action='store_true',
            help='Ignora os cadernos de acessibilidade.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostra o planejamento sem alterar o banco.',
        )
        parser.add_argument(
            '--somente-cadastrar',
            action='store_true',
            help='Cadastra as provas sem importar questões.',
        )
        parser.add_argument(
            '--retomar',
            action='store_true',
            help='Reprocessa apenas itens pendentes ou com erro.',
        )
        parser.add_argument(
            '--forcar',
            action='store_true',
            help='Reimporta provas já concluídas.',
        )
        parser.add_argument(
            '--limite',
            type=int,
            help='Quantidade máxima de provas processadas.',
        )
        parser.add_argument(
            '--pdf-dir',
            help=(
                'Diretório com PDFs oficiais baixados previamente. '
                'Os arquivos devem manter o nome original do INEP.'
            ),
        )
        parser.add_argument(
            '--relatorio',
            help='Caminho do relatório JSON.',
        )
        parser.add_argument(
            '--espaco-minimo-mb',
            type=int,
            default=ESPACO_MINIMO_MB,
            help='Espaço livre mínimo em MEDIA_ROOT antes de cada prova.',
        )

    # ---------------------------------------------------------
    # Entrada do comando
    # ---------------------------------------------------------

    def handle(self, *args, **options):
        entradas = catalogo_enem.filtrar(
            ano=options.get('ano'),
            modalidade=options.get('modalidade'),
            dia=options.get('dia'),
            caderno=options.get('caderno'),
            acessibilidade=options.get('acessibilidade'),
            apenas_importaveis=options.get('apenas_importaveis'),
        )

        if options.get('limite'):
            entradas = entradas[:options['limite']]

        if not entradas:
            raise CommandError(
                'Nenhuma prova do catálogo corresponde aos filtros.'
            )

        if options.get('dry_run'):
            self._mostrar_planejamento(entradas, options)
            return

        identificador = self._identificador(options)
        lote = ImportacaoLote.objects.create(
            identificador=identificador,
            ano=(options.get('ano') or [None])[0],
            modalidade=options.get('modalidade') or '',
        )

        inicio = time.monotonic()
        itens_relatorio = []

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f'Lote {identificador}: {len(entradas)} prova(s).'
            )
        )

        try:
            for indice, entrada in enumerate(entradas, start=1):
                prefixo = f'[{indice}/{len(entradas)}] {entrada.chave}'
                self.stdout.write(prefixo)

                item = self._processar_item(
                    entrada,
                    lote,
                    options,
                )
                itens_relatorio.append(self._resumo_item(item))

                if item.status == 'importado':
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'  importado: '
                            f'{item.detalhes.get("questoes", 0)} questões, '
                            f'{item.detalhes.get("imagens", 0)} imagens.'
                        )
                    )
                elif item.status == 'cadastrado':
                    self.stdout.write(
                        self.style.SUCCESS('  cadastrado (sem questões).')
                    )
                elif item.status == 'ignorado':
                    self.stdout.write(
                        self.style.WARNING(
                            f'  ignorado: {item.mensagem}'
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.ERROR(f'  erro: {item.mensagem}')
                    )
        except KeyboardInterrupt:
            lote.status = 'interrompido'
            lote.save(update_fields=['status'])
            raise CommandError(
                'Importação interrompida. Use --retomar para continuar.'
            )
        finally:
            duracao = round(time.monotonic() - inicio, 2)
            resumo = self._montar_resumo(
                itens_relatorio,
                duracao,
            )
            lote.resumo = resumo

            if lote.status == 'em_andamento':
                lote.status = 'concluido'

            lote.save(update_fields=['resumo', 'status'])

            caminho = self._gravar_relatorio(
                options.get('relatorio'),
                identificador,
                resumo,
            )

            self.stdout.write('')
            self.stdout.write(
                self.style.MIGRATE_HEADING('Resumo do lote')
            )
            self.stdout.write(
                f'  cadastrados: {resumo["cadastrados"]} | '
                f'importados: {resumo["importados"]} | '
                f'ignorados: {resumo["ignorados"]} | '
                f'erros: {resumo["erros"]}'
            )
            self.stdout.write(
                f'  questões: {resumo["questoes"]} | '
                f'imagens: {resumo["imagens"]} | '
                f'tempo: {duracao}s'
            )
            self.stdout.write(f'  relatório: {caminho}')

            if resumo['erros']:
                self.stdout.write(
                    self.style.ERROR(
                        '  Há itens com erro. Use --retomar após '
                        'corrigir a causa.'
                    )
                )

    # ---------------------------------------------------------
    # Planejamento
    # ---------------------------------------------------------

    def _mostrar_planejamento(self, entradas, options):
        total_questoes = 0
        total_gabaritos = 0

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f'Planejamento ({len(entradas)} prova(s)):'
            )
        )

        for entrada in entradas:
            marca = (
                'importar'
                if entrada.importar_questoes
                and not options.get('somente_cadastrar')
                else 'cadastrar'
            )
            self.stdout.write(
                f'  {entrada.chave:<32} {marca:<9} '
                f'{entrada.nome}'
            )

            if marca == 'importar':
                total_questoes += entrada.quantidade_questoes or 0
                total_gabaritos += len(entrada.arquivos)

        self.stdout.write('')
        self.stdout.write(
            f'  Questões previstas: {total_questoes} '
            '(90 por prova; o 1º dia gera 95 registros)'
        )
        self.stdout.write(
            f'  Gabaritos previstos: {total_gabaritos}'
        )
        self.stdout.write(
            '  Nenhuma alteração foi feita no banco (--dry-run).'
        )

    # ---------------------------------------------------------
    # Processamento de um item
    # ---------------------------------------------------------

    def _processar_item(self, entrada, lote, options):
        item, _ = ImportacaoItem.objects.get_or_create(
            chave_oficial=entrada.chave,
            defaults={'lote': lote},
        )

        if item.status == 'importado' and not options.get('forcar'):
            # O estado permanece "importado" no banco. Apenas o
            # relatório desta execução registra o item como ignorado.
            item.lote = lote
            item.save(update_fields=['lote', 'atualizado_em'])
            item.status = 'ignorado'
            item.mensagem = 'Prova já importada anteriormente.'
            return item

        if (
            options.get('retomar')
            and item.status not in ('pendente', 'erro')
            and not options.get('forcar')
        ):
            item.status = 'ignorado'
            item.mensagem = 'Item fora do escopo da retomada.'
            return item

        item.lote = lote
        item.tentativas += 1
        item.status = 'pendente'
        item.etapa = 'cadastro'
        item.mensagem = ''
        item.save()

        try:
            self._verificar_espaco(options.get('espaco_minimo_mb'))
            prova = self._cadastrar(entrada, item)
            item.prova = prova
            item.save(update_fields=['prova'])

            if (
                not entrada.importar_questoes
                or options.get('somente_cadastrar')
            ):
                item.status = 'cadastrado'
                item.etapa = 'concluido'
                item.detalhes = {
                    'questoes': 0,
                    'imagens': 0,
                    'acessibilidade': entrada.acessibilidade,
                }
                item.save()
                return item

            if prova.questoes.exists() and not options.get('forcar'):
                item.status = 'ignorado'
                item.etapa = 'concluido'
                item.mensagem = (
                    'A prova já possui questões e não foi reprocessada.'
                )
                item.save()
                return item

            self._importar(prova, entrada, item, options)

            item.status = 'importado'
            item.etapa = 'concluido'
            item.mensagem = ''
            item.save()
        except Exception as erro:
            item.status = 'erro'
            item.etapa = 'concluido'
            item.mensagem = str(erro)
            item.save()

        return item

    def _cadastrar(self, entrada, item):
        """
        Cria ou atualiza a prova do catálogo sem tocar em provas manuais.
        """
        item.etapa = 'cadastro'
        item.save(update_fields=['etapa'])

        dados = {
            'nome': entrada.nome,
            'tipo': 'enem',
            'ano': entrada.ano,
            'descricao': entrada.descricao,
            'modalidade': entrada.modalidade,
            'dia': entrada.dia,
            'caderno': entrada.caderno,
            'cor_caderno': entrada.cor,
            'acessibilidade': entrada.acessibilidade,
            'idioma_caderno': entrada.idioma,
            'url_prova': entrada.url_prova,
            'url_gabarito': entrada.url_gabarito,
            'url_prova_espanhol': entrada.url_prova_espanhol,
            'url_gabarito_espanhol': entrada.url_gabarito_espanhol,
            'fonte_url': entrada.fonte_url,
            'quantidade_questoes': entrada.quantidade_questoes,
            'origem': 'catalogo_oficial',
        }

        prova = Prova.objects.filter(
            chave_oficial=entrada.chave
        ).first()

        if prova is None:
            return Prova.objects.create(
                chave_oficial=entrada.chave,
                **dados,
            )

        if prova.origem == 'manual':
            raise ValueError(
                'Já existe uma prova manual com esta chave oficial.'
            )

        campos = []
        for campo, valor in dados.items():
            if getattr(prova, campo) != valor:
                setattr(prova, campo, valor)
                campos.append(campo)

        if campos:
            prova.save(update_fields=campos)

        return prova

    # ---------------------------------------------------------
    # Importação das questões
    # ---------------------------------------------------------

    def _importar(self, prova, entrada, item, options):
        item.etapa = 'download'
        item.save(update_fields=['etapa'])

        prova.status_importacao = 'processando'
        prova.mensagem_importacao = ''
        prova.data_processamento = None
        prova.save(update_fields=[
            'status_importacao',
            'mensagem_importacao',
            'data_processamento',
        ])

        try:
            with tempfile.TemporaryDirectory(
                prefix='enem-catalogo-'
            ) as temporario:
                arquivos = self._obter_arquivos(
                    entrada,
                    Path(temporario),
                    options,
                )

                caminho_principal = arquivos['principal']['prova']
                self._anexar_arquivos(prova, entrada, arquivos)

                item.etapa = 'extracao'
                item.save(update_fields=['etapa'])

                with transaction.atomic():
                    confirmacoes = capturar_confirmacoes(prova)

                    questoes, gabarito, anuladas = self._extrair(
                        entrada,
                        arquivos,
                    )
                    anotar_paginas_questoes(prova, questoes)

                    imagens = 0
                    try:
                        with transaction.atomic():
                            extrair_e_registrar_imagens(
                                prova,
                                caminho_pdf=caminho_principal,
                            )
                            anotar_imagens_nas_alternativas(
                                prova,
                                questoes,
                            )
                    except Exception as erro_imagens:
                        self.stderr.write(
                            self.style.WARNING(
                                '  imagens não processadas: '
                                f'{erro_imagens}'
                            )
                        )

                    try:
                        anotar_alternativas_vetoriais(prova, questoes)
                    except Exception as erro_vetoriais:
                        self.stderr.write(
                            self.style.WARNING(
                                '  alternativas desenhadas não '
                                f'processadas: {erro_vetoriais}'
                            )
                        )

                    validas, problemas = dividir_questoes_validas(
                        questoes,
                        gabarito,
                        anuladas,
                    )

                    ausentes = validar_cobertura(
                        validas,
                        anuladas,
                        inicio=faixa_questoes(entrada.dia)[0],
                    )

                    if ausentes:
                        amostra = ', '.join(
                            str(numero) for numero in ausentes[:10]
                        )
                        restantes = len(ausentes) - 10

                        if restantes > 0:
                            amostra += f' e mais {restantes}'

                        raise ValueError(
                            f'Extração incompleta: faltam as questões '
                            f'{amostra}. Nenhuma questão foi importada.'
                        )

                    if entrada.e_digital_dia_1:
                        ausentes_idioma = validar_variantes_idioma(
                            validas
                        )

                        if ausentes_idioma:
                            raise ValueError(
                                'Extração incompleta: faltam as '
                                'variantes de idioma '
                                f'{", ".join(ausentes_idioma)}. '
                                'Nenhuma questão foi importada.'
                            )

                    preparadas = preparar_questoes_para_importacao(
                        validas,
                        gabarito,
                    )

                    item.etapa = 'importacao'
                    item.save(update_fields=['etapa'])

                    quantidade = importar_questoes_no_banco(
                        prova,
                        preparadas,
                        gabarito,
                    )

                    restaurar_confirmacoes(prova, confirmacoes)

                    sugestoes = 0
                    try:
                        with transaction.atomic():
                            sugestoes = gerar_sugestoes_associacao(
                                prova
                            )
                    except Exception as erro_sugestoes:
                        self.stderr.write(
                            self.style.WARNING(
                                '  sugestões de imagem não geradas: '
                                f'{erro_sugestoes}'
                            )
                        )

                    imagens = prova.imagens.count()
                    anuladas_numeros = sorted(
                        numeros_anulados(anuladas)
                    )

                    # A quantidade oficial continua sendo 90, mesmo
                    # quando há questões anuladas no gabarito.
                    prova.quantidade_questoes = (
                        entrada.quantidade_questoes
                        or QUESTOES_ESPERADAS
                    )
                    prova.status_importacao = 'processada'
                    prova.data_processamento = timezone.now()
                    prova.mensagem_importacao = self._mensagem_importacao(
                        quantidade,
                        len(questoes),
                        problemas,
                        sugestoes,
                        anuladas_numeros,
                    )
                    prova.save(update_fields=[
                        'quantidade_questoes',
                        'status_importacao',
                        'data_processamento',
                        'mensagem_importacao',
                    ])

                    item.detalhes = {
                        'questoes': quantidade,
                        'questoes_extraidas': len(questoes),
                        'questoes_ignoradas': len(questoes) - len(validas),
                        'anuladas': anuladas_numeros,
                        'imagens': imagens,
                        'sugestoes_imagens': sugestoes,
                        'problemas': problemas[:50],
                    }
                    item.save(update_fields=['detalhes'])

        except Exception as erro:
            prova.status_importacao = 'erro'
            prova.mensagem_importacao = str(erro)
            prova.data_processamento = None
            prova.save(update_fields=[
                'status_importacao',
                'mensagem_importacao',
                'data_processamento',
            ])
            raise

    def _extrair(self, entrada, arquivos):
        """
        Extrai questões e gabarito, agregando os idiomas do digital.
        """
        if entrada.e_digital_dia_1:
            texto_ingles = extrair_texto_pdf(
                arquivos['principal']['prova']
            )
            texto_gabarito_ingles = extrair_texto_pdf(
                arquivos['principal']['gabarito']
            )
            texto_espanhol = extrair_texto_pdf(
                arquivos['espanhol']['prova']
            )
            texto_gabarito_espanhol = extrair_texto_pdf(
                arquivos['espanhol']['gabarito']
            )

            questoes = montar_questoes_digital(
                separar_questoes_enem(texto_ingles),
                separar_questoes_enem(texto_espanhol),
            )

            gabarito, anuladas = montar_gabarito_digital(
                extrair_gabarito_enem(
                    texto_gabarito_ingles,
                    idioma_padrao='Inglês',
                ),
                extrair_gabarito_enem(
                    texto_gabarito_espanhol,
                    idioma_padrao='Espanhol',
                ),
                extrair_questoes_anuladas_gabarito(
                    texto_gabarito_ingles
                ),
                extrair_questoes_anuladas_gabarito(
                    texto_gabarito_espanhol
                ),
            )

            return questoes, gabarito, anuladas

        texto = extrair_texto_pdf(arquivos['principal']['prova'])
        texto_gabarito = extrair_texto_pdf(
            arquivos['principal']['gabarito']
        )

        return (
            separar_questoes_enem(texto),
            extrair_gabarito_enem(texto_gabarito),
            extrair_questoes_anuladas_gabarito(texto_gabarito),
        )

    def _mensagem_importacao(
        self,
        quantidade,
        extraidas,
        problemas,
        sugestoes,
        anuladas=None,
    ):
        partes = []

        if problemas:
            ignoradas = extraidas - quantidade
            partes.append(
                f'{quantidade} questão(ões) importada(s) de '
                f'{extraidas} extraída(s). {ignoradas} ignorada(s) por '
                'inconsistência.\n\nProblemas encontrados:\n'
                + '\n'.join(f'- {problema}' for problema in problemas)
            )

        if anuladas:
            lista = ', '.join(str(numero) for numero in anuladas)
            partes.append(
                f'{len(anuladas)} questão(ões) anulada(s) no gabarito '
                f'oficial e não importada(s): {lista}.'
            )

        return '\n\n'.join(partes)

    # ---------------------------------------------------------
    # Arquivos
    # ---------------------------------------------------------

    def _obter_arquivos(self, entrada, diretorio, options):
        """
        Localiza os PDFs no diretório informado ou baixa do INEP.
        """
        resultado = {}

        for par in entrada.arquivos:
            idioma = par['idioma']
            chave = self._chave_idioma(idioma)

            caminho_prova = self._obter_pdf(
                par['url_prova'],
                diretorio,
                options.get('pdf_dir'),
                sufixo=f'{chave}-prova',
            )
            caminho_gabarito = self._obter_pdf(
                par['url_gabarito'],
                diretorio,
                options.get('pdf_dir'),
                sufixo=f'{chave}-gabarito',
            )

            resultado[chave] = {
                'prova': caminho_prova,
                'gabarito': caminho_gabarito,
            }

        return resultado

    def _chave_idioma(self, idioma):
        if idioma == 'Espanhol':
            return 'espanhol'

        return 'principal'

    def _obter_pdf(self, url, diretorio, pdf_dir, sufixo):
        nome = url.rsplit('/', 1)[-1]

        if pdf_dir:
            caminho_local = self._procurar_pdf(pdf_dir, nome)
            if caminho_local:
                return caminho_local

        destino = diretorio / f'{sufixo}-{nome}'
        self._baixar(url, destino)
        return destino

    def _procurar_pdf(self, pdf_dir, nome):
        base = Path(pdf_dir)

        candidatos = list(base.rglob(nome))
        if candidatos:
            return candidatos[0]

        return None

    def _baixar(self, url, destino):
        requisicao = urllib.request.Request(
            url,
            headers={'User-Agent': 'Examix/1.0 (importacao oficial)'},
        )

        try:
            with urllib.request.urlopen(
                requisicao,
                timeout=120,
            ) as resposta:
                with open(destino, 'wb') as arquivo:
                    shutil.copyfileobj(resposta, arquivo)
        except Exception as erro:
            raise ValueError(
                f'Não foi possível baixar {url}: {erro}'
            )

        if not destino.exists() or destino.stat().st_size == 0:
            raise ValueError(
                f'O download de {url} gerou um arquivo vazio.'
            )

        return destino

    def _anexar_arquivos(self, prova, entrada, arquivos):
        """
        Guarda os PDFs em MEDIA_ROOT para permitir reprocessamento.
        """
        principal = arquivos['principal']
        self._salvar_campo(
            prova,
            'arquivo_pdf',
            principal['prova'],
        )
        self._salvar_campo(
            prova,
            'arquivo_gabarito',
            principal['gabarito'],
        )

        if 'espanhol' in arquivos:
            espanhol = arquivos['espanhol']
            self._salvar_campo(
                prova,
                'arquivo_pdf_espanhol',
                espanhol['prova'],
            )
            self._salvar_campo(
                prova,
                'arquivo_gabarito_espanhol',
                espanhol['gabarito'],
            )

    def _salvar_campo(self, prova, campo, caminho):
        atual = getattr(prova, campo)

        if atual and default_storage.exists(atual.name):
            return

        nome = os.path.basename(str(caminho))

        with open(caminho, 'rb') as arquivo:
            atual.save(nome, File(arquivo), save=True)

    # ---------------------------------------------------------
    # Relatório
    # ---------------------------------------------------------

    def _verificar_espaco(self, minimo_mb):
        if minimo_mb is None:
            return

        if settings.MEDIA_ROOT is None:
            return

        livre = shutil.disk_usage(settings.MEDIA_ROOT).free
        minimo = minimo_mb * 1024 * 1024

        if livre < minimo:
            raise ValueError(
                f'Espaço livre insuficiente em MEDIA_ROOT: '
                f'{livre // (1024 * 1024)} MB disponíveis; '
                f'mínimo de {minimo_mb} MB.'
            )

    def _identificador(self, options):
        partes = ['enem-catalogo']

        if options.get('ano'):
            partes.append('-'.join(str(ano) for ano in options['ano']))

        if options.get('modalidade'):
            partes.append(options['modalidade'])

        if options.get('dia'):
            partes.append('d' + 'd'.join(str(dia) for dia in options['dia']))

        partes.append(timezone.now().strftime('%Y%m%d-%H%M%S-%f'))

        return '-'.join(partes)

    def _resumo_item(self, item):
        return {
            'chave': item.chave_oficial,
            'status': item.status,
            'mensagem': item.mensagem,
            'questoes': item.detalhes.get('questoes', 0),
            'imagens': item.detalhes.get('imagens', 0),
        }

    def _montar_resumo(self, itens, duracao):
        resumo = {
            'total': len(itens),
            'cadastrados': 0,
            'importados': 0,
            'ignorados': 0,
            'erros': 0,
            'questoes': 0,
            'imagens': 0,
            'duracao_s': duracao,
            'itens': itens,
        }

        for item in itens:
            if item['status'] == 'cadastrado':
                resumo['cadastrados'] += 1
            elif item['status'] == 'importado':
                resumo['importados'] += 1
                resumo['questoes'] += item['questoes']
                resumo['imagens'] += item['imagens']
            elif item['status'] == 'ignorado':
                resumo['ignorados'] += 1
            else:
                resumo['erros'] += 1

        return resumo

    def _gravar_relatorio(self, caminho, identificador, resumo):
        if not caminho:
            pasta = Path(settings.BASE_DIR) / 'outputs' / 'relatorios'
            pasta.mkdir(parents=True, exist_ok=True)
            caminho = pasta / f'{identificador}.json'

        caminho = Path(caminho)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(
            json.dumps(resumo, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )

        return caminho
