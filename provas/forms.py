# Importa o sistema de formulários do Django.
from django import forms

# Importa os modelos utilizados pelos formulários.
from .models import (
    Alternativa,
    Disciplina,
    Prova,
    Questao,
)
class ProvaForm(forms.ModelForm):
    class Meta:
        model = Prova

        # Campos que o desenvolvedor poderá preencher.
        fields = [
            'nome',
            'tipo',
            'ano',
            'descricao',
            'arquivo_pdf',
            'arquivo_gabarito',
            'ativa',
        ]

        # Nomes exibidos na tela.
        labels = {
            'nome': 'Nome da prova',
            'tipo': 'Tipo de prova',
            'ano': 'Ano',
            'descricao': 'Descrição',
            'arquivo_pdf': 'PDF da prova',
            'arquivo_gabarito': 'PDF do gabarito',
            'ativa': 'Prova ativa',
        }

        # Aparência dos campos.
        widgets = {
            'nome': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Ex.: ENEM 2025'
                }
            ),

            'tipo': forms.Select(
                attrs={
                    'class': 'form-select'
                }
            ),

            'ano': forms.NumberInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Ex.: 2025',
                    'min': 1900,
                    'max': 2100
                }
            ),

            'descricao': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 4,
                    'placeholder': 'Descreva a prova...'
                }
            ),

            'arquivo_pdf': forms.ClearableFileInput(
                attrs={
                    'class': 'form-control',
                    'accept': '.pdf,application/pdf'
                }
            ),

            'arquivo_gabarito': forms.ClearableFileInput(
                attrs={
                    'class': 'form-control',
                    'accept': '.pdf,application/pdf'
                }
            ),

            'ativa': forms.CheckboxInput(
                attrs={
                    'class': 'form-check-input'
                }
            ),
        }

    def clean_arquivo_pdf(self):
        # Recupera o arquivo enviado.
        arquivo = self.cleaned_data.get('arquivo_pdf')

        # Se não houver arquivo, deixa a validação padrão continuar.
        if not arquivo:
            return arquivo

        # Verifica a extensão.
        if not arquivo.name.lower().endswith('.pdf'):
            raise forms.ValidationError(
                'O arquivo da prova deve estar no formato PDF.'
            )

        return arquivo

    def clean_arquivo_gabarito(self):
        # Recupera o gabarito enviado.
        arquivo = self.cleaned_data.get('arquivo_gabarito')

        # O gabarito é opcional nesta etapa.
        if not arquivo:
            return arquivo

        # Verifica a extensão.
        if not arquivo.name.lower().endswith('.pdf'):
            raise forms.ValidationError(
                'O arquivo do gabarito deve estar no formato PDF.'
            )

        return arquivo

# Formulário utilizado para criar e editar disciplinas.
class DisciplinaForm(forms.ModelForm):

    class Meta:
        # Define o modelo utilizado.
        model = Disciplina

        # Define os campos disponíveis.
        fields = [
            'nome',
            'descricao',
        ]

        # Define os nomes exibidos na tela.
        labels = {
            'nome': 'Nome da disciplina',
            'descricao': 'Descrição',
        }

        # Define os componentes HTML.
        widgets = {
            'nome': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Ex.: Matemática',
                }
            ),

            'descricao': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 4,
                    'placeholder': 'Descreva a disciplina...',
                }
            ),
        }


# Formulário utilizado para criar e editar questões.
class QuestaoForm(forms.ModelForm):

    class Meta:
        # Define o modelo utilizado.
        model = Questao

        # Define os campos disponíveis.
        fields = [
            'prova',
            'disciplina',
            'numero',
            'enunciado',
            'dificuldade',
            'imagem',
            'ativa',
        ]

        # Define os nomes exibidos.
        labels = {
            'prova': 'Prova',
            'disciplina': 'Disciplina',
            'numero': 'Número da questão',
            'enunciado': 'Enunciado',
            'dificuldade': 'Dificuldade',
            'imagem': 'Imagem da questão',
            'ativa': 'Questão ativa',
        }

        # Define os componentes HTML.
        widgets = {
            'prova': forms.Select(
                attrs={
                    'class': 'form-select',
                }
            ),

            'disciplina': forms.Select(
                attrs={
                    'class': 'form-select',
                }
            ),

            'numero': forms.NumberInput(
                attrs={
                    'class': 'form-control',
                    'min': 1,
                }
            ),

            'enunciado': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 8,
                    'placeholder': 'Digite o enunciado da questão...',
                }
            ),

            'dificuldade': forms.Select(
                attrs={
                    'class': 'form-select',
                }
            ),

            'imagem': forms.ClearableFileInput(
                attrs={
                    'class': 'form-control',
                    'accept': 'image/*',
                }
            ),
        }


# Formulário utilizado para cada alternativa.
class AlternativaForm(forms.ModelForm):

    class Meta:
        # Define o modelo utilizado.
        model = Alternativa

        # Define os campos disponíveis.
        fields = [
            'letra',
            'texto',
            'correta',
        ]

        # Define os nomes exibidos.
        labels = {
            'letra': 'Alternativa',
            'texto': 'Texto',
            'correta': 'Resposta correta',
        }

        # Define os componentes HTML.
        widgets = {
            'letra': forms.Select(
                attrs={
                    'class': 'form-select',
                }
            ),

            'texto': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Digite o texto da alternativa...',
                }
            ),

            'correta': forms.CheckboxInput(
                attrs={
                    'class': 'form-check-input',
                }
            ),
        }


# Formulário utilizado para cadastrar as cinco alternativas.
class AlternativasForm(forms.Form):

    # Texto da alternativa A.
    alternativa_a = forms.CharField(
        label='Alternativa A',
        max_length=1000,
        widget=forms.TextInput(
            attrs={
                'class': 'form-control',
                'placeholder': 'Digite a alternativa A...',
            }
        )
    )

    # Texto da alternativa B.
    alternativa_b = forms.CharField(
        label='Alternativa B',
        max_length=1000,
        widget=forms.TextInput(
            attrs={
                'class': 'form-control',
                'placeholder': 'Digite a alternativa B...',
            }
        )
    )

    # Texto da alternativa C.
    alternativa_c = forms.CharField(
        label='Alternativa C',
        max_length=1000,
        widget=forms.TextInput(
            attrs={
                'class': 'form-control',
                'placeholder': 'Digite a alternativa C...',
            }
        )
    )

    # Texto da alternativa D.
    alternativa_d = forms.CharField(
        label='Alternativa D',
        max_length=1000,
        widget=forms.TextInput(
            attrs={
                'class': 'form-control',
                'placeholder': 'Digite a alternativa D...',
            }
        )
    )

    # Texto da alternativa E.
    alternativa_e = forms.CharField(
        label='Alternativa E',
        max_length=1000,
        widget=forms.TextInput(
            attrs={
                'class': 'form-control',
                'placeholder': 'Digite a alternativa E...',
            }
        )
    )

    # Define qual alternativa é correta.
    correta = forms.ChoiceField(
        label='Resposta correta',
        choices=[
            ('A', 'Alternativa A'),
            ('B', 'Alternativa B'),
            ('C', 'Alternativa C'),
            ('D', 'Alternativa D'),
            ('E', 'Alternativa E'),
        ],
        widget=forms.RadioSelect,
    )