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

    # -----------------------------------------------------
    # Catálogo oficial do ENEM
    # -----------------------------------------------------

    # Identificador estável da prova no catálogo oficial.
    # É usado para evitar duplicações nas importações em lote.
    # Provas cadastradas manualmente permanecem com o campo vazio.
    chave_oficial = models.CharField(
        max_length=80,
        unique=True,
        blank=True,
        null=True
    )

    # Modalidade de aplicação da prova.
    modalidade = models.CharField(
        max_length=20,
        choices=[
            ('regular', 'Regular'),
            ('digital', 'Digital'),
        ],
        blank=True
    )

    # Dia de aplicação da prova.
    dia = models.PositiveSmallIntegerField(
        choices=[
            (1, '1º dia'),
            (2, '2º dia'),
        ],
        blank=True,
        null=True
    )

    # Número do caderno oficial.
    caderno = models.PositiveSmallIntegerField(
        blank=True,
        null=True
    )

    # Cor do caderno oficial.
    cor_caderno = models.CharField(
        max_length=20,
        blank=True
    )

    # Formato de acessibilidade do caderno.
    acessibilidade = models.CharField(
        max_length=20,
        choices=[
            ('padrao', 'Padrão'),
            ('braile_ledor', 'Braille/Ledor'),
            ('libras', 'Libras'),
        ],
        default='padrao'
    )

    # Idioma do caderno, quando a prova é separada por idioma.
    idioma_caderno = models.CharField(
        max_length=30,
        blank=True
    )

    # Links oficiais do INEP para a prova e o gabarito.
    url_prova = models.URLField(
        max_length=500,
        blank=True
    )

    url_gabarito = models.URLField(
        max_length=500,
        blank=True
    )

    # Variante em espanhol dos cadernos digitais do primeiro dia.
    url_prova_espanhol = models.URLField(
        max_length=500,
        blank=True
    )

    url_gabarito_espanhol = models.URLField(
        max_length=500,
        blank=True
    )

    arquivo_pdf_espanhol = models.FileField(
        upload_to='provas/espanhol/',
        blank=True,
        null=True
    )

    arquivo_gabarito_espanhol = models.FileField(
        upload_to='gabaritos/espanhol/',
        blank=True,
        null=True
    )

    # Página oficial de onde os links foram obtidos.
    fonte_url = models.URLField(
        max_length=500,
        blank=True
    )

    # Quantidade de questões confirmada para a prova.
    quantidade_questoes = models.PositiveIntegerField(
        blank=True,
        null=True
    )

    # Indica se a prova foi criada manualmente ou pelo catálogo.
    origem = models.CharField(
        max_length=20,
        choices=[
            ('manual', 'Manual'),
            ('catalogo_oficial', 'Catálogo oficial'),
        ],
        default='manual'
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

    @property
    def area_conhecimento(self):
        """
        Área de conhecimento avaliada no dia da aplicação.
        """
        if self.dia == 1:
            return (
                'Linguagens, Códigos e suas Tecnologias e '
                'Ciências Humanas e suas Tecnologias'
            )

        if self.dia == 2:
            return (
                'Ciências da Natureza e suas Tecnologias e '
                'Matemática e suas Tecnologias'
            )

        return ''

    @property
    def dia_display(self):
        """
        Devolve o dia de aplicação já formatado.
        """
        if self.dia == 1:
            return '1º dia'

        if self.dia == 2:
            return '2º dia'

        return ''

    @property
    def modalidade_display(self):
        """
        Devolve a modalidade já formatada.
        """
        return self.get_modalidade_display() if self.modalidade else ''

    @property
    def caderno_display(self):
        """
        Devolve o caderno no formato usado pelo INEP.
        """
        partes = []

        if self.caderno:
            partes.append(f'Caderno {self.caderno}')

        if self.cor_caderno:
            partes.append(self.cor_caderno)

        if self.origem == 'catalogo_oficial' and self.acessibilidade != 'padrao':
            partes.append(self.get_acessibilidade_display())

        return ' (' + ', '.join(partes) + ')' if partes else ''

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

    # Idioma da variante de língua estrangeira do ENEM.
    # Questões das demais áreas permanecem sem idioma.
    idioma = models.CharField(
        max_length=20,
        choices=[
            ('Inglês', 'Inglês'),
            ('Espanhol', 'Espanhol'),
        ],
        blank=True,
        null=True
    )

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
        ordering = ['prova', 'numero', 'idioma']

        # Impede duas questões com o mesmo número na mesma prova.
        constraints = [
            models.UniqueConstraint(
                fields=['prova', 'numero', 'idioma'],
                name='numero_unico_por_prova_idioma'
            ),
            models.UniqueConstraint(
                fields=['prova', 'numero'],
                condition=models.Q(idioma__isnull=True),
                name='numero_unico_por_prova_sem_idioma'
            )
        ]

    # Nome exibido no Admin.
    def __str__(self):
        idioma = f' ({self.idioma})' if self.idioma else ''
        return f'{self.prova} - Questão {self.numero}{idioma}'

    @property
    def textos_base_exibicao(self):
        """
        Retorna os textos-base compartilhados que devem anteceder esta questão.

        A ordem é controlada pelo vínculo ``QuestaoTextoBase``. Questões
        independentes simplesmente devolvem uma lista vazia.
        """
        return [
            vinculo.texto_base
            for vinculo in self.textos_base_vinculados.all()
        ]

    @property
    def imagens_exibicao(self):
        """
        Retorna as imagens que devem aparecer no simulado e na impressão.

        Prioriza as associações confirmadas e revalida as associações
        automáticas pela geometria do PDF. Caso a questão ainda utilize
        apenas o campo legado ``imagem``, ele é retornado como fallback,
        também sujeito à validação quando a imagem veio do PDF.
        """
        from .imagens import (
            associacao_imagem_segura,
            imagem_legada_segura,
            marcadores_da_prova,
        )

        marcadores = None
        confirmadas = []

        for associacao in self.imagens_associadas.all():
            imagem = associacao.imagem

            if not associacao.confirmada or not imagem.arquivo:
                continue

            if imagem.ignorada or not imagem.exibida:
                continue

            # Imagens usadas como conteúdo de uma alternativa não devem
            # aparecer novamente como imagem do enunciado.
            if imagem.alternativas_como_imagem.exists():
                continue

            if associacao.origem == 'automatica':
                if marcadores is None:
                    marcadores = marcadores_da_prova(self.prova)

                if not associacao_imagem_segura(
                    associacao,
                    marcadores,
                ):
                    continue

            confirmadas.append(imagem.arquivo)

        if confirmadas:
            return confirmadas

        if self.imagem:
            if marcadores is None:
                marcadores = marcadores_da_prova(self.prova)

            if imagem_legada_segura(self, marcadores):
                return [self.imagem]

        return []


# Modelo responsável pelas imagens extraídas do PDF da prova.
class ImagemProva(models.Model):

    # Prova à qual a imagem pertence.
    prova = models.ForeignKey(
        Prova,
        on_delete=models.CASCADE,
        related_name='imagens'
    )

    # Arquivo original extraído do PDF.
    arquivo = models.ImageField(
        upload_to='provas/imagens/'
    )

    # Hash usado para evitar duplicação ao reprocessar o mesmo PDF.
    hash_sha256 = models.CharField(
        max_length=64,
        db_index=True
    )

    # Página em que a imagem foi encontrada (começa em 1).
    pagina = models.PositiveIntegerField(
        default=1
    )

    # Ordem da imagem dentro da página.
    indice_pagina = models.PositiveIntegerField(
        default=0
    )

    # Nome original informado pelo PDF.
    nome_original = models.CharField(
        max_length=255,
        blank=True
    )

    # Dimensões originais da imagem em pixels.
    largura = models.PositiveIntegerField(
        default=0
    )

    altura = models.PositiveIntegerField(
        default=0
    )

    # Indica se a imagem é efetivamente desenhada na página.
    exibida = models.BooleanField(
        default=True
    )

    # Posição e tamanho estimados no sistema de coordenadas do PDF.
    x = models.FloatField(
        blank=True,
        null=True
    )

    y = models.FloatField(
        blank=True,
        null=True
    )

    largura_exibicao = models.FloatField(
        blank=True,
        null=True
    )

    altura_exibicao = models.FloatField(
        blank=True,
        null=True
    )

    # Permite ocultar imagens que não pertencem a nenhuma questão.
    ignorada = models.BooleanField(
        default=False
    )

    # Data em que a imagem foi extraída.
    data_extracao = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ['pagina', 'indice_pagina', 'id']

        constraints = [
            models.UniqueConstraint(
                fields=[
                    'prova',
                    'hash_sha256',
                    'pagina',
                    'indice_pagina',
                ],
                name='imagem_unica_por_prova_hash_pagina'
            )
        ]

    def __str__(self):
        return (
            f'{self.prova} - imagem da página {self.pagina} '
            f'(#{self.indice_pagina})'
        )


# Modelo que associa uma imagem extraída a uma questão.
class ImagemQuestao(models.Model):

    # Origens possíveis de uma associação.
    ORIGENS = [
        ('automatica', 'Automática'),
        ('manual', 'Manual'),
    ]

    # Imagem extraída do PDF.
    imagem = models.ForeignKey(
        ImagemProva,
        on_delete=models.CASCADE,
        related_name='associacoes'
    )

    # Questão à qual a imagem pertence.
    questao = models.ForeignKey(
        Questao,
        on_delete=models.CASCADE,
        related_name='imagens_associadas'
    )

    # Somente associações confirmadas aparecem no simulado.
    confirmada = models.BooleanField(
        default=False
    )

    # Indica se a associação foi sugerida pelo sistema ou feita manualmente.
    origem = models.CharField(
        max_length=20,
        choices=ORIGENS,
        default='manual'
    )

    # Ordem de exibição quando a questão possui várias imagens.
    ordem = models.PositiveIntegerField(
        default=0
    )

    # Datas de controle.
    criada_em = models.DateTimeField(
        auto_now_add=True
    )

    atualizada_em = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ['ordem', 'id']

        constraints = [
            models.UniqueConstraint(
                fields=['imagem', 'questao'],
                name='associacao_unica_imagem_questao'
            ),
            models.UniqueConstraint(
                fields=['imagem'],
                condition=models.Q(confirmada=True),
                name='imagem_confirmada_unica'
            ),
        ]

    def __str__(self):
        return f'{self.imagem} -> {self.questao}'


# Modelo responsável pelos textos-base compartilhados por várias questões.
class TextoBase(models.Model):

    # Prova à qual o texto-base pertence.
    prova = models.ForeignKey(
        Prova,
        on_delete=models.CASCADE,
        related_name='textos_base'
    )

    # Chave estável calculada a partir do conteúdo, usada para evitar
    # duplicação quando a mesma prova é processada mais de uma vez.
    chave = models.CharField(
        max_length=64,
        db_index=True
    )

    # Cabeçalho original, como "Texto para as Questões de 06 a 10.".
    identificador = models.CharField(
        max_length=200,
        blank=True
    )

    # Título curto do texto, como "De próprio punho".
    titulo = models.CharField(
        max_length=200,
        blank=True
    )

    # Conteúdo integral do texto-base.
    texto = models.TextField()

    # Ordem de exibição dentro da prova.
    ordem = models.PositiveIntegerField(
        default=0
    )

    # Data em que o texto-base foi registrado.
    criado_em = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ['ordem', 'id']

        constraints = [
            models.UniqueConstraint(
                fields=['prova', 'chave'],
                name='texto_base_unico_por_prova_chave'
            )
        ]

    def __str__(self):
        return (
            self.titulo
            or self.identificador
            or f'Texto-base #{self.pk}'
        )


# Modelo que associa um texto-base às questões que dependem dele.
class QuestaoTextoBase(models.Model):

    # Texto-base compartilhado.
    texto_base = models.ForeignKey(
        TextoBase,
        on_delete=models.CASCADE,
        related_name='questoes_vinculadas'
    )

    # Questão que utiliza o texto-base.
    questao = models.ForeignKey(
        Questao,
        on_delete=models.CASCADE,
        related_name='textos_base_vinculados'
    )

    # Ordem de exibição quando a questão possui mais de um texto-base.
    ordem = models.PositiveIntegerField(
        default=0
    )

    class Meta:
        ordering = ['ordem', 'id']

        constraints = [
            models.UniqueConstraint(
                fields=['texto_base', 'questao'],
                name='texto_base_unico_por_questao'
            )
        ]

    def __str__(self):
        return f'{self.texto_base} -> {self.questao}'


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

    # Imagem usada como conteúdo da alternativa.
    # Algumas questões do ENEM apresentam as opções apenas como figuras.
    imagem = models.ForeignKey(
        ImagemProva,
        on_delete=models.SET_NULL,
        related_name='alternativas_como_imagem',
        blank=True,
        null=True
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


def distribuir_textos_base(questoes):
    """
    Marca cada questão com os textos-base que ainda não foram exibidos.

    Em telas que mostram todas as questões em sequência (impressão e
    resultado), o mesmo texto-base não deve ser repetido antes de cada
    questão do grupo. A primeira questão do grupo recebe o texto-base;
    as seguintes recebem uma lista vazia.

    O atributo dinâmico ``textos_base_para_exibir`` é lido pelos
    templates.
    """
    vistos = set()

    for questao in questoes:
        exibir = []

        for texto_base in questao.textos_base_exibicao:
            if texto_base.pk in vistos:
                continue

            vistos.add(texto_base.pk)
            exibir.append(texto_base)

        questao.textos_base_para_exibir = exibir

    return questoes


# Modelo que registra uma execução do comando de importação em lote.
class ImportacaoLote(models.Model):

    # Estados possíveis do lote.
    STATUS = [
        ('em_andamento', 'Em andamento'),
        ('concluido', 'Concluído'),
        ('interrompido', 'Interrompido'),
    ]

    # Identificador legível do lote.
    identificador = models.CharField(
        max_length=120,
        unique=True
    )

    # Filtros utilizados na execução.
    ano = models.PositiveIntegerField(
        blank=True,
        null=True
    )

    modalidade = models.CharField(
        max_length=20,
        blank=True
    )

    # Estado atual do lote.
    status = models.CharField(
        max_length=20,
        choices=STATUS,
        default='em_andamento'
    )

    # Resumo final com os totais da execução.
    resumo = models.JSONField(
        default=dict,
        blank=True
    )

    criado_em = models.DateTimeField(
        auto_now_add=True
    )

    atualizado_em = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ['-criado_em']

    def __str__(self):
        return self.identificador


# Modelo que registra o estado de cada prova do catálogo.
# A chave oficial é única para permitir retomar uma importação
# interrompida sem duplicar provas.
class ImportacaoItem(models.Model):

    # Estados possíveis de um item.
    STATUS = [
        ('pendente', 'Pendente'),
        ('cadastrado', 'Cadastrado'),
        ('importado', 'Importado'),
        ('ignorado', 'Ignorado'),
        ('erro', 'Erro'),
    ]

    # Etapas do processamento de um item.
    ETAPAS = [
        ('cadastro', 'Cadastro'),
        ('download', 'Download'),
        ('extracao', 'Extração'),
        ('importacao', 'Importação'),
        ('concluido', 'Concluído'),
    ]

    # Lote que processou o item pela última vez.
    lote = models.ForeignKey(
        ImportacaoLote,
        on_delete=models.SET_NULL,
        related_name='itens',
        blank=True,
        null=True
    )

    # Chave oficial da prova no catálogo.
    chave_oficial = models.CharField(
        max_length=80,
        unique=True
    )

    # Prova criada ou atualizada pelo item.
    prova = models.ForeignKey(
        Prova,
        on_delete=models.SET_NULL,
        related_name='importacoes',
        blank=True,
        null=True
    )

    # Estado e etapa atuais.
    status = models.CharField(
        max_length=20,
        choices=STATUS,
        default='pendente'
    )

    etapa = models.CharField(
        max_length=20,
        choices=ETAPAS,
        default='cadastro'
    )

    # Quantidade de tentativas já realizadas.
    tentativas = models.PositiveIntegerField(
        default=0
    )

    # Mensagem individual de erro ou alerta.
    mensagem = models.TextField(
        blank=True
    )

    # Detalhes estruturados do processamento.
    detalhes = models.JSONField(
        default=dict,
        blank=True
    )

    criado_em = models.DateTimeField(
        auto_now_add=True
    )

    atualizado_em = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ['chave_oficial']

    def __str__(self):
        return f'{self.chave_oficial} ({self.get_status_display()})'
