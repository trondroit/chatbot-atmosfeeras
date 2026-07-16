"""Cliente de la API de Facebook Messenger (Send API, Graph de Meta):
envío de mensajes, indicadores de estado y descarga de adjuntos.

Messenger e Instagram comparten esta misma Send API; el token de la Página
(PAGE_ACCESS_TOKEN) determina a qué canal se responde.
"""
import logging

import requests

import config

log = logging.getLogger(__name__)

TIMEOUT = 15


def _url_y_token(canal):
    """Devuelve (url, token) según el canal. Instagram usa su propia API y su
    propio token si está configurado; si no, cae a la Página de Facebook."""
    if canal == "ig" and config.IG_ACCESS_TOKEN:
        return f"{config.IG_GRAPH_URL}/me/messages", config.IG_ACCESS_TOKEN
    return f"{config.GRAPH_API_URL}/me/messages", config.PAGE_ACCESS_TOKEN


def enviar_mensaje(uid, texto, canal="msgr"):
    """Envía un mensaje de texto a un usuario de Messenger o Instagram.
    Devuelve True si Meta lo aceptó."""
    url, token = _url_y_token(canal)
    body = {
        "recipient": {"id": uid},
        "messaging_type": "RESPONSE",
        "message": {"text": texto},
    }
    try:
        resp = requests.post(url, params={"access_token": token},
                             json=body, timeout=TIMEOUT)
        if resp.status_code >= 400:
            log.error("%s respondió %s: %s", canal,
                      resp.status_code, resp.text[:300])
            return False
        return True
    except requests.RequestException as e:
        log.error("Error enviando a %s: %s", canal, e)
        return False


def marcar_visto(uid, canal="msgr"):
    """Marca la conversación como vista y muestra el indicador de
    'escribiendo…'. Es cosmético: si falla, se ignora."""
    url, token = _url_y_token(canal)
    for accion in ("mark_seen", "typing_on"):
        try:
            requests.post(url, params={"access_token": token},
                          json={"recipient": {"id": uid}, "sender_action": accion},
                          timeout=TIMEOUT)
        except requests.RequestException as e:
            log.debug("No se pudo enviar sender_action %s: %s", accion, e)


def descargar_adjunto(url):
    """Descarga un adjunto (imagen o audio) desde la URL pública que envía
    Messenger. Devuelve (bytes, mime_type) o (None, None) si falla."""
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return resp.content, resp.headers.get("Content-Type", "")
    except requests.RequestException as e:
        log.error("Error descargando adjunto de Messenger: %s", e)
        return None, None
