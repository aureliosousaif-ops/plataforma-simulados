from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from simulados.models import Simulado


@login_required
def dashboard(request):
    """
    Mostra o painel de desempenho do aluno.

    Os dados são calculados utilizando os simulados
    que já foram finalizados.
    """

    # ==========================================
    # BUSCA OS SIMULADOS
    # ==========================================

    # Busca somente os simulados finalizados
    # pertencentes ao usuário logado.
    simulados = list(
        Simulado.objects.filter(
            usuario=request.user,
            status='finalizado'
        )
        .select_related('prova')
        .prefetch_related(
            'respostas__questao__disciplina'
        )
        .order_by(
            'finalizado_em'
        )
    )

    # ==========================================
    # QUANTIDADE DE SIMULADOS
    # ==========================================

    total_simulados = len(simulados)

    # ==========================================
    # VARIÁVEIS GERAIS
    # ==========================================

    total_acertos = 0
    total_erros = 0
    total_nao_respondidas = 0

    soma_percentuais = 0

    # ==========================================
    # DESEMPENHO POR DISCIPLINA
    # ==========================================

    disciplinas = {}

    # ==========================================
    # EVOLUÇÃO
    # ==========================================

    evolucao = []

    # Percorre os simulados realizados.
    for indice, simulado in enumerate(simulados, start=1):

        # ------------------------------------------
        # RESULTADOS GERAIS
        # ------------------------------------------

        total_acertos += simulado.acertos

        total_erros += simulado.erros

        # Conta as respostas não respondidas.
        total_questoes = simulado.respostas.count()

        respondidas = simulado.respostas.filter(
            respondida=True
        ).count()

        nao_respondidas = (
            total_questoes
            - respondidas
        )

        total_nao_respondidas += (
            nao_respondidas
        )

        # Soma o percentual.
        soma_percentuais += float(
            simulado.percentual
        )

        # ------------------------------------------
        # EVOLUÇÃO
        # ------------------------------------------

        evolucao.append(
            {
                'numero': indice,
                'nome': simulado.prova.nome,
                'percentual': float(
                    simulado.percentual
                ),
                'data': simulado.finalizado_em,
            }
        )

        # ------------------------------------------
        # DISCIPLINAS
        # ------------------------------------------

        # Busca as respostas deste simulado.
        respostas = simulado.respostas.all()

        for resposta in respostas:

            # Nome da disciplina.
            nome_disciplina = (
                resposta.questao.disciplina.nome
            )

            # Cria a disciplina caso ainda não exista.
            if nome_disciplina not in disciplinas:

                disciplinas[nome_disciplina] = {
                    'total': 0,
                    'acertos': 0,
                    'erros': 0,
                    'nao_respondidas': 0,
                    'percentual': 0,
                }

            # Incrementa o total.
            disciplinas[nome_disciplina][
                'total'
            ] += 1

            # Analisa a resposta.
            if not resposta.respondida:

                disciplinas[nome_disciplina][
                    'nao_respondidas'
                ] += 1

            elif resposta.correta:

                disciplinas[nome_disciplina][
                    'acertos'
                ] += 1

            else:

                disciplinas[nome_disciplina][
                    'erros'
                ] += 1

    # ==========================================
    # MÉDIA GERAL
    # ==========================================

    media_percentual = 0

    if total_simulados:

        media_percentual = round(
            soma_percentuais
            / total_simulados,
            2
        )

    # ==========================================
    # PERCENTUAIS DAS DISCIPLINAS
    # ==========================================

    for dados in disciplinas.values():

        if dados['total']:

            dados['percentual'] = round(
                (
                    dados['acertos']
                    / dados['total']
                ) * 100,
                2
            )

    # ==========================================
    # CONVERTE PARA LISTA
    # ==========================================

    desempenho_disciplinas = sorted(
        disciplinas.items()
    )

    # ==========================================
    # ENVIA PARA O TEMPLATE
    # ==========================================

    return render(
        request,
        'desempenho/dashboard.html',
        {
            'total_simulados': total_simulados,
            'media_percentual': media_percentual,
            'total_acertos': total_acertos,
            'total_erros': total_erros,
            'total_nao_respondidas': (
                total_nao_respondidas
            ),
            'desempenho_disciplinas': (
                desempenho_disciplinas
            ),
            'evolucao': evolucao,
        }
    )