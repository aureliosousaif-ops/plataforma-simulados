from django.contrib.auth.models import User
from django.db import models

from provas.models import Prova, Questao, Alternativa


class Simulado(models.Model):
    """
    Representa uma tentativa de uma prova feita por um aluno.
    """

    STATUS = [
        ('em_andamento', 'Em andamento'),
        ('finalizado', 'Finalizado'),
    ]

    usuario = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='simulados'
    )

    prova = models.ForeignKey(
        Prova,
        on_delete=models.PROTECT,
        related_name='simulados'
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS,
        default='em_andamento'
    )

    iniciado_em = models.DateTimeField(
        auto_now_add=True
    )

    finalizado_em = models.DateTimeField(
        null=True,
        blank=True
    )

    tempo_total_segundos = models.PositiveIntegerField(
        default=0
    )

    acertos = models.PositiveIntegerField(
        default=0
    )

    erros = models.PositiveIntegerField(
        default=0
    )

    percentual = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0
    )

    class Meta:
        ordering = ['-iniciado_em']

    def __str__(self):
        return (
            f'{self.usuario.username} - '
            f'{self.prova.nome}'
        )


class RespostaSimulado(models.Model):
    """
    Armazena a resposta dada pelo aluno para cada questão.
    """

    simulado = models.ForeignKey(
        Simulado,
        on_delete=models.CASCADE,
        related_name='respostas'
    )

    questao = models.ForeignKey(
        Questao,
        on_delete=models.PROTECT,
        related_name='respostas_simulados'
    )

    alternativa = models.ForeignKey(
        Alternativa,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='respostas_simulados'
    )

    respondida = models.BooleanField(
        default=False
    )

    correta = models.BooleanField(
        default=False
    )

    iniciada_em = models.DateTimeField(
        null=True,
        blank=True
    )

    respondida_em = models.DateTimeField(
        null=True,
        blank=True
    )

    tempo_segundos = models.PositiveIntegerField(
        default=0
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['simulado', 'questao'],
                name='questao_unica_por_simulado'
            )
        ]

        ordering = ['questao__numero']

    def __str__(self):
        return (
            f'{self.simulado} - '
            f'Questão {self.questao.numero}'
        )