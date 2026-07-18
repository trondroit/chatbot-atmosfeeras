"""Chatbot de WhatsApp de Atmósferas Muebles — servidor Flask.

Flujo:
- Meta (u Odoo vía webhook) entrega los mensajes entrantes en POST /webhook.
- Se valida la firma, se deduplica y se responde 200 de inmediato;
  la IA, el envío por WhatsApp y el registro en Odoo corren en segundo plano.
- Los mensajes que los asesores mandan desde Odoo llegan a
  POST /webhook-saliente y sirven para pausar/reactivar el bot por número.
"""
import base64
import hashlib
import hmac
import logging
import re
import threading
import unicodedata

from flask import Flask, jsonify, request

import ai
import config
import messenger_api
import odoo_client
import storage
import whatsapp_api

log = logging.getLogger("chatbot")

app = Flask(__name__)

# Frases con las que un asesor pausa/reactiva el bot desde Odoo. Se comparan
# sin acentos ni mayúsculas. Se aceptan la frase histórica con error de dedo
# ("comunicarce") y la versión corregida.
FRASES_PAUSA = ("un asesor te atendera",)
FRASES_REANUDAR = (
    "gracias por comunicarse a atmosferas",
    "gracias por comunicarce a atmosferas",
)
COMANDO_PAUSA = "#bot-off"
COMANDO_REANUDAR = "#bot-on"

MENSAJE_TIPO_NO_SOPORTADO = (
    "Por el momento puedo leer mensajes de texto, fotos y notas de voz. "
    "¿En qué le puedo ayudar? 😊"
)
MENSAJE_IMAGEN_FALLIDA = (
    "No pude abrir la imagen que me envió 😔 "
    "¿Me la puede reenviar o describir lo que necesita?"
)
MENSAJE_AUDIO_FALLIDO = (
    "No pude escuchar bien su nota de voz 😔 "
    "¿Me lo puede compartir por texto, por favor?"
)
MENSAJE_PASO_ASESOR = (
    "¡Con mucho gusto! 🙏 En un momento un asesor de Atmósferas continúa su "
    "atención por este mismo chat. Gracias por su preferencia."
)


def limpiar_html(texto):
    return re.sub(r"<[^>]+>", "", texto).strip()


def _normalizar(texto):
    """Minúsculas y sin acentos, para comparar frases de control."""
    texto = unicodedata.normalize("NFD", texto.lower().strip())
    return "".join(c for c in texto if not unicodedata.combining(c))


def _mask(telefono):
    """Enmascara el teléfono para los logs (dato personal)."""
    telefono = str(telefono or "")
    return f"***{telefono[-4:]}" if len(telefono) >= 4 else "***"


def _lanzar(func, *args):
    """Ejecuta el procesamiento en segundo plano para responder el webhook
    de inmediato (si Meta no recibe el 200 rápido, reintenta y se duplican
    los mensajes)."""
    threading.Thread(target=func, args=args, daemon=True).start()


# ─── SEGURIDAD DE WEBHOOKS ───

def _firma_meta_valida():
    """Verifica la firma X-Hub-Signature-256. Se acepta si coincide con el App
    Secret de Facebook (WhatsApp/Messenger) o con el App Secret de Instagram,
    porque la API de Instagram firma sus webhooks con un secreto distinto."""
    secretos = [s for s in (config.META_APP_SECRET, config.IG_APP_SECRET) if s]
    if not secretos:
        log.warning("No hay App Secret configurado: el webhook acepta "
                    "peticiones sin verificar la firma. Configúralo cuanto antes.")
        return True
    firma = request.headers.get("X-Hub-Signature-256", "")
    cuerpo = request.get_data()
    for secreto in secretos:
        esperada = "sha256=" + hmac.new(
            secreto.encode(), cuerpo, hashlib.sha256
        ).hexdigest()
        if hmac.compare_digest(firma, esperada):
            return True
    return False


def _token_odoo_valido():
    """Verifica el token compartido de los webhooks que vienen de Odoo."""
    if not config.WEBHOOK_SALIENTE_TOKEN:
        log.warning("WEBHOOK_SALIENTE_TOKEN no está configurado: los webhooks "
                    "de Odoo se aceptan sin autenticación. Configúralo cuanto antes.")
        return True
    token = (request.headers.get("X-Webhook-Token")
             or request.args.get("token", ""))
    return hmac.compare_digest(token, config.WEBHOOK_SALIENTE_TOKEN)


# ─── PROCESAMIENTO (corre en segundo plano) ───

def _quizas_crear_lead(telefono, respuesta):
    """Si el bot ofreció canalizar con un asesor, crea un lead en el CRM
    de Odoo (uno por número cada 24 h, y solo si ODOO_CREAR_LEADS=1)."""
    if not config.ODOO_CREAR_LEADS:
        return
    respuesta_norm = _normalizar(respuesta)
    if "canalic" not in respuesta_norm and "canaliz" not in respuesta_norm:
        return
    if storage.ya_procesado(f"lead:{telefono}"):
        return
    historial = storage.historial(telefono)
    resumen = "\n".join(
        f"{'Cliente' if m['role'] == 'user' else 'Bot'}: {m['content']}"
        for m in historial[-10:]
        if isinstance(m.get("content"), str)
    )
    odoo_client.crear_lead(telefono, resumen)


def _procesar_mensaje_meta(mensaje):
    telefono = mensaje.get("from")
    if not telefono:
        return
    if storage.esta_pausado(telefono):
        log.info("Bot pausado para %s, ignorando", _mask(telefono))
        return

    if mensaje.get("id"):
        whatsapp_api.marcar_leido(mensaje["id"])

    tipo = mensaje.get("type")
    texto, imagen_b64, imagen_mime = None, None, None

    if tipo == "text":
        texto = mensaje.get("text", {}).get("body", "")
    elif tipo == "image":
        contenido, mime = whatsapp_api.descargar_media(mensaje["image"]["id"])
        if not contenido:
            whatsapp_api.enviar_mensaje(telefono, MENSAJE_IMAGEN_FALLIDA)
            return
        imagen_b64 = base64.b64encode(contenido).decode()
        imagen_mime = mime or "image/jpeg"
        texto = mensaje["image"].get("caption", "")
    elif tipo == "audio":
        contenido, mime = whatsapp_api.descargar_media(mensaje["audio"]["id"])
        texto = ai.transcribir(contenido, mime) if contenido else None
        if not texto:
            whatsapp_api.enviar_mensaje(telefono, MENSAJE_AUDIO_FALLIDO)
            return
    else:
        whatsapp_api.enviar_mensaje(telefono, MENSAJE_TIPO_NO_SOPORTADO)
        return

    if not texto and not imagen_b64:
        return

    log.info("Mensaje %s de %s", tipo, _mask(telefono))
    respuesta, quiere_asesor = ai.responder(telefono, texto or "",
                                            imagen_b64, imagen_mime)
    if quiere_asesor:
        _pasar_a_asesor(telefono,
                        lambda t: whatsapp_api.enviar_mensaje(telefono, t))
        return
    whatsapp_api.enviar_mensaje(telefono, respuesta)
    _quizas_crear_lead(telefono, respuesta)


def _procesar_mensaje_odoo(telefono, texto, odoo_msg_id):
    if storage.esta_pausado(telefono):
        log.info("Bot pausado para %s, ignorando", _mask(telefono))
        return
    log.info("Mensaje (vía Odoo) de %s", _mask(telefono))
    respuesta, quiere_asesor = ai.responder(telefono, texto)
    if quiere_asesor:
        _pasar_a_asesor(telefono,
                        lambda t: whatsapp_api.enviar_mensaje(telefono, t))
        return
    whatsapp_api.enviar_mensaje(telefono, respuesta)
    if odoo_msg_id:
        odoo_client.registrar_respuesta(telefono, respuesta, odoo_msg_id)
    _quizas_crear_lead(telefono, respuesta)


def _pasar_a_asesor(dest_id, enviar):
    """El cliente pidió un asesor humano: se pausa el bot para ese contacto y
    se le confirma. Un asesor lo reactiva luego con la frase o #bot-on.

    `dest_id` es la clave con la que se guarda el estado (teléfono en
    WhatsApp, msgr:<psid> en Messenger) y `enviar` es la función del canal
    para mandarle el mensaje de confirmación al cliente."""
    storage.pausar(dest_id)
    enviar(MENSAJE_PASO_ASESOR)
    log.info("Bot AUTO-PAUSADO: %s pidió pasar con un asesor", _mask(dest_id))


# ─── MENSAJERÍA DE META: MESSENGER E INSTAGRAM (canal directo Meta -> bot) ───
# Messenger e Instagram comparten el mismo formato de webhook (messaging[]) y
# la misma Send API con el token de la Página; solo cambia el prefijo con el
# que se guarda el estado, para que los canales nunca se crucen.

# object del webhook -> prefijo de estado
CANAL_POR_OBJECT = {"page": "msgr", "instagram": "ig"}


def _clave_canal(canal, uid):
    return f"{canal}:{uid}"


def _procesar_mensaje_mensajeria(evento, canal):
    uid = evento.get("sender", {}).get("id")
    if not uid:
        return
    clave = _clave_canal(canal, uid)
    if storage.esta_pausado(clave):
        log.info("Bot pausado para %s, ignorando", _mask(clave))
        return

    mensaje = evento.get("message", {})
    messenger_api.marcar_visto(uid, canal)

    texto = mensaje.get("text")
    imagen_b64, imagen_mime = None, None

    for adj in mensaje.get("attachments", []) or []:
        tipo = adj.get("type")
        url = adj.get("payload", {}).get("url")
        if tipo == "image" and url:
            contenido, mime = messenger_api.descargar_adjunto(url)
            if not contenido:
                messenger_api.enviar_mensaje(uid, MENSAJE_IMAGEN_FALLIDA, canal)
                return
            imagen_b64 = base64.b64encode(contenido).decode()
            imagen_mime = mime or "image/jpeg"
        elif tipo == "audio" and url:
            contenido, mime = messenger_api.descargar_adjunto(url)
            texto = ai.transcribir(contenido, mime) if contenido else None
            if not texto:
                messenger_api.enviar_mensaje(uid, MENSAJE_AUDIO_FALLIDO, canal)
                return
        else:
            messenger_api.enviar_mensaje(uid, MENSAJE_TIPO_NO_SOPORTADO, canal)
            return

    if not texto and not imagen_b64:
        return

    log.info("Mensaje %s de %s", canal, _mask(clave))
    respuesta, quiere_asesor = ai.responder(clave, texto or "",
                                            imagen_b64, imagen_mime)
    if quiere_asesor:
        _pasar_a_asesor(clave,
                        lambda t: messenger_api.enviar_mensaje(uid, t, canal))
        return
    messenger_api.enviar_mensaje(uid, respuesta, canal)


def _procesar_echo_mensajeria(evento, canal):
    """Eco de un mensaje enviado por la Página/cuenta. Si lo escribió un
    agente humano desde la Bandeja de Meta (sin app_id), sus frases sirven
    para pausar/reactivar el bot, igual que un asesor en Odoo. Los ecos de
    los propios envíos del bot (con app_id) se ignoran."""
    mensaje = evento.get("message", {})
    if mensaje.get("app_id"):
        return
    uid = evento.get("recipient", {}).get("id")
    if not uid:
        return
    clave = _clave_canal(canal, uid)
    texto = _normalizar(mensaje.get("text", ""))
    if COMANDO_PAUSA in texto or any(f in texto for f in FRASES_PAUSA):
        storage.pausar(clave)
        log.info("Bot PAUSADO (agente) para %s", _mask(clave))
    elif COMANDO_REANUDAR in texto or any(f in texto for f in FRASES_REANUDAR):
        storage.reanudar(clave)
        log.info("Bot REACTIVADO (agente) para %s", _mask(clave))


def _procesar_entrada_mensajeria(data, canal):
    if not config.PAGE_ACCESS_TOKEN:
        log.warning("Llegó un webhook de %s pero PAGE_ACCESS_TOKEN no está "
                    "configurado; se ignora.", canal)
        return
    for entry in data.get("entry", []):
        for evento in entry.get("messaging", []) or []:
            mensaje = evento.get("message")
            if not mensaje:
                continue  # ignora entregas, lecturas, postbacks, etc.
            mid = mensaje.get("mid")
            if mid and storage.ya_procesado(f"{canal}:{mid}"):
                continue
            if mensaje.get("is_echo"):
                _procesar_echo_mensajeria(evento, canal)
            else:
                _lanzar(_procesar_mensaje_mensajeria, evento, canal)


def _procesar_entrada_whatsapp(data):
    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for mensaje in value.get("messages", []) or []:
                msg_id = mensaje.get("id")
                if msg_id and storage.ya_procesado(f"meta:{msg_id}"):
                    log.info("Mensaje %s ya procesado, ignorando", msg_id)
                    continue
                _lanzar(_procesar_mensaje_meta, mensaje)


# ─── RUTAS ───

@app.route("/health", methods=["GET", "HEAD"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/webhook", methods=["GET"])
def verificar_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token", "")
    challenge = request.args.get("hub.challenge", "")
    if (mode == "subscribe" and config.VERIFY_TOKEN
            and hmac.compare_digest(token, config.VERIFY_TOKEN)):
        return challenge, 200
    return "Token inválido", 403


@app.route("/webhook", methods=["POST"])
def recibir_mensaje():
    data = request.get_json(silent=True) or {}

    # Payload directo de Meta (WhatsApp Cloud API o Messenger). Se distingue
    # por el campo "object"; ambos van firmados con el App Secret.
    if "entry" in data:
        if not _firma_meta_valida():
            log.warning("Webhook de Meta con firma inválida, rechazado")
            return "Firma inválida", 403
        canal = CANAL_POR_OBJECT.get(data.get("object"))
        if canal:                       # page -> Messenger, instagram -> Instagram
            _procesar_entrada_mensajeria(data, canal)
        else:                           # whatsapp_business_account, etc.
            _procesar_entrada_whatsapp(data)
        return jsonify({"status": "ok"}), 200

    # Payload reenviado por Odoo (mensaje entrante del cliente).
    if not _token_odoo_valido():
        log.warning("Webhook de Odoo con token inválido, rechazado")
        return "Token inválido", 403
    telefono = data.get("mobile_number") or data.get("display_name", "")
    texto = limpiar_html(data.get("body", ""))
    odoo_msg_id = data.get("id")
    if not telefono or not texto:
        return jsonify({"status": "ok"}), 200
    if odoo_msg_id and storage.ya_procesado(f"odoo:{odoo_msg_id}"):
        return jsonify({"status": "ok"}), 200
    _lanzar(_procesar_mensaje_odoo, telefono, texto, odoo_msg_id)
    return jsonify({"status": "ok"}), 200


@app.route("/webhook-saliente", methods=["POST"])
def recibir_mensaje_saliente():
    """Mensajes que los asesores envían desde Odoo. Sirven para pausar o
    reactivar el bot para un número, por frase o por comando."""
    if not _token_odoo_valido():
        log.warning("Webhook saliente con token inválido, rechazado")
        return "Token inválido", 403
    data = request.get_json(silent=True) or {}
    telefono = data.get("mobile_number") or data.get("display_name", "")
    texto = _normalizar(limpiar_html(data.get("body", "")))
    if not telefono or not texto:
        return jsonify({"status": "ok"}), 200

    if COMANDO_PAUSA in texto or any(f in texto for f in FRASES_PAUSA):
        storage.pausar(telefono)
        log.info("Bot PAUSADO para %s", _mask(telefono))
    elif COMANDO_REANUDAR in texto or any(f in texto for f in FRASES_REANUDAR):
        storage.reanudar(telefono)
        log.info("Bot REACTIVADO para %s", _mask(telefono))
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
