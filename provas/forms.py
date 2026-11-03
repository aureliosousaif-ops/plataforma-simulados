from django import forms

from .models import Prova


class ProvaForm(forms.ModelForm):
    """
    Formulário para cadastro e edição de provas.
    """

    class Meta:
        model = Prova

        fields = [
            'nome',
            'tipo',
            'ano',
            'descricao',
            'arquivo_pdf',
            'arquivo_gabarito',
            'ativa',
        ]

        labels = {
            'nome': 'Nome da prova',
            'tipo': 'Tipo de prova',
            'ano': 'Ano',
            'descricao': 'Descrição',
            'arquivo_pdf': 'PDF da prova',
            'arquivo_gabarito': 'PDF do gabarito',
            'ativa': 'Prova ativa',
        }

        widgets = {
            'nome': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Ex.: ENEM 2025',
                }
            ),

            'tipo': forms.Select(
                attrs={
                    'class': 'form-select',
                }
            ),

            'ano': forms.NumberInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Ex.: 2025',
                    'min': 1900,
                    'max': 2100,
                }
            ),

            'descricao': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 4,
                    'placeholder': 'Descreva a prova...',
                }
            ),

            'arquivo_pdf': forms.ClearableFileInput(
                attrs={
                    'class': 'form-control',
                    'accept': '.pdf,application/pdf',
                }
            ),

            'arquivo_gabarito': forms.ClearableFileInput(
                attrs={
                    'class': 'form-control',
                    'accept': '.pdf,application/pdf',
                }
            ),

            'ativa': forms.CheckboxInput(
                attrs={
                    'class': 'form-check-input',
                }
            ),
        }

    def clean_tipo(self):
        tipo = self.cleaned_data.get('tipo')

        if tipo != 'enem':
            raise forms.ValidationError(
                'A plataforma aceita somente provas do ENEM.'
            )

        return tipo

    def clean_arquivo_pdf(self):
        """
        Garante que o arquivo da prova seja PDF.
        """

        arquivo = self.cleaned_data.get(
            'arquivo_pdf'
        )

        if not arquivo:
            return arquivo

        if not arquivo.name.lower().endswith('.pdf'):
            raise forms.ValidationError(
                'O arquivo da prova deve estar no formato PDF.'
            )

        return arquivo

    def clean_arquivo_gabarito(self):
        """
        Garante que o arquivo do gabarito seja PDF.
        """

        arquivo = self.cleaned_data.get(
            'arquivo_gabarito'
        )

        if not arquivo:
            return arquivo

        if not arquivo.name.lower().endswith('.pdf'):
            raise forms.ValidationError(
                'O arquivo do gabarito deve estar no formato PDF.'
            )

        return arquivo
