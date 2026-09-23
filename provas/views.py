# Importa mensagens para mostrar informações ao usuário.
from django.contrib import messages

# Permite exigir autenticação.
from django.contrib.auth.decorators import login_required

# Exceção utilizada para bloquear usuários sem permissão.
from django.core.exceptions import PermissionDenied

# Funções auxiliares do Django.
from django.shortcuts import get_object_or_404, redirect, render

# Importa os formulários.
from .forms import (
    AlternativaForm,
    AlternativasForm,
    DisciplinaForm,
    ProvaForm,
    QuestaoForm,
)

# Importa os modelos.
from .models import (
    Alternativa,
    Disciplina,
    Prova,
    Questao,
)


# Verifica se o usuário é desenvolvedor.
def desenvolvedor_required(view_function):

    # Função executada antes da view.
    def wrapper(request, *args, **kwargs):

        # Verifica se o usuário está autenticado.
        if not request.user.is_authenticated:
            return redirect('usuarios:login')

        # Verifica se o perfil existe.
        if not hasattr(request.user, 'perfil'):
            raise PermissionDenied

        # Verifica o tipo de usuário.
        if request.user.perfil.tipo != 'desenvolvedor':
            raise PermissionDenied

        # Executa a view original.
        return view_function(request, *args, **kwargs)

    # Mantém o nome da função.
    wrapper.__name__ = view_function.__name__

    return wrapper


# ==========================================================
# PROVAS
# ==========================================================


# Lista as provas.
@login_required
def lista_provas(request):

    # Busca todas as provas.
    provas = Prova.objects.all()

    # Renderiza a página.
    return render(
        request,
        'provas/lista.html',
        {
            'provas': provas,
        }
    )


# Cria uma prova.
@login_required
@desenvolvedor_required
def criar_prova(request):

    # Verifica o envio do formulário.
    if request.method == 'POST':

        # Carrega os dados enviados.
        form = ProvaForm(
            request.POST,
            request.FILES
        )

        # Valida os dados.
        if form.is_valid():

            # Salva a prova.
            form.save()

            # Mostra mensagem.
            messages.success(
                request,
                'Prova criada com sucesso!'
            )

            # Volta para a lista.
            return redirect('provas:lista')

    else:

        # Cria formulário vazio.
        form = ProvaForm()

    # Exibe o formulário.
    return render(
        request,
        'provas/form.html',
        {
            'form': form,
            'titulo': 'Criar prova',
        }
    )


# Edita uma prova.
@login_required
@desenvolvedor_required
def editar_prova(request, prova_id):

    # Busca a prova.
    prova = get_object_or_404(
        Prova,
        id=prova_id
    )

    # Verifica o envio.
    if request.method == 'POST':

        # Carrega os dados.
        form = ProvaForm(
            request.POST,
            request.FILES,
            instance=prova
        )

        # Valida os dados.
        if form.is_valid():

            # Salva as alterações.
            form.save()

            # Mostra mensagem.
            messages.success(
                request,
                'Prova atualizada com sucesso!'
            )

            # Volta para a lista.
            return redirect('provas:lista')

    else:

        # Carrega os dados atuais.
        form = ProvaForm(
            instance=prova
        )

    # Exibe o formulário.
    return render(
        request,
        'provas/form.html',
        {
            'form': form,
            'titulo': 'Editar prova',
            'prova': prova,
        }
    )


# Exclui uma prova.
@login_required
@desenvolvedor_required
def excluir_prova(request, prova_id):

    # Busca a prova.
    prova = get_object_or_404(
        Prova,
        id=prova_id
    )

    # Confirma a exclusão.
    if request.method == 'POST':

        # Guarda o nome.
        nome = prova.nome

        # Exclui a prova.
        prova.delete()

        # Mostra mensagem.
        messages.success(
            request,
            f'Prova "{nome}" excluída com sucesso!'
        )

        # Volta para a lista.
        return redirect('provas:lista')

    # Exibe confirmação.
    return render(
        request,
        'provas/excluir.html',
        {
            'prova': prova,
        }
    )


# ==========================================================
# DISCIPLINAS
# ==========================================================


# Lista disciplinas.
@login_required
def lista_disciplinas(request):

    # Busca todas as disciplinas.
    disciplinas = Disciplina.objects.all()

    # Renderiza a página.
    return render(
        request,
        'provas/disciplinas.html',
        {
            'disciplinas': disciplinas,
        }
    )


# Cria uma disciplina.
@login_required
@desenvolvedor_required
def criar_disciplina(request):

    # Verifica o envio.
    if request.method == 'POST':

        # Carrega os dados.
        form = DisciplinaForm(
            request.POST
        )

        # Valida os dados.
        if form.is_valid():

            # Salva a disciplina.
            form.save()

            # Mostra mensagem.
            messages.success(
                request,
                'Disciplina criada com sucesso!'
            )

            # Volta para a lista.
            return redirect(
                'provas:disciplinas'
            )

    else:

        # Cria formulário vazio.
        form = DisciplinaForm()

    # Exibe o formulário.
    return render(
        request,
        'provas/form.html',
        {
            'form': form,
            'titulo': 'Criar disciplina',
        }
    )


# Edita uma disciplina.
@login_required
@desenvolvedor_required
def editar_disciplina(request, disciplina_id):

    # Busca a disciplina.
    disciplina = get_object_or_404(
        Disciplina,
        id=disciplina_id
    )

    # Verifica o envio.
    if request.method == 'POST':

        # Carrega os dados.
        form = DisciplinaForm(
            request.POST,
            instance=disciplina
        )

        # Valida os dados.
        if form.is_valid():

            # Salva as alterações.
            form.save()

            # Mostra mensagem.
            messages.success(
                request,
                'Disciplina atualizada com sucesso!'
            )

            # Volta para a lista.
            return redirect(
                'provas:disciplinas'
            )

    else:

        # Carrega os dados atuais.
        form = DisciplinaForm(
            instance=disciplina
        )

    # Exibe o formulário.
    return render(
        request,
        'provas/form.html',
        {
            'form': form,
            'titulo': 'Editar disciplina',
        }
    )


# Exclui uma disciplina.
@login_required
@desenvolvedor_required
def excluir_disciplina(request, disciplina_id):

    # Busca a disciplina.
    disciplina = get_object_or_404(
        Disciplina,
        id=disciplina_id
    )

    # Confirma a exclusão.
    if request.method == 'POST':

        # Guarda o nome.
        nome = disciplina.nome

        # Exclui a disciplina.
        disciplina.delete()

        # Mostra mensagem.
        messages.success(
            request,
            f'Disciplina "{nome}" excluída com sucesso!'
        )

        # Volta para a lista.
        return redirect(
            'provas:disciplinas'
        )

    # Exibe confirmação.
    return render(
        request,
        'provas/excluir_disciplina.html',
        {
            'disciplina': disciplina,
        }
    )


# ==========================================================
# QUESTÕES
# ==========================================================


# Lista todas as questões.
@login_required
def lista_questoes(request):

    # Busca questões com prova e disciplina.
    questoes = Questao.objects.select_related(
        'prova',
        'disciplina'
    ).all()

    # Renderiza a página.
    return render(
        request,
        'provas/questoes.html',
        {
            'questoes': questoes,
        }
    )


# Cria uma questão.
@login_required
@desenvolvedor_required
def criar_questao(request):

    # Verifica o envio do formulário.
    if request.method == 'POST':

        # Carrega os dados.
        form = QuestaoForm(
            request.POST,
            request.FILES
        )

        # Valida os dados.
        if form.is_valid():

            # Salva a questão.
            questao = form.save()

            # Mostra mensagem.
            messages.success(
                request,
                'Questão criada com sucesso!'
            )

            # Vai para o cadastro das alternativas.
            return redirect(
                'provas:alternativas',
                questao_id=questao.id
            )

    else:

        # Cria formulário vazio.
        form = QuestaoForm()

    # Exibe o formulário.
    return render(
        request,
        'provas/form.html',
        {
            'form': form,
            'titulo': 'Criar questão',
        }
    )


# ==========================================================
# ALTERNATIVAS
# ==========================================================


# Lista as alternativas da questão.
@login_required
@desenvolvedor_required
def lista_alternativas(request, questao_id):

    # Busca a questão.
    questao = get_object_or_404(
        Questao,
        id=questao_id
    )

    # Busca as alternativas.
    alternativas = questao.alternativas.all()

    # Renderiza a página.
    return render(
        request,
        'provas/alternativas.html',
        {
            'questao': questao,
            'alternativas': alternativas,
        }
    )


# Cria as cinco alternativas de uma vez.
@login_required
@desenvolvedor_required
def criar_alternativas(request, questao_id):

    # Busca a questão.
    questao = get_object_or_404(
        Questao,
        id=questao_id
    )

    # Verifica se já existem alternativas.
    alternativas_existentes = questao.alternativas.exists()

    # Se já existirem, não permite duplicar.
    if alternativas_existentes:

        messages.warning(
            request,
            'Esta questão já possui alternativas cadastradas.'
        )

        return redirect(
            'provas:alternativas',
            questao_id=questao.id
        )

    # Verifica o envio.
    if request.method == 'POST':

        # Carrega os dados enviados.
        form = AlternativasForm(
            request.POST
        )

        # Valida o formulário.
        if form.is_valid():

            # Obtém a alternativa correta.
            correta = form.cleaned_data['correta']

            # Define os textos das alternativas.
            dados = {
                'A': form.cleaned_data['alternativa_a'],
                'B': form.cleaned_data['alternativa_b'],
                'C': form.cleaned_data['alternativa_c'],
                'D': form.cleaned_data['alternativa_d'],
                'E': form.cleaned_data['alternativa_e'],
            }

            # Cria as cinco alternativas.
            for letra, texto in dados.items():

                # Salva cada alternativa.
                Alternativa.objects.create(
                    questao=questao,
                    letra=letra,
                    texto=texto,
                    correta=(letra == correta)
                )

            # Mostra mensagem.
            messages.success(
                request,
                'As cinco alternativas foram cadastradas com sucesso!'
            )

            # Volta para a questão.
            return redirect(
                'provas:alternativas',
                questao_id=questao.id
            )

    else:

        # Cria formulário vazio.
        form = AlternativasForm()

    # Exibe o formulário.
    return render(
        request,
        'provas/alternativas_form.html',
        {
            'form': form,
            'questao': questao,
        }
    )


# Mantém o cadastro individual de alternativa disponível.
@login_required
@desenvolvedor_required
def criar_alternativa(request, questao_id):

    # Busca a questão.
    questao = get_object_or_404(
        Questao,
        id=questao_id
    )

    # Verifica o envio.
    if request.method == 'POST':

        # Carrega os dados.
        form = AlternativaForm(
            request.POST
        )

        # Valida os dados.
        if form.is_valid():

            # Cria a alternativa sem salvar.
            alternativa = form.save(
                commit=False
            )

            # Vincula a questão.
            alternativa.questao = questao

            # Salva a alternativa.
            alternativa.save()

            # Mostra mensagem.
            messages.success(
                request,
                'Alternativa adicionada com sucesso!'
            )

            # Volta para a questão.
            return redirect(
                'provas:alternativas',
                questao_id=questao.id
            )

    else:

        # Cria formulário vazio.
        form = AlternativaForm()

    # Exibe o formulário.
    return render(
        request,
        'provas/form.html',
        {
            'form': form,
            'titulo': 'Criar alternativa',
            'questao': questao,
        }
    )