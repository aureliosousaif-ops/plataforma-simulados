import os

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from usuarios.models import Perfil


class Command(BaseCommand):
    """
    Cria ou atualiza o administrador da plataforma.

    Os dados são obtidos através das variáveis
    de ambiente configuradas no Render.
    """

    help = 'Cria ou atualiza o administrador da plataforma.'

    def handle(self, *args, **options):
        # Lê os dados do administrador das variáveis de ambiente.
        username = os.environ.get('ADMIN_USERNAME')
        email = os.environ.get('ADMIN_EMAIL')
        password = os.environ.get('ADMIN_PASSWORD')

        # Verifica se o usuário foi configurado.
        if not username:
            self.stdout.write(
                self.style.ERROR(
                    'ERRO: ADMIN_USERNAME não foi configurado.'
                )
            )
            return

        # Verifica se o e-mail foi configurado.
        if not email:
            self.stdout.write(
                self.style.ERROR(
                    'ERRO: ADMIN_EMAIL não foi configurado.'
                )
            )
            return

        # Verifica se a senha foi configurada.
        if not password:
            self.stdout.write(
                self.style.ERROR(
                    'ERRO: ADMIN_PASSWORD não foi configurado.'
                )
            )
            return

        # Obtém o modelo de usuário do Django.
        User = get_user_model()

        # Procura o usuário ou cria um novo.
        usuario, criado = User.objects.get_or_create(
            username=username,
            defaults={
                'email': email,
            }
        )

        # Atualiza os dados do usuário.
        usuario.email = email
        usuario.is_active = True
        usuario.is_staff = True
        usuario.is_superuser = True

        # Define a senha com segurança usando o sistema do Django.
        usuario.set_password(password)

        # Salva o usuário no banco.
        usuario.save()

        # Cria o perfil caso ainda não exista.
        perfil, _ = Perfil.objects.get_or_create(
            usuario=usuario
        )

        # Define o perfil como desenvolvedor.
        perfil.tipo = 'desenvolvedor'
        perfil.save()

        # Mostra o resultado no log do Render.
        if criado:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Administrador "{username}" criado com sucesso.'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Administrador "{username}" atualizado com sucesso.'
                )
            )