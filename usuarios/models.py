from django.contrib.auth.models import User
from django.db import models


class Perfil(models.Model):
    TIPOS_USUARIO = [
        ('aluno', 'Aluno'),
        ('professor', 'Professor'),
    ]

    ESCOLARIDADES = [
        ('fundamental', 'Ensino Fundamental'),
        ('medio', 'Ensino Médio'),
        ('superior', 'Ensino Superior'),
        ('pos', 'Pós-graduação'),
        ('outro', 'Outro'),
    ]

    OBJETIVOS = [
        ('enem', 'ENEM'),
        ('vestibular', 'Vestibular'),
        ('concurso', 'Concurso Público'),
        ('exato', 'EXATO'),
        ('ibge', 'IBGE'),
        ('outro', 'Outro'),
    ]

    usuario = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='perfil'
    )

    tipo = models.CharField(
        max_length=20,
        choices=TIPOS_USUARIO,
        default='aluno'
    )

    idade = models.PositiveIntegerField(
        null=True,
        blank=True
    )

    escolaridade = models.CharField(
        max_length=30,
        choices=ESCOLARIDADES,
        blank=True
    )

    objetivo = models.CharField(
        max_length=30,
        choices=OBJETIVOS,
        blank=True
    )

    data_criacao = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return self.usuario.username