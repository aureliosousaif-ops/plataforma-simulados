"""
Tratamento personalizado de falhas CSRF.

Este arquivo serve temporariamente para descobrir
por que o celular está recebendo erro 403 CSRF.
"""

import logging

from django.http import HttpResponseForbidden


# Logger específico de segurança do Django.
logger = logging.getLogger("django.security.csrf")


def csrf_failure(request, reason=""):
    """
    Registra informações da requisição que falhou
    na proteção CSRF.
    """

    # Obtém informações importantes da requisição.
    host = request.get_host()
    origin = request.META.get("HTTP_ORIGIN", "NÃO INFORMADO")
    referer = request.META.get("HTTP_REFERER", "NÃO INFORMADO")
    user_agent = request.META.get(
        "HTTP_USER_AGENT",
        "NÃO INFORMADO"
    )

    # Registra a causa da falha no log do Django.
    logger.warning(
        "FALHA CSRF | motivo=%s | host=%s | origin=%s | "
        "referer=%s | user_agent=%s",
        reason,
        host,
        origin,
        referer,
        user_agent,
    )

    # Retorna uma resposta 403 para o navegador.
    return HttpResponseForbidden(
        """
        <h1>403 - CSRF</h1>
        <p>A requisição foi bloqueada pela proteção de segurança.</p>
        """
    )