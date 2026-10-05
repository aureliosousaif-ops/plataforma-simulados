# ==========================================
# IMPORTAÇÕES
# ==========================================

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from provas.models import Prova, Alternativa

from .models import RespostaSimulado, Simulado


# ==========================================
# LISTA DE SIMULADOS
# ==========================================

def lista(request):
    """
    Mostra as provas disponíveis.

    Esta página é pública.
    Qualquer visitante pode visualizar
    os simulados disponíveis sem fazer login.
    """

    # Busca somente provas ativas e já processadas.
    provas = Prova.objects.filter(
        ativa=True,
        status_importacao='processada'
    )

    # Exibe a lista de provas.
    return render(
        request,
        'simulados/lista.html',
        {
            'provas': provas
        }
    )


# ==========================================
# INICIAR SIMULADO
# ==========================================

def iniciar(request, prova_id):
    """
    Inicia um novo simulado.

    A lista de provas é pública, mas para
    realmente iniciar uma prova o usuário
    precisa estar autenticado.
    """

    # ==========================================
    # VERIFICA LOGIN
    # ==========================================

    if not request.user.is_authenticated:

        # O visitante tentou iniciar um simulado.
        # Guardamos o endereço da prova para que,
        # depois do login, ele possa continuar.
        destino = request.path

        # Envia o visitante para a página de login.
        return redirect(
            f'/usuarios/login/?next={destino}'
        )

    # ==========================================
    # VERIFICA MÉTODO DA REQUISIÇÃO
    # ==========================================

    # O simulado deve ser iniciado através
    # do formulário POST do botão.
    if request.method != 'POST':

        return redirect(
            'simulados:lista'
        )

    # ==========================================
    # BUSCA A PROVA
    # ==========================================

    # Busca somente uma prova válida.
    prova = get_object_or_404(
        Prova,
        id=prova_id,
        ativa=True,
        status_importacao='processada'
    )

    # ==========================================
    # CRIA O SIMULADO
    # ==========================================

    # Cria uma nova tentativa para
    # o usuário atualmente logado.
    simulado = Simulado.objects.create(
        usuario=request.user,
        prova=prova
    )

    # Busca todas as questões ativas
    # pertencentes à prova.
    questoes = prova.questoes.filter(
        ativa=True
    )

    # ==========================================
    # CRIA AS RESPOSTAS
    # ==========================================

    # Cria uma resposta vazia para
    # cada questão do simulado.
    respostas = [
        RespostaSimulado(
            simulado=simulado,
            questao=questao
        )
        for questao in questoes
    ]

    # Salva todas as respostas de uma vez.
    RespostaSimulado.objects.bulk_create(
        respostas
    )

    # ==========================================
    # PRIMEIRA QUESTÃO
    # ==========================================

    # Envia o usuário para a primeira questão.
    return redirect(
        'simulados:responder',
        simulado_id=simulado.id
    )


# ==========================================
# RESPONDER SIMULADO
# ==========================================

@login_required
def responder(request, simulado_id):
    """
    Exibe uma questão e salva a resposta do aluno.
    """

    # ==========================================
    # BUSCA O SIMULADO
    # ==========================================

    # Busca somente o simulado pertencente ao
    # usuário atualmente logado.
    simulado = get_object_or_404(
        Simulado,
        id=simulado_id,
        usuario=request.user
    )

    # ==========================================
    # VERIFICA SE JÁ FOI FINALIZADO
    # ==========================================

    # Se o simulado já foi finalizado,
    # mostra diretamente o resultado.
    if simulado.status == 'finalizado':

        return redirect(
            'simulados:resultado',
            simulado_id=simulado.id
        )

    # ==========================================
    # BUSCA AS RESPOSTAS
    # ==========================================

    # Busca todas as respostas do simulado.
    respostas = list(
        simulado.respostas
        .select_related(
            'questao',
            'questao__disciplina'
        )
        .prefetch_related(
            'questao__alternativas'
        )
        .order_by(
            'questao__numero'
        )
    )

    # ==========================================
    # VERIFICA SE EXISTEM QUESTÕES
    # ==========================================

    # Caso não existam questões,
    # volta para a lista de provas.
    if not respostas:

        return redirect(
            'simulados:lista'
        )

    # ==========================================
    # QUESTÃO ATUAL
    # ==========================================

    # Pega o número da questão pela URL.
    numero = request.GET.get(
        'questao',
        '1'
    )

    # Tenta transformar o número em inteiro.
    try:

        numero = int(numero)

    except (TypeError, ValueError):

        numero = 1

    # Impede número menor que 1.
    if numero < 1:

        numero = 1

    # Impede número maior que o total.
    if numero > len(respostas):

        numero = len(respostas)

    # Seleciona a questão atual.
    resposta_atual = respostas[
        numero - 1
    ]

    # ==========================================
    # INÍCIO DA QUESTÃO
    # ==========================================

    # Registra quando a questão foi visualizada.
    if resposta_atual.iniciada_em is None:

        resposta_atual.iniciada_em = timezone.now()

        resposta_atual.save(
            update_fields=[
                'iniciada_em'
            ]
        )

    # ==========================================
    # TEMPO DO SIMULADO
    # ==========================================

    # Calcula o tempo total desde o início
    # do simulado.
    tempo_decorrido = int(
        (
            timezone.now()
            - simulado.iniciado_em
        ).total_seconds()
    )

    # Evita valores negativos.
    tempo_decorrido = max(
        0,
        tempo_decorrido
    )

    # ==========================================
    # PROCESSAMENTO DO FORMULÁRIO
    # ==========================================

    if request.method == 'POST':

        # Pega a alternativa escolhida.
        alternativa_id = request.POST.get(
            'alternativa'
        )

        # Define a ação solicitada.
        acao = request.POST.get(
            'acao',
            'proxima'
        )

        # ==========================================
        # SALVA A RESPOSTA
        # ==========================================

        if alternativa_id:

            # Busca a alternativa somente dentro
            # da questão atual.
            alternativa = get_object_or_404(
                Alternativa,
                id=alternativa_id,
                questao=resposta_atual.questao
            )

            # Horário atual.
            agora = timezone.now()

            # Salva a alternativa escolhida.
            resposta_atual.alternativa = alternativa

            # Marca como respondida.
            resposta_atual.respondida = True

            # Verifica se a alternativa está correta.
            resposta_atual.correta = alternativa.correta

            # Registra o horário da resposta.
            resposta_atual.respondida_em = agora

            # Calcula o tempo gasto na questão.
            if resposta_atual.iniciada_em:

                tempo_questao = (
                    agora
                    - resposta_atual.iniciada_em
                ).total_seconds()

                resposta_atual.tempo_segundos = max(
                    0,
                    int(tempo_questao)
                )

            # Salva a resposta.
            resposta_atual.save()

        # ==========================================
        # QUESTÃO ANTERIOR
        # ==========================================

        if acao == 'anterior':

            # Só volta se não estiver na primeira questão.
            if numero > 1:

                return redirect(
                    f'/simulados/{simulado.id}/responder/'
                    f'?questao={numero - 1}'
                )

            # Se estiver na primeira,
            # continua na primeira questão.
            return redirect(
                f'/simulados/{simulado.id}/responder/'
                f'?questao=1'
            )

        # ==========================================
        # FINALIZAR
        # ==========================================

        if acao == 'finalizar':

            return finalizar_simulado(
                simulado
            )

        # ==========================================
        # PRÓXIMA QUESTÃO
        # ==========================================

        if acao == 'proxima':

            # Só avança se existir uma próxima questão.
            if numero < len(respostas):

                return redirect(
                    f'/simulados/{simulado.id}/responder/'
                    f'?questao={numero + 1}'
                )

            # Se já estiver na última questão,
            # permanece nela.
            return redirect(
                f'/simulados/{simulado.id}/responder/'
                f'?questao={numero}'
            )

    # ==========================================
    # NAVEGAÇÃO ENTRE QUESTÕES
    # ==========================================

    # Questão anterior.
    resposta_anterior = None

    if numero > 1:

        resposta_anterior = respostas[
            numero - 2
        ]

    # Próxima questão.
    proxima_resposta = None

    if numero < len(respostas):

        proxima_resposta = respostas[
            numero
        ]

    # ==========================================
    # QUESTÕES NÃO RESPONDIDAS
    # ==========================================

    # Conta as questões ainda não respondidas.
    nao_respondidas = sum(
        1
        for resposta in respostas
        if not resposta.respondida
    )

    # ==========================================
    # RENDERIZA A QUESTÃO
    # ==========================================

    return render(
        request,
        'simulados/responder.html',
        {
            # Simulado atual.
            'simulado': simulado,

            # Questão atual.
            'resposta': resposta_atual,

            # Todas as questões.
            'respostas': respostas,

            # Número atual.
            'numero_atual': numero,

            # Total de questões.
            'total_questoes': len(respostas),

            # Tempo total do simulado.
            'tempo_decorrido': tempo_decorrido,

            # Questões ainda não respondidas.
            'nao_respondidas': nao_respondidas,

            # Questão anterior.
            'resposta_anterior': resposta_anterior,

            # Próxima questão.
            'proxima_resposta': proxima_resposta,
        }
    )


# ==========================================
# FINALIZAR SIMULADO
# ==========================================

def finalizar_simulado(simulado):
    """
    Finaliza o simulado e calcula os resultados.

    Também calcula o tempo das questões que foram
    visualizadas, mas não foram respondidas.
    """

    # ==========================================
    # VERIFICA SE JÁ FOI FINALIZADO
    # ==========================================

    if simulado.status == 'finalizado':

        return redirect(
            'simulados:resultado',
            simulado_id=simulado.id
        )

    # Horário da finalização.
    agora = timezone.now()

    # Busca todas as respostas.
    respostas = list(
        simulado.respostas.all()
    )

    # ==========================================
    # ATUALIZA O TEMPO DAS QUESTÕES
    # NÃO RESPONDIDAS
    # ==========================================

    for resposta in respostas:

        # Se a questão foi visualizada,
        # mas não foi respondida, calcula
        # o tempo até a finalização.
        if (
            not resposta.respondida
            and resposta.iniciada_em
        ):

            tempo_questao = (
                agora
                - resposta.iniciada_em
            ).total_seconds()

            resposta.tempo_segundos = max(
                0,
                int(tempo_questao)
            )

            resposta.save(
                update_fields=[
                    'tempo_segundos'
                ]
            )

    # ==========================================
    # RESULTADOS
    # ==========================================

    # Total de questões.
    total = len(respostas)

    # Quantidade respondida.
    respondidas = sum(
        1
        for resposta in respostas
        if resposta.respondida
    )

    # Quantidade de acertos.
    acertos = sum(
        1
        for resposta in respostas
        if (
            resposta.respondida
            and resposta.correta
        )
    )

    # Quantidade de erros.
    erros = sum(
        1
        for resposta in respostas
        if (
            resposta.respondida
            and not resposta.correta
        )
    )

    # Quantidade não respondida.
    nao_respondidas = (
        total
        - respondidas
    )

    # ==========================================
    # TEMPO TOTAL
    # ==========================================

    # Soma o tempo de todas as questões.
    tempo_total = sum(
        resposta.tempo_segundos
        for resposta in respostas
    )

    # ==========================================
    # PERCENTUAL
    # ==========================================

    percentual = 0

    if total:

        percentual = (
            acertos
            / total
        ) * 100

    # ==========================================
    # FINALIZA O SIMULADO
    # ==========================================

    simulado.status = 'finalizado'

    # Registra quando terminou.
    simulado.finalizado_em = agora

    # Salva o tempo total.
    simulado.tempo_total_segundos = tempo_total

    # Salva os acertos.
    simulado.acertos = acertos

    # Salva os erros.
    simulado.erros = erros

    # Salva o percentual.
    simulado.percentual = round(
        percentual,
        2
    )

    # Salva no banco.
    simulado.save()

    # Vai para o resultado.
    return redirect(
        'simulados:resultado',
        simulado_id=simulado.id
    )


# ==========================================
# FINALIZAR PELA URL
# ==========================================

@login_required
def finalizar(request, simulado_id):
    """
    Finaliza o simulado através da URL.
    """

    # A finalização deve acontecer através de POST.
    if request.method != 'POST':

        return redirect(
            'simulados:responder',
            simulado_id=simulado_id
        )

    # Busca o simulado pertencente ao usuário.
    simulado = get_object_or_404(
        Simulado,
        id=simulado_id,
        usuario=request.user
    )

    # Finaliza o simulado.
    return finalizar_simulado(
        simulado
    )


# ==========================================
# RESULTADO
# ==========================================

@login_required
def resultado(request, simulado_id):
    """
    Mostra a análise completa do resultado.
    """

    # Busca somente o simulado finalizado
    # pertencente ao usuário.
    simulado = get_object_or_404(
        Simulado,
        id=simulado_id,
        usuario=request.user,
        status='finalizado'
    )

    # ==========================================
    # BUSCA AS RESPOSTAS
    # ==========================================

    # Busca todas as respostas.
    respostas = list(
        simulado.respostas
        .select_related(
            'questao',
            'questao__disciplina',
            'alternativa'
        )
        .prefetch_related(
            'questao__alternativas'
        )
        .order_by(
            'questao__numero'
        )
    )

    # Total de questões.
    total = len(respostas)

    # Quantidade respondida.
    respondidas = sum(
        1
        for resposta in respostas
        if resposta.respondida
    )

    # Quantidade não respondida.
    nao_respondidas = (
        total
        - respondidas
    )

    # ==========================================
    # DESEMPENHO POR DISCIPLINA
    # ==========================================

    desempenho_disciplinas = {}

    for resposta in respostas:

        # Nome da disciplina.
        disciplina = (
            resposta.questao.disciplina.nome
        )

        # Cria a estrutura da disciplina.
        if disciplina not in desempenho_disciplinas:

            desempenho_disciplinas[disciplina] = {
                'total': 0,
                'acertos': 0,
                'erros': 0,
                'nao_respondidas': 0,
                'percentual': 0,
            }

        # Incrementa o total.
        desempenho_disciplinas[disciplina][
            'total'
        ] += 1

        # Verifica a resposta.
        if not resposta.respondida:

            desempenho_disciplinas[disciplina][
                'nao_respondidas'
            ] += 1

        elif resposta.correta:

            desempenho_disciplinas[disciplina][
                'acertos'
            ] += 1

        else:

            desempenho_disciplinas[disciplina][
                'erros'
            ] += 1

    # Calcula o percentual de cada disciplina.
    for dados in desempenho_disciplinas.values():

        if dados['total']:

            dados['percentual'] = round(
                (
                    dados['acertos']
                    / dados['total']
                ) * 100,
                2
            )

    # ==========================================
    # TEMPO FORMATADO
    # ==========================================

    # Tempo total salvo.
    tempo_total = (
        simulado.tempo_total_segundos
    )

    # Horas.
    horas = tempo_total // 3600

    # Minutos.
    minutos = (
        tempo_total % 3600
    ) // 60

    # Segundos.
    segundos = (
        tempo_total % 60
    )

    # Formato HH:MM:SS.
    tempo_formatado = (
        f'{horas:02d}:'
        f'{minutos:02d}:'
        f'{segundos:02d}'
    )

    # ==========================================
    # RESULTADO
    # ==========================================

    return render(
        request,
        'simulados/resultado.html',
        {
            'simulado': simulado,
            'respostas': respostas,
            'total_questoes': total,
            'respondidas': respondidas,
            'nao_respondidas': nao_respondidas,
            'desempenho_disciplinas': (
                desempenho_disciplinas.items()
            ),
            'tempo_formatado': tempo_formatado,
        }
    )


# ==========================================
# HISTÓRICO
# ==========================================

@login_required
def historico(request):
    """
    Mostra todos os simulados do usuário.

    Aqui aparecem tanto os simulados que ainda
    estão em andamento quanto os finalizados.
    """

    # Busca somente os simulados pertencentes
    # ao usuário atualmente logado.
    simulados = Simulado.objects.filter(
        usuario=request.user
    ).select_related(
        'prova'
    ).order_by(
        '-iniciado_em'
    )

    # Lista que receberá os dados preparados
    # para o template.
    historico_simulados = []

    # Percorre cada simulado.
    for simulado in simulados:

        # ==========================================
        # QUESTÕES
        # ==========================================

        # Total de questões.
        total = simulado.respostas.count()

        # Quantidade de questões respondidas.
        respondidas = simulado.respostas.filter(
            respondida=True
        ).count()

        # Quantidade ainda não respondida.
        nao_respondidas = (
            total
            - respondidas
        )

        # ==========================================
        # TEMPO
        # ==========================================

        # Tempo salvo no banco.
        tempo_total = simulado.tempo_total_segundos

        # Para simulados em andamento, calcula
        # o tempo atual.
        if (
            simulado.status != 'finalizado'
            and simulado.iniciado_em
        ):

            tempo_total = int(
                (
                    timezone.now()
                    - simulado.iniciado_em
                ).total_seconds()
            )

            tempo_total = max(
                0,
                tempo_total
            )

        # Calcula horas.
        horas = tempo_total // 3600

        # Calcula minutos.
        minutos = (
            tempo_total % 3600
        ) // 60

        # Calcula segundos.
        segundos = (
            tempo_total % 60
        )

        # Formato HH:MM:SS.
        tempo_formatado = (
            f'{horas:02d}:'
            f'{minutos:02d}:'
            f'{segundos:02d}'
        )

        # ==========================================
        # ADICIONA AO HISTÓRICO
        # ==========================================

        historico_simulados.append(
            {
                'simulado': simulado,
                'total': total,
                'respondidas': respondidas,
                'nao_respondidas': nao_respondidas,
                'tempo_formatado': tempo_formatado,
            }
        )

    # ==========================================
    # RENDERIZA O HISTÓRICO
    # ==========================================

    return render(
        request,
        'simulados/historico.html',
        {
            'historico_simulados': historico_simulados,
        }
    )