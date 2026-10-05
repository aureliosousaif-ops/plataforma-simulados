# =========================================================
# IMPORTAÇÕES
# =========================================================

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm

from .models import Perfil


# =========================================================
# SEÇÃO 1 — FORMULÁRIO DE CADASTRO
# =========================================================

class CadastroForm(UserCreationForm):
    """
    Formulário utilizado para cadastrar novos alunos.
    """

    # ---------------------------------------------------------
    # E-MAIL
    # ---------------------------------------------------------

    email = forms.EmailField(
        required=True,
        label='E-mail'
    )

    # ---------------------------------------------------------
    # IDADE
    # ---------------------------------------------------------

    idade = forms.IntegerField(
        required=False,
        min_value=10,
        max_value=100,
        label='Idade'
    )

    # ---------------------------------------------------------
    # ESCOLARIDADE
    # ---------------------------------------------------------

    escolaridade = forms.ChoiceField(
        choices=Perfil.ESCOLARIDADES,
        required=False,
        label='Escolaridade'
    )

    # ---------------------------------------------------------
    # OBJETIVO
    # ---------------------------------------------------------

    objetivo = forms.ChoiceField(
        choices=Perfil.OBJETIVOS,
        required=False,
        label='Objetivo de estudo'
    )

    # ---------------------------------------------------------
    # SENHA
    # ---------------------------------------------------------

    password1 = forms.CharField(
        label='Senha',
        widget=forms.PasswordInput(
            attrs={
                'class': 'form-control',
                'placeholder': 'Digite sua senha'
            }
        ),
        help_text=(
            'Escolha uma senha que você consiga lembrar.'
        )
    )

    # ---------------------------------------------------------
    # CONFIRMAÇÃO DA SENHA
    # ---------------------------------------------------------

    password2 = forms.CharField(
        label='Confirme a senha',
        widget=forms.PasswordInput(
            attrs={
                'class': 'form-control',
                'placeholder': 'Digite a senha novamente'
            }
        ),
        help_text='Digite a mesma senha novamente.'
    )

    # =========================================================
    # CONFIGURAÇÃO DO FORMULÁRIO
    # =========================================================

    class Meta:

        model = User

        fields = [
            'username',
            'email',
            'password1',
            'password2',
            'idade',
            'escolaridade',
            'objetivo',
        ]

        labels = {
            'username': 'Nome de usuário'
        }

    # =========================================================
    # VALIDAÇÃO DA SENHA
    # =========================================================

    def validate_password(self, password, user=None):
        """
        Mantém a senha sem os validadores extras
        configurados pelo Django.
        """

        return

    # =========================================================
    # CONFIRMAÇÃO DA SENHA
    # =========================================================

    def clean_password2(self):
        """
        Verifica se as duas senhas são iguais.
        """

        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')

        # Verifica se os dois campos foram preenchidos.
        if not password1 or not password2:

            raise forms.ValidationError(
                'Digite a senha nos dois campos.'
            )

        # Compara as duas senhas.
        if password1 != password2:

            raise forms.ValidationError(
                'As senhas não são iguais.'
            )

        return password2

    # =========================================================
    # SALVAMENTO
    # =========================================================

    def save(self, commit=True):
        """
        Cria o usuário e seu perfil automaticamente.
        """

        # Cria o usuário sem salvar imediatamente.
        usuario = super().save(commit=False)

        # Salva o e-mail.
        usuario.email = self.cleaned_data['email']

        if commit:

            # Salva o usuário.
            usuario.save()

            # Cria automaticamente o perfil como aluno.
            Perfil.objects.create(
                usuario=usuario,
                tipo='aluno',
                idade=self.cleaned_data.get('idade'),
                escolaridade=self.cleaned_data.get(
                    'escolaridade'
                ),
                objetivo=self.cleaned_data.get(
                    'objetivo'
                )
            )

        return usuario