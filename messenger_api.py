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


def _url():
    return f"{config.GRAPH_API_URL}/me/messages"


def _params():
    return {"access_token": config.PAGE_ACCESS_TOKEN}


def enviar_mensaje(psid, texto):
    """Envía un mensaje de texto a un usuario de Messenger (identificado por
    su PSID). Devuelve True si Meta lo aceptó."""
    body = {
        "recipient": {"id": psid},
        "messaging_type": "RESPONSE",
        "message": {"text": texto},
    }
    try:
        resp = requests.post(_url(), params=_params(), json=body, timeout=TIMEOUT)
        if resp.status_code >= 400:
            log.error("Messenger respondió %s: %s",
                      resp.status_code, resp.text[:300])
            return False
        return True
    except requests.RequestException as e:
        log.error("Error enviando a Messenger: %s", e)
        return False


def marcar_visto(psid, escribiendo=True):
    """Marca la conversación como vista y (opcional) muestra el indicador de
    'escribiendo…'. Es cosmético: si falla, se ignora."""
    for accion in filter(None, ["mark_seen", "typing_on" if escribiendo else None]):
        try:
            requests.post(_url(), params=_params(),
                          json={"recipient": {"id": psid}, "sender_action": accion},
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
