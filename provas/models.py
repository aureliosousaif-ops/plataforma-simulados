from django.db import models


class Prova(models.Model):
    # Tipos de provas disponíveis na plataforma.
    TIPOS = [
        ('enem', 'ENEM'),
        ('exato', 'EXATO'),
        ('vestibular', 'Vestibular'),
        ('concurso', 'Concurso Público'),
        ('ibge', 'IBGE'),
        ('outro', 'Outro'),
    ]

    # Estados possíveis do processamento automático.
    STATUS_IMPORTACAO = [
        ('pendente', 'Pendente'),
        ('processando', 'Processando'),
        ('processada', 'Processada'),
        ('erro', 'Erro'),
    ]

    # Nome da prova.
    nome = models.CharField(
        max_length=200
    )

    # Tipo da prova.
    tipo = models.CharField(
        max_length=30,
        choices=TIPOS
    )

    # Ano da prova.
    ano = models.PositiveIntegerField()

    # Descrição opcional.
    descricao = models.TextField(
        blank=True
    )

    # PDF principal da prova.
    arquivo_pdf = models.FileField(
        upload_to='provas/',
        blank=True,
        null=True
    )

    # PDF separado do gabarito, caso exista.
    arquivo_gabarito = models.FileField(
        upload_to='gabaritos/',
        blank=True,
        null=True
    )

    # Indica se a prova pode ser utilizada na plataforma.
    ativa = models.BooleanField(
        default=True
    )

    # Estado atual da importação automática.
    status_importacao = models.CharField(
        max_length=20,
        choices=STATUS_IMPORTACAO,
        default='pendente'
    )

    # Guarda uma mensagem caso aconteça algum problema no processamento.
    mensagem_importacao = models.TextField(
        blank=True
    )

    # Guarda a data e hora em que a prova foi processada.
    data_processamento = models.DateTimeField(
        blank=True,
        null=True
    )

    # Data em que a prova foi cadastrada.
    data_criacao = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        # Mostra primeiro as provas mais recentes.
        ordering = ['-ano', 'nome']

    def __str__(self):
        # Nome que será exibido para a prova.
        return f'{self.nome} - {self.ano}'

# Modelo responsável pelas disciplinas.
class Disciplina(models.Model):

    # Nome da disciplina.
    nome = models.CharField(
        max_length=100,
        unique=True
    )

    # Descrição opcional da disciplina.
    descricao = models.TextField(
        blank=True
    )

    # Ordena as disciplinas alfabeticamente.
    class Meta:
        ordering = ['nome']

    # Nome exibido no Admin.
    def __str__(self):
        return self.nome


# Modelo responsável pelas questões das provas.
class Questao(models.Model):

    # Níveis de dificuldade disponíveis.
    DIFICULDADES = [
        ('facil', 'Fácil'),
        ('media', 'Média'),
        ('dificil', 'Difícil'),
    ]

    # Prova à qual a questão pertence.
    prova = models.ForeignKey(
        Prova,
        on_delete=models.CASCADE,
        related_name='questoes'
    )

    # Disciplina da questão.
    disciplina = models.ForeignKey(
        Disciplina,
        on_delete=models.PROTECT,
        related_name='questoes'
    )

    # Número da questão dentro da prova.
    numero = models.PositiveIntegerField()

    # Texto principal da questão.
    enunciado = models.TextField()

    # Nível de dificuldade.
    dificuldade = models.CharField(
        max_length=20,
        choices=DIFICULDADES,
        default='media'
    )

    # Imagem opcional utilizada na questão.
    imagem = models.ImageField(
        upload_to='questoes/',
        blank=True,
        null=True
    )

    # Permite ativar/desativar uma questão.
    ativa = models.BooleanField(
        default=True
    )

    # Configurações adicionais do modelo.
    class Meta:
        # Ordena as questões pela prova e pelo número.
        ordering = ['prova', 'numero']

        # Impede duas questões com o mesmo número na mesma prova.
        constraints = [
            models.UniqueConstraint(
                fields=['prova', 'numero'],
                name='numero_unico_por_prova'
            )
        ]

    # Nome exibido no Admin.
    def __str__(self):
        return f'{self.prova} - Questão {self.numero}'


# Modelo responsável pelas alternativas das questões.
class Alternativa(models.Model):

    # Letras disponíveis para as alternativas.
    LETRAS = [
        ('A', 'A'),
        ('B', 'B'),
        ('C', 'C'),
        ('D', 'D'),
        ('E', 'E'),
    ]

    # Questão à qual a alternativa pertence.
    questao = models.ForeignKey(
        Questao,
        on_delete=models.CASCADE,
        related_name='alternativas'
    )

    # Letra da alternativa.
    letra = models.CharField(
        max_length=1,
        choices=LETRAS
    )

    # Texto da alternativa.
    texto = models.TextField()

    # Define se essa é a alternativa correta.
    correta = models.BooleanField(
        default=False
    )

    # Configurações adicionais.
    class Meta:
        # Ordena as alternativas pela letra.
        ordering = ['letra']

        # Impede duas alternativas com a mesma letra na questão.
        constraints = [
            models.UniqueConstraint(
                fields=['questao', 'letra'],
                name='letra_unica_por_questao'
            )
        ]

    # Nome exibido no Admin.
    def __str__(self):
        return f'{self.letra} - {self.questao}'