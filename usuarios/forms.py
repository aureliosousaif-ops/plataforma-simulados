from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm

from .models import Perfil


class CadastroForm(UserCreationForm):
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

    tipo = forms.ChoiceField(
        choices=Perfil.TIPOS_USUARIO,
        initial='aluno',
        label='Tipo de usuário'
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
            'tipo',
        ]

        labels = {
            'username': 'Nome de usuário',
        }

    def save(self, commit=True):
        usuario = super().save(commit)

        usuario.email = self.cleaned_data['email']

        if commit:
            usuario.save()

            perfil = usuario.perfil
            perfil.idade = self.cleaned_data['idade']
            perfil.escolaridade = self.cleaned_data['escolaridade']
            perfil.objetivo = self.cleaned_data['objetivo']
            perfil.tipo = self.cleaned_data['tipo']
            perfil.save()

        return usuario