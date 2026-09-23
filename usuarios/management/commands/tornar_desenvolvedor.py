from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User


class Command(BaseCommand):
    """
    Transforma um usuário existente em desenvolvedor.

    O comando é executado somente pelo terminal do projeto,
    evitando que qualquer pessoa escolha esse tipo no cadastro.
    """

    help = 'Transforma um usuário existente em desenvolvedor.'

    def add_arguments(self, parser):
        """
        Define o argumento que receberemos pelo terminal.
        """

        parser.add_argument(
            'username',
            type=str,
            help='Nome do usuário que será transformado.'
        )

    def handle(self, *args, **options):
        """
        Executa a transformação do perfil.
        """

        username = options['username']

        try:
            usuario = User.objects.get(
                username=username
            )

        except User.DoesNotExist:

            raise CommandError(
                f'O usuário "{username}" não foi encontrado.'
            )

        perfil = usuario.perfil

        perfil.tipo = 'desenvolvedor'
        perfil.save(
            update_fields=['tipo']
        )

        self.stdout.write(
            self.style.SUCCESS(
                f'Usuário "{username}" agora é desenvolvedor.'
            )
        )