"""Cliente de la API de WhatsApp Cloud (Meta): envío de mensajes,
confirmación de lectura y descarga de archivos multimedia."""
import logging

import requests

import config

log = logging.getLogger(__name__)

TIMEOUT = 15


def _headers():
    return {
        "Authorization": f"Bearer {config.WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }


def _url_mensajes():
    return f"{config.GRAPH_API_URL}/{config.PHONE_NUMBER_ID}/messages"


def enviar_mensaje(telefono, texto):
    """Envía un mensaje de texto. Devuelve True si Meta lo aceptó."""
    body = {
        "messaging_product": "whatsapp",
        "to": telefono,
        "type": "text",
        "text": {"body": texto},
    }
    try:
        resp = requests.post(_url_mensajes(), headers=_headers(),
                             json=body, timeout=TIMEOUT)
        if resp.status_code >= 400:
            log.error("WhatsApp respondió %s: %s",
                      resp.status_code, resp.text[:300])
            return False
        return True
    except requests.RequestException as e:
        log.error("Error enviando WhatsApp: %s", e)
        return False


def marcar_leido(message_id):
    """Marca el mensaje como leído y muestra el indicador de 'escribiendo...'
    mientras se genera la respuesta. Es solo cosmético: si falla, se ignora."""
    body = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
        "typing_indicator": {"type": "text"},
    }
    try:
        resp = requests.post(_url_mensajes(), headers=_headers(),
                             json=body, timeout=TIMEOUT)
        if resp.status_code >= 400:
            log.debug("No se pudo marcar como leído (%s): %s",
                      resp.status_code, resp.text[:200])
    except requests.RequestException as e:
        log.debug("No se pudo marcar como leído: %s", e)


def descargar_media(media_id):
    """Descarga una imagen o audio recibido. Devuelve (bytes, mime_type),
    o (None, None) si algo falla."""
    try:
        meta = requests.get(f"{config.GRAPH_API_URL}/{media_id}",
                            headers=_headers(), timeout=TIMEOUT)
        meta.raise_for_status()
        info = meta.json()
        url = info.get("url")
        if not url:
            log.error("Meta no devolvió URL para el media %s", media_id)
            return None, None
        archivo = requests.get(
            url,
            headers={"Authorization": f"Bearer {config.WHATSAPP_TOKEN}"},
            timeout=30,
        )
        archivo.raise_for_status()
        return archivo.content, info.get("mime_type", "")
    except requests.RequestException as e:
        log.error("Error descargando media %s: %s", media_id, e)
        return None, None
