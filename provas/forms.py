from django import forms

from .dias import inferir_dia
from .models import Prova


class ProvaForm(forms.ModelForm):
    """
    Formulário para cadastro e edição de provas.
    """

    # O campo dia existe no modelo desde a migração 0008, mas não era
    # exibido no cadastro manual. "Não informado" preserva o dia já
    # cadastrado (provas do catálogo) e tenta identificar o dia das
    # provas novas a partir dos dados confiáveis do cadastro.
    dia = forms.TypedChoiceField(
        choices=[
            ('', 'Não informado'),
            (1, '1º dia — Linguagens, Códigos e Ciências Humanas'),
            (2, '2º dia — Ciências da Natureza e Matemática'),
        ],
        coerce=int,
        empty_value=None,
        required=False,
        widget=forms.Select(
            attrs={
                'class': 'form-select',
            }
        ),
        help_text=(
            'Ao editar, manter "Não informado" preserva o dia atual. '
            'Selecione o dia correspondente à prova do ENEM.'
        ),
    )

    class Meta:
        model = Prova

        fields = [
            'nome',
            'tipo',
            'ano',
            'dia',
            'descricao',
            'arquivo_pdf',
            'arquivo_gabarito',
            'ativa',
        ]

        labels = {
            'nome': 'Nome da prova',
            'tipo': 'Tipo de prova',
            'ano': 'Ano',
            'dia': 'Dia da prova',
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

    def clean_dia(self):
        """
        Não apaga o dia de uma prova já cadastrada quando o campo
        opcional não é enviado (formulários antigos, por exemplo).
        """

        dia = self.cleaned_data.get('dia')

        if dia in (1, 2):
            return dia

        if self.instance and self.instance.pk:
            return self.instance.dia

        return None

    def save(self, commit=True):
        """Preenche o dia quando o usuário não informou um."""

        prova = super().save(commit=False)

        if prova.dia not in (1, 2):
            prova.dia = inferir_dia(prova)

        if commit:
            prova.save()
            self.save_m2m()

        return prova
