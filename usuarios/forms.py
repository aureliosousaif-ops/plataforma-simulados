from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm

from .models import Perfil


class CadastroForm(UserCreationForm):
    """
    Formulário de cadastro dos alunos.

    Todo cadastro público começa automaticamente
    como aluno.
    """

    email = forms.EmailField(
        required=True,
        label='E-mail'
    )

    idade = forms.IntegerField(
        required=False,
        min_value=10,
        max_value=100,
        label='Idade'
    )

    escolaridade = forms.ChoiceField(
        choices=Perfil.ESCOLARIDADES,
        required=False,
        label='Escolaridade'
    )

    objetivo = forms.ChoiceField(
        choices=Perfil.OBJETIVOS,
        required=False,
        label='Objetivo de estudo'
    )

    # Campo da senha.
    #
    # Não exige número, símbolo, letra maiúscula
    # nem quantidade mínima de caracteres.
    password1 = forms.CharField(
        label='Senha',
        widget=forms.PasswordInput(
            attrs={
                'class': 'form-control',
                'placeholder': 'Digite sua senha',
            }
        ),
        help_text=(
            'Dica: evite usar informações fáceis de adivinhar.'
        )
    )

    # Confirmação da senha.
    password2 = forms.CharField(
        label='Confirme a senha',
        widget=forms.PasswordInput(
            attrs={
                'class': 'form-control',
                'placeholder': 'Digite a senha novamente',
            }
        ),
        help_text='Digite a mesma senha novamente.'
    )

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

    def validate_password(self, password, user=None):
        """
        Desativa os validadores de senha do Django.

        Assim, não serão exibidos erros como:

        - A senha é muito comum.
        - A senha é muito parecida com o nome de usuário.
        - A senha é muito curta.
        - A senha precisa conter determinados caracteres.
        """

        # Não executa os validadores padrão do Django.
        return

    def clean_password2(self):
        """
        Verifica somente se as duas senhas são iguais.
        """

        password1 = self.cleaned_data.get(
            'password1'
        )

        password2 = self.cleaned_data.get(
            'password2'
        )

        if not password1 or not password2:

            raise forms.ValidationError(
                'Digite a senha nos dois campos.'
            )

        if password1 != password2:

            raise forms.ValidationError(
                'As senhas não são iguais.'
            )

        return password2

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