# =========================================================
# IMPORTAÇÕES
# =========================================================

from django.contrib import messages
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

# Decorator que permite acesso somente aos desenvolvedores.
from usuarios.decorators import desenvolvedor_required

from .models import (
    ImagemProva,
    ImagemQuestao,
    Prova,
    distribuir_textos_base,
)
from .forms import ProvaForm

# Funções responsáveis pelo processamento automático dos PDFs.
from .importador import (
    extrair_texto_pdf,
    extrair_gabarito_enem,
    extrair_questoes_anuladas_gabarito,
    separar_questoes_enem,
    dividir_questoes_validas,
    preparar_questoes_para_importacao,
    importar_questoes_no_banco,
)

# Funções responsáveis pela extração, associação e revisão das imagens.
from .imagens import (
    anotar_alternativas_vetoriais,
    anotar_imagens_nas_alternativas,
    anotar_paginas_questoes,
    associar_imagem,
    capturar_confirmacoes,
    confirmar_associacao,
    confirmar_todas_sugestoes,
    extrair_e_registrar_imagens,
    gerar_sugestoes_associacao,
    ignorar_imagem,
    remover_associacao,
    restaurar_confirmacoes,
)


# =========================================================
# SEÇÃO 1 — LISTA DE PROVAS
# =========================================================

@desenvolvedor_required
def lista(request):
    """
    Mostra todas as provas cadastradas na plataforma.
    """

    # Busca todas as provas cadastradas.
    provas = Prova.objects.all()

    # Envia as provas para o template.
    return render(
        request,
        'provas/lista.html',
        {
            'provas': provas
        }
    )


# =========================================================
# SEÇÃO 2 — CRIAR PROVA
# =========================================================

@desenvolvedor_required
def criar(request):
    """
    Cria uma nova prova através da plataforma.
    """

    # Verifica se o formulário foi enviado.
    if request.method == 'POST':

        # Cria o formulário com os dados e arquivos enviados.
        form = ProvaForm(
            request.POST,
            request.FILES
        )

        # Verifica se todos os dados são válidos.
        if form.is_valid():

            # Salva a prova no banco de dados.
            prova = form.save()

            # Exibe uma mensagem de sucesso.
            messages.success(
                request,
                'Prova cadastrada com sucesso!'
            )

            # Vai para a página de detalhes da prova.
            return redirect(
                'provas:detalhe',
                prova_id=prova.id
            )

    else:

        # Cria um formulário vazio quando a página é aberta.
        form = ProvaForm()

    # Exibe o formulário.
    return render(
        request,
        'provas/form.html',
        {
            'form': form
        }
    )


# =========================================================
# SEÇÃO 3 — DETALHES DA PROVA
# =========================================================

@desenvolvedor_required
def detalhe(request, prova_id):
    """
    Mostra os detalhes de uma prova e suas questões.
    """

    # Procura a prova pelo ID.
    prova = get_object_or_404(
        Prova,
        id=prova_id
    )

    # Busca todas as questões relacionadas à prova.
    questoes = (
        prova.questoes
        .select_related('disciplina')
        .prefetch_related(
            'imagens_associadas__imagem',
            'textos_base_vinculados__texto_base',
        )
    )

    # Verifica se a prova já possui simulados.
    possui_simulados = prova.simulados.exists()

    # Estatísticas das imagens extraídas.
    total_imagens = prova.imagens.count()

    imagens_pendentes = (
        prova.imagens
        .filter(ignorada=False)
        .annotate(
            tem_confirmacao=Exists(
                ImagemQuestao.objects.filter(
                    imagem=OuterRef('pk'),
                    confirmada=True,
                )
            )
        )
        .filter(tem_confirmacao=False)
        .count()
    )

    # Exibe a página de detalhes.
    return render(
        request,
        'provas/detalhe.html',
        {
            'prova': prova,
            'questoes': questoes,
            'possui_simulados': possui_simulados,
            'total_imagens': total_imagens,
            'imagens_pendentes': imagens_pendentes,
        }
    )


# =========================================================
# SEÇÃO 4 — PROCESSAR PROVA
# =========================================================

@desenvolvedor_required
def processar(request, prova_id):
    """
    Processa automaticamente uma prova.

    O sistema:
    1. Lê o PDF da prova.
    2. Lê o PDF do gabarito.
    3. Identifica as questões.
    4. Identifica as alternativas.
    5. Identifica as respostas corretas.
    6. Salva tudo no banco de dados.
    """

    # O processamento deve acontecer somente
    # através do formulário POST da plataforma.
    if request.method != 'POST':

        messages.error(
            request,
            'O processamento deve ser iniciado pelo botão da plataforma.'
        )

        return redirect(
            'provas:detalhe',
            prova_id=prova_id
        )

    with transaction.atomic():
        prova = get_object_or_404(
            Prova.objects.select_for_update(),
            id=prova_id,
        )

        if prova.tipo != 'enem':
            messages.error(
                request,
                'A plataforma está configurada para processar apenas provas do ENEM.'
            )
            return redirect('provas:detalhe', prova_id=prova.id)

        if prova.status_importacao == 'processando':
            messages.error(
                request,
                'Esta prova já está sendo processada. Aguarde a conclusão.'
            )
            return redirect('provas:detalhe', prova_id=prova.id)

        if prova.simulados.exists():
            messages.error(
                request,
                'Esta prova já possui simulados vinculados e não pode ser reprocessada '
                'para preservar o histórico dos alunos.'
            )
            return redirect('provas:detalhe', prova_id=prova.id)

        if not prova.arquivo_pdf:
            messages.error(request, 'Esta prova não possui um PDF.')
            return redirect('provas:detalhe', prova_id=prova.id)

        if not prova.arquivo_gabarito:
            messages.error(request, 'Esta prova não possui um PDF de gabarito.')
            return redirect('provas:detalhe', prova_id=prova.id)

        prova.status_importacao = 'processando'
        prova.mensagem_importacao = ''
        prova.data_processamento = None
        prova.save(update_fields=[
            'status_importacao',
            'mensagem_importacao',
            'data_processamento',
        ])

        try:
            with transaction.atomic():
                # Guarda as associações confirmadas antes de recriar
                # as questões, para restaurá-las após a importação.
                confirmacoes_imagens = capturar_confirmacoes(prova)

                texto_prova = extrair_texto_pdf(prova.arquivo_pdf.path)
                questoes = separar_questoes_enem(texto_prova)
                anotar_paginas_questoes(prova, questoes)
                texto_gabarito = extrair_texto_pdf(prova.arquivo_gabarito.path)
                gabarito = extrair_gabarito_enem(texto_gabarito)
                anuladas = extrair_questoes_anuladas_gabarito(texto_gabarito)

                # As imagens precisam existir antes da validação para que
                # alternativas compostas apenas por figuras não sejam
                # rejeitadas como "sem texto". A falha nessa etapa não
                # desfaz a importação textual.
                resultado_imagens = None
                sugestoes_imagens = 0
                erro_imagens = ''

                try:
                    with transaction.atomic():
                        resultado_imagens = extrair_e_registrar_imagens(
                            prova
                        )
                        anotar_imagens_nas_alternativas(prova, questoes)
                except Exception as erro_imagens_extraidas:
                    resultado_imagens = None
                    erro_imagens = str(erro_imagens_extraidas)

                # Alternativas desenhadas diretamente no PDF (sem texto
                # extraível e sem imagem incorporada) são rasterizadas
                # e associadas à alternativa. A falha aqui não desfaz a
                # importação: as questões voltam a ser rejeitadas com
                # a mensagem original.
                try:
                    anotar_alternativas_vetoriais(prova, questoes)
                except Exception as erro_alternativas_vetoriais:
                    erro_imagens = erro_imagens or str(
                        erro_alternativas_vetoriais
                    )

                # Uma questão com problema não invalida a importação
                # inteira: as válidas são preservadas e os erros são
                # relatados individualmente.
                questoes_validas, problemas = dividir_questoes_validas(
                    questoes,
                    gabarito,
                    anuladas,
                )

                if not questoes_validas:
                    detalhes = '\n'.join(problemas)
                    if not detalhes:
                        detalhes = (
                            'Nenhuma questão válida foi encontrada '
                            'no PDF da prova.'
                        )
                    raise ValueError(detalhes)

                questoes_preparadas = preparar_questoes_para_importacao(
                    questoes_validas,
                    gabarito,
                )
                quantidade = importar_questoes_no_banco(
                    prova,
                    questoes_preparadas,
                    gabarito,
                )

                questoes_ignoradas = len(questoes) - len(questoes_validas)
                relatorio_problemas = ''
                if problemas:
                    relatorio_problemas = (
                        f'{quantidade} questão(ões) importada(s) de '
                        f'{len(questoes)} extraída(s). '
                        f'{questoes_ignoradas} ignorada(s) por inconsistência.'
                        '\n\nProblemas encontrados:\n'
                        + '\n'.join(
                            f'- {problema}'
                            for problema in problemas
                        )
                    )

                restaurar_confirmacoes(
                    prova,
                    confirmacoes_imagens,
                )

                # As sugestões são geradas em um savepoint próprio. Uma
                # falha nessa etapa não desfaz a importação textual.
                mensagem_imagens = ''

                if resultado_imagens is not None:
                    try:
                        with transaction.atomic():
                            sugestoes_imagens = gerar_sugestoes_associacao(
                                prova
                            )
                    except Exception as erro_sugestoes:
                        erro_imagens = str(erro_sugestoes)

                if erro_imagens:
                    mensagem_imagens = (
                        'As questões foram importadas, mas as imagens '
                        'não puderam ser processadas: '
                        f'{erro_imagens}'
                    )

                prova.status_importacao = 'processada'
                prova.data_processamento = timezone.now()
                prova.mensagem_importacao = '\n\n'.join(
                    parte
                    for parte in (relatorio_problemas, mensagem_imagens)
                    if parte
                )
                prova.save(update_fields=[
                    'status_importacao',
                    'data_processamento',
                    'mensagem_importacao',
                ])
        except Exception as erro:
            prova.status_importacao = 'erro'
            prova.mensagem_importacao = str(erro)
            prova.data_processamento = None
            prova.save(update_fields=[
                'status_importacao',
                'mensagem_importacao',
                'data_processamento',
            ])
            messages.error(
                request,
                'Ocorreu um erro durante o processamento da prova. '
                'Verifique os detalhes.'
            )
            return redirect('provas:detalhe', prova_id=prova.id)

        mensagem_sucesso = (
            'Prova processada! '
            f'{quantidade} questões foram importadas.'
        )

        if resultado_imagens:
            mensagem_sucesso += (
                f' {resultado_imagens["criadas"]} imagens foram extraídas'
                f' e {sugestoes_imagens} sugestões de associação criadas.'
            )

        messages.success(request, mensagem_sucesso)

        if problemas:
            messages.warning(
                request,
                f'{quantidade} questões foram importadas, mas '
                f'{len(problemas)} problema(s) foi(ram) encontrado(s). '
                'Confira os detalhes na página da prova.'
            )

        if mensagem_imagens:
            messages.warning(request, mensagem_imagens)

        return redirect('provas:detalhe', prova_id=prova.id)


# =========================================================
# SEÇÃO 5 — REVISÃO DAS IMAGENS
# =========================================================

@desenvolvedor_required
def revisar_imagens(request, prova_id):
    """
    Mostra as imagens extraídas para revisão e associação manual.
    """
    prova = get_object_or_404(Prova, id=prova_id)

    imagens = (
        prova.imagens
        .prefetch_related('associacoes__questao__disciplina')
        .order_by('pagina', 'indice_pagina', 'id')
    )

    questoes = (
        prova.questoes
        .select_related('disciplina')
        .order_by('numero', 'idioma')
    )

    pendentes = (
        prova.imagens
        .filter(ignorada=False)
        .annotate(
            tem_confirmacao=Exists(
                ImagemQuestao.objects.filter(
                    imagem=OuterRef('pk'),
                    confirmada=True,
                )
            )
        )
        .filter(tem_confirmacao=False)
        .count()
    )

    return render(
        request,
        'provas/imagens.html',
        {
            'prova': prova,
            'imagens': imagens,
            'questoes': questoes,
            'pendentes': pendentes,
        }
    )


# =========================================================
# SEÇÃO 6 — EXTRAIR IMAGENS DE UMA PROVA JÁ PROCESSADA
# =========================================================

@desenvolvedor_required
def extrair_imagens(request, prova_id):
    """
    Extrai/reprocessa apenas as imagens de uma prova já importada.
    """
    if request.method != 'POST':
        messages.error(
            request,
            'A extração de imagens deve ser iniciada pelo botão da plataforma.'
        )
        return redirect('provas:detalhe', prova_id=prova_id)

    prova = get_object_or_404(Prova, id=prova_id)

    if not prova.arquivo_pdf:
        messages.error(request, 'Esta prova não possui um PDF.')
        return redirect('provas:detalhe', prova_id=prova.id)

    try:
        resultado = extrair_e_registrar_imagens(prova)
    except Exception as erro:
        messages.error(
            request,
            f'Não foi possível extrair as imagens: {erro}'
        )
        return redirect('provas:detalhe', prova_id=prova.id)

    try:
        sugestoes = gerar_sugestoes_associacao(prova)
    except Exception as erro:
        sugestoes = 0
        messages.warning(
            request,
            'As imagens foram extraídas, mas não foi possível gerar '
            f'as sugestões automáticas: {erro}'
        )

    messages.success(
        request,
        f'{resultado["extraidas"]} imagens encontradas, '
        f'{resultado["criadas"]} novas e '
        f'{resultado["reutilizadas"]} já existentes. '
        f'{sugestoes} sugestões de associação criadas.'
    )

    return redirect('provas:revisar_imagens', prova_id=prova.id)


# =========================================================
# SEÇÃO 7 — AÇÕES DE REVISÃO DAS IMAGENS
# =========================================================

@desenvolvedor_required
def acao_imagem(request, prova_id):
    """
    Executa as ações POST da tela de revisão de imagens.
    """
    prova = get_object_or_404(Prova, id=prova_id)

    if request.method != 'POST':
        messages.error(
            request,
            'As ações de imagem devem ser enviadas pelo formulário da revisão.'
        )
        return redirect('provas:revisar_imagens', prova_id=prova.id)

    acao = request.POST.get('acao', '')

    if acao == 'associar':
        imagem = get_object_or_404(
            ImagemProva,
            id=request.POST.get('imagem_id'),
            prova=prova,
        )
        questao_id = request.POST.get('questao_id')

        if not questao_id:
            messages.error(
                request,
                'Selecione uma questão para associar à imagem.'
            )
            return redirect('provas:revisar_imagens', prova_id=prova.id)

        questao = get_object_or_404(
            prova.questoes,
            id=questao_id,
        )

        associar_imagem(
            imagem,
            questao,
            origem='manual',
            confirmar=True,
        )
        messages.success(
            request,
            f'Imagem associada manualmente à questão {questao.numero}.'
        )

    elif acao == 'confirmar':
        associacao = get_object_or_404(
            ImagemQuestao,
            id=request.POST.get('associacao_id'),
            imagem__prova=prova,
        )
        confirmar_associacao(associacao)
        messages.success(
            request,
            'Sugestão confirmada e imagem liberada no simulado.'
        )

    elif acao == 'remover':
        associacao = get_object_or_404(
            ImagemQuestao,
            id=request.POST.get('associacao_id'),
            imagem__prova=prova,
        )
        questao = associacao.questao
        remover_associacao(associacao)
        messages.success(
            request,
            f'Associação com a questão {questao.numero} removida.'
        )

    elif acao == 'ignorar':
        imagem = get_object_or_404(
            ImagemProva,
            id=request.POST.get('imagem_id'),
            prova=prova,
        )

        if ignorar_imagem(imagem, True):
            messages.success(request, 'Imagem ignorada na revisão.')
        else:
            messages.error(
                request,
                'Remova a associação confirmada antes de ignorar esta imagem.'
            )

    elif acao == 'reativar':
        imagem = get_object_or_404(
            ImagemProva,
            id=request.POST.get('imagem_id'),
            prova=prova,
        )
        ignorar_imagem(imagem, False)
        messages.success(request, 'Imagem reativada na revisão.')

    elif acao == 'confirmar_sugestoes':
        quantidade = confirmar_todas_sugestoes(prova)
        messages.success(
            request,
            f'{quantidade} sugestões foram confirmadas.'
        )

    else:
        messages.error(request, 'Ação de imagem desconhecida.')

    return redirect('provas:revisar_imagens', prova_id=prova.id)


# =========================================================
# SEÇÃO 8 — IMPRESSÃO DA PROVA COM IMAGENS
# =========================================================

@desenvolvedor_required
def imprimir(request, prova_id):
    """
    Exibe uma versão da prova preparada para impressão.
    """
    prova = get_object_or_404(Prova, id=prova_id)

    questoes = list(
        prova.questoes
        .select_related('disciplina')
        .prefetch_related(
            'alternativas',
            'imagens_associadas__imagem',
            'textos_base_vinculados__texto_base',
        )
        .order_by('numero', 'idioma')
    )

    distribuir_textos_base(questoes)

    return render(
        request,
        'provas/imprimir.html',
        {
            'prova': prova,
            'questoes': questoes,
        }
    )

