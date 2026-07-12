"""Capa de IA: respuestas del asesor virtual, análisis de fotos y
transcripción de audios."""
import io
import logging

from openai import OpenAI

import config
import storage
from prompts import SYSTEM_PROMPT

log = logging.getLogger(__name__)

MENSAJE_FALLBACK = (
    "Disculpe, en este momento tengo un problema técnico para responderle. "
    "En breve un asesor de Atmósferas le atenderá personalmente 🙏"
)

_client = None


def _cliente():
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=config.OPENAI_API_KEY,
            timeout=config.OPENAI_TIMEOUT,
            max_retries=2,
        )
    return _client


def responder(telefono, texto, imagen_b64=None, imagen_mime=None):
    """Genera la respuesta del asesor virtual para un mensaje del cliente.

    Si hay imagen, se envía al modelo solo en esta llamada; en el historial
    se guarda una nota de texto para no arrastrar la imagen en cada turno.
    """
    historial = storage.historial(telefono)

    if imagen_b64:
        contenido = [
            {"type": "text",
             "text": texto or "El cliente envió esta foto de su espacio."},
            {"type": "image_url",
             "image_url": {"url": f"data:{imagen_mime};base64,{imagen_b64}"}},
        ]
        texto_historial = f"[El cliente envió una foto] {texto}".strip()
    else:
        contenido = texto
        texto_historial = texto

    mensajes = (
        [{"role": "system", "content": SYSTEM_PROMPT}]
        + historial
        + [{"role": "user", "content": contenido}]
    )

    try:
        response = _cliente().chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=mensajes,
            max_tokens=400,
            temperature=0.7,
        )
        respuesta = response.choices[0].message.content
    except Exception as e:
        log.error("Error consultando OpenAI: %s", e)
        return MENSAJE_FALLBACK

    storage.agregar_mensaje(telefono, "user", texto_historial)
    storage.agregar_mensaje(telefono, "assistant", respuesta)
    return respuesta


def transcribir(audio_bytes, mime="audio/ogg"):
    """Transcribe una nota de voz. Devuelve None si no se pudo."""
    try:
        response = _cliente().audio.transcriptions.create(
            model=config.OPENAI_TRANSCRIBE_MODEL,
            file=("audio.ogg", io.BytesIO(audio_bytes), mime or "audio/ogg"),
        )
        texto = (response.text or "").strip()
        return texto or None
    except Exception as e:
        log.error("Error transcribiendo audio: %s", e)
        return None
