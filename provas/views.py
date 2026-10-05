# =========================================================
# IMPORTAÇÕES
# =========================================================

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

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

    # Busca a prova pelo ID.
    prova = get_object_or_404(
        Prova,
        id=prova_id
    )

    # ---------------------------------------------------------
    # SEÇÃO 4.1 — PROTEÇÃO CONTRA REPROCESSAMENTO
    # ---------------------------------------------------------

    # Se a prova já foi utilizada em algum simulado,
    # não permitimos apagar e recriar suas questões.
    #
    # Isso protege o histórico dos alunos.
    if prova.simulados.exists():

        messages.error(
            request,
            'Esta prova já possui simulados vinculados '
            'e não pode ser reprocessada para preservar '
            'o histórico dos alunos.'
        )

        return redirect(
            'provas:detalhe',
            prova_id=prova.id
        )

    # ---------------------------------------------------------
    # SEÇÃO 4.2 — VERIFICAÇÃO DO PDF DA PROVA
    # ---------------------------------------------------------

    # Verifica se o PDF da prova foi enviado.
    if not prova.arquivo_pdf:

        messages.error(
            request,
            'Esta prova não possui um PDF.'
        )

        return redirect(
            'provas:detalhe',
            prova_id=prova.id
        )

    # ---------------------------------------------------------
    # SEÇÃO 4.3 — VERIFICAÇÃO DO GABARITO
    # ---------------------------------------------------------

    # Verifica se o PDF do gabarito foi enviado.
    if not prova.arquivo_gabarito:

        messages.error(
            request,
            'Esta prova não possui um PDF de gabarito.'
        )

        return redirect(
            'provas:detalhe',
            prova_id=prova.id
        )

    try:

        # -----------------------------------------------------
        # SEÇÃO 4.4 — MARCA A PROVA COMO PROCESSANDO
        # -----------------------------------------------------

        prova.status_importacao = 'processando'

        # Limpa uma mensagem de erro anterior.
        prova.mensagem_importacao = ''

        # Salva somente esses campos.
        prova.save(
            update_fields=[
                'status_importacao',
                'mensagem_importacao'
            ]
        )

        # -----------------------------------------------------
        # SEÇÃO 4.5 — EXTRAI O TEXTO DO PDF DA PROVA
        # -----------------------------------------------------

        texto_prova = extrair_texto_pdf(
            prova.arquivo_pdf.path
        )

        # -----------------------------------------------------
        # SEÇÃO 4.6 — SEPARA AS QUESTÕES
        # -----------------------------------------------------

        questoes = separar_questoes_enem(
            texto_prova
        )

        # -----------------------------------------------------
        # SEÇÃO 4.7 — EXTRAI O TEXTO DO GABARITO
        # -----------------------------------------------------

        texto_gabarito = extrair_texto_pdf(
            prova.arquivo_gabarito.path
        )

        # -----------------------------------------------------
        # SEÇÃO 4.8 — EXTRAI AS RESPOSTAS DO GABARITO
        # -----------------------------------------------------

        gabarito = extrair_gabarito_enem(
            texto_gabarito
        )

        # -----------------------------------------------------
        # SEÇÃO 4.9 — VALIDA AS QUESTÕES
        # -----------------------------------------------------

        problemas = validar_questoes_com_gabarito(
            questoes,
            gabarito
        )

        # Se existirem problemas, não salva as questões.
        if problemas:

            # Junta todos os problemas em uma única mensagem.
            mensagem = '\n'.join(
                problemas
            )

            # Marca a prova como erro.
            prova.status_importacao = 'erro'

            # Salva os detalhes do problema.
            prova.mensagem_importacao = mensagem

            prova.save(
                update_fields=[
                    'status_importacao',
                    'mensagem_importacao'
                ]
            )

            # Mostra uma mensagem para o usuário.
            messages.error(
                request,
                'A prova não pôde ser processada. '
                'Verifique os detalhes.'
            )

            return redirect(
                'provas:detalhe',
                prova_id=prova.id
            )

        # -----------------------------------------------------
        # SEÇÃO 4.10 — PREPARA AS QUESTÕES
        # -----------------------------------------------------

        questoes_preparadas = (
            preparar_questoes_para_importacao(
                questoes,
                gabarito
            )
        )

        # -----------------------------------------------------
        # SEÇÃO 4.11 — SALVA AS QUESTÕES NO BANCO
        # -----------------------------------------------------

        quantidade = importar_questoes_no_banco(
            prova,
            questoes_preparadas
        )

        # -----------------------------------------------------
        # SEÇÃO 4.12 — SUCESSO
        # -----------------------------------------------------

        messages.success(
            request,
            f'Prova processada com sucesso! '
            f'{quantidade} questões foram importadas.'
        )

    except Exception as erro:

        # -----------------------------------------------------
        # SEÇÃO 4.13 — TRATAMENTO DE ERRO
        # -----------------------------------------------------

        # Marca a prova como erro.
        prova.status_importacao = 'erro'

        # Salva a mensagem técnica do erro.
        prova.mensagem_importacao = str(
            erro
        )

        # Atualiza o banco.
        prova.save(
            update_fields=[
                'status_importacao',
                'mensagem_importacao'
            ]
        )

        # Mostra uma mensagem simples para o usuário.
        messages.error(
            request,
            'Ocorreu um erro durante o processamento da prova.'
        )

    # Volta para a página da prova.
    return redirect(
        'provas:detalhe',
        prova_id=prova.id
    )