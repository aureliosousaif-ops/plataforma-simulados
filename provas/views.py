# =========================================================
# IMPORTAÇÕES
# =========================================================

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

# Decorator que permite acesso somente aos desenvolvedores.
from usuarios.decorators import desenvolvedor_required

from .models import Prova
from .forms import ProvaForm

# Funções responsáveis pelo processamento automático dos PDFs.
from .importador import (
    extrair_texto_pdf,
    extrair_gabarito_enem,
    separar_questoes_enem,
    validar_questoes_com_gabarito,
    preparar_questoes_para_importacao,
    importar_questoes_no_banco,
    validar_estrutura_questoes,
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
    questoes = prova.questoes.all()

    # Verifica se a prova já possui simulados.
    possui_simulados = prova.simulados.exists()

    # Exibe a página de detalhes.
    return render(
        request,
        'provas/detalhe.html',
        {
            'prova': prova,
            'questoes': questoes,
            'possui_simulados': possui_simulados,
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
                texto_prova = extrair_texto_pdf(prova.arquivo_pdf.path)
                questoes = separar_questoes_enem(texto_prova)
                texto_gabarito = extrair_texto_pdf(prova.arquivo_gabarito.path)
                gabarito = extrair_gabarito_enem(texto_gabarito)

                problemas = validar_questoes_com_gabarito(questoes, gabarito)
                problemas.extend(validar_estrutura_questoes(questoes, gabarito))
                if problemas:
                    raise ValueError('\n'.join(problemas))

                questoes_preparadas = preparar_questoes_para_importacao(
                    questoes,
                    gabarito,
                )
                quantidade = importar_questoes_no_banco(
                    prova,
                    questoes_preparadas,
                    gabarito,
                )

                prova.status_importacao = 'processada'
                prova.data_processamento = timezone.now()
                prova.mensagem_importacao = ''
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

        messages.success(
            request,
            f'Prova processada com sucesso! {quantidade} questões foram importadas.'
        )
        return redirect('provas:detalhe', prova_id=prova.id)
