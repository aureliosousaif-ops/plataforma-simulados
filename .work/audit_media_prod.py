"""Verifica se a mídia é servida com DEBUG=False (simulação de deploy)."""

import tempfile
from io import BytesIO

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from provas.models import Disciplina, ImagemProva, Prova, Questao
from usuarios.models import Perfil


class MediaProducaoTestCase(TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.config = override_settings(MEDIA_ROOT=self.pasta.name)
        self.config.enable()
        self.addCleanup(self.config.disable)

        self.dev = User.objects.create_user(
            username='prod_dev',
            password='SenhaTeste123!',
        )
        Perfil.objects.update_or_create(
            usuario=self.dev,
            defaults={'tipo': 'desenvolvedor'},
        )
        self.client.force_login(self.dev)

        self.disciplina = Disciplina.objects.create(nome='Prod')
        self.prova = Prova.objects.create(
            nome='Prova produção',
            tipo='enem',
            ano=2024,
        )
        Questao.objects.create(
            prova=self.prova,
            disciplina=self.disciplina,
            numero=1,
            enunciado='Questão.',
        )

        buffer = BytesIO()
        Image.new('RGB', (40, 20), (10, 20, 30)).save(buffer, 'PNG')
        self.imagem = ImagemProva.objects.create(
            prova=self.prova,
            arquivo=SimpleUploadedFile(
                'prod.png',
                buffer.getvalue(),
                content_type='image/png',
            ),
            hash_sha256='a' * 64,
            pagina=1,
            indice_pagina=0,
        )

    def test_media_nao_e_servida_com_debug_false(self):
        url_media = self.imagem.arquivo.url

        resposta = self.client.get(url_media)

        self.assertEqual(resposta.status_code, 404)
        print(
            '[achado] DEBUG=False: GET '
            f'{url_media} -> 404 (mídia não é servida em produção)'
        )

        resposta = self.client.get(
            reverse(
                'provas:revisar_imagens',
                kwargs={'prova_id': self.prova.id},
            )
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, url_media)
        print(
            '[achado] tela de revisão renderiza 200, mas o <img> aponta '
            'para URL que retorna 404'
        )
