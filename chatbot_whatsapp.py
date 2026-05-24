import os
import re
import requests
import xmlrpc.client
from flask import Flask, request, jsonify
from openai import OpenAI

app = Flask(__name__)

VERIFY_TOKEN    = os.environ.get("VERIFY_TOKEN")
WHATSAPP_TOKEN  = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
OPENAI_API_KEY  = os.environ.get("OPENAI_API_KEY")
ODOO_URL        = os.environ.get("ODOO_URL")
ODOO_DB         = os.environ.get("ODOO_DB")
ODOO_USER       = os.environ.get("ODOO_USER")
ODOO_API_KEY    = os.environ.get("ODOO_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

conversaciones = {}

SYSTEM_PROMPT = """
Eres el asistente virtual de Atmosferas Muebles por WhatsApp.
Tu objetivo es atender clientes, resolver dudas y perfilar oportunidades de venta.

REGLAS:
- Responde siempre en español.
- Sé breve, amable y profesional. Máximo 3-4 oraciones por mensaje.
- No inventes precios, tiempos de entrega ni promociones.
- No digas que eres ChatGPT; eres el asistente de Atmosferas Muebles.
- Si no tienes información suficiente, pide los datos necesarios.
- Si el cliente está molesto, pide disculpas y ofrece pasarlo con un asesor humano.

CUANDO PIDAN COTIZACIÓN, solicita uno por uno:
1. Tipo de proyecto (cocina, closet, sala, etc.)
2. Medidas aproximadas
3. Ciudad
4. Fecha estimada de inicio
5. Si tiene fotos, planos o referencias

CUANDO PREGUNTEN POR SERVICIOS, explica:
- Diseño y fabricación de muebles a medida
- Cocinas integrales
- Closets y vestidores
- Muebles de sala y comedor
- Instalación incluida

CUANDO SEA SEGUIMIENTO DE PEDIDO, solicita:
- Nombre completo
- Número de pedido o proyecto
- Motivo del seguimiento
"""


def limpiar_html(texto: str) -> str:
    return re.sub(r"<[^>]+>", "", texto).strip()


def obtener_respuesta_ia(telefono: str, mensaje_usuario: str) -> str:
    if telefono not in conversaciones:
        conversaciones[telefono] = []

    conversaciones[telefono].append({"role": "user", "content": mensaje_usuario})
    historial = conversaciones[telefono][-10:]

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": SYSTEM_PROMPT}] + historial,
        max_tokens=300,
        temperature=0.7
    )

    respuesta = response.choices[0].message.content
    conversaciones[telefono].append({"role": "assistant", "content": respuesta})
    return respuesta


def enviar_whatsapp(telefono: str, mensaje: str):
    url = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    body = {
        "messaging_product": "whatsapp",
        "to": telefono,
        "type": "text",
        "text": {"body": mensaje}
    }
    resp = requests.post(url, headers=headers, json=body)
    print(f"[WhatsApp] Enviado a {telefono}: {resp.status_code} - {resp.text}")
    return resp


def registrar_en_odoo(telefono: str, respuesta_ia: str, odoo_message_id: int, wa_account_id: int):
    """Registra la respuesta de la IA en el hilo correcto de Odoo."""
    try:
        common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
        uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_API_KEY, {})

        if not uid:
            print("[Odoo] Error de autenticación")
            return

        models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")

        # Buscar el mail_message_id del mensaje entrante para vincularnos al mismo hilo
        mensaje_original = models.execute_kw(
            ODOO_DB, uid, ODOO_API_KEY,
            "whatsapp.message", "read",
            [[odoo_message_id]],
            {"fields": ["mail_message_id", "wa_account_id"]}
        )

        if not mensaje_original:
            print("[Odoo] No se encontró el mensaje original")
            return

        mail_message_id = mensaje_original[0].get("mail_message_id")
        mail_message_id = mail_message_id[0] if isinstance(mail_message_id, list) else mail_message_id
        print(f"[Odoo] mail_message_id del hilo: {mail_message_id}")

        # Buscar el discuss.channel vinculado a ese mail.message
        canal = models.execute_kw(
            ODOO_DB, uid, ODOO_API_KEY,
            "mail.message", "read",
            [[mail_message_id]],
            {"fields": ["res_id", "model"]}
        )
        print(f"[Odoo] Canal info: {canal}")

        if canal and canal[0].get("model") == "discuss.channel":
            channel_id = canal[0].get("res_id")

            # Postear mensaje en el canal de discuss
            models.execute_kw(
                ODOO_DB, uid, ODOO_API_KEY,
                "discuss.channel", "message_post",
                [channel_id],
                {
                    "body": respuesta_ia,
                    "message_type": "comment",
                    "author_id": uid,
                }
            )
            print(f"[Odoo] Respuesta posteada en discuss.channel {channel_id}")
        else:
            # Fallback: crear whatsapp.message saliente vinculado al mismo número
            nuevo_id = models.execute_kw(
                ODOO_DB, uid, ODOO_API_KEY,
                "whatsapp.message", "create",
                [{
                    "mobile_number": telefono,
                    "body": respuesta_ia,
                    "message_type": "outbound",
                    "state": "sent",
                    "wa_account_id": wa_account_id,
                    "parent_id": odoo_message_id,
                }]
            )
            print(f"[Odoo] Mensaje creado con parent_id, ID: {nuevo_id}")

    except Exception as e:
        print(f"[Odoo] Error al registrar: {e}")


# ─── VERIFICACIÓN DEL WEBHOOK ───
@app.route("/webhook", methods=["GET"])
def verificar_webhook():
    mode      = request.args.get("hub.mode")
    token     = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("[Webhook] Verificado correctamente")
        return challenge, 200
    return "Token inválido", 403


# ─── RECEPCIÓN DE MENSAJES ───
@app.route("/webhook", methods=["POST"])
def recibir_mensaje():
    data = request.get_json(silent=True) or {}
    print(f"[Webhook] Datos recibidos: {data}")

    telefono      = None
    texto         = None
    odoo_msg_id   = None
    wa_account_id = 3  # ID cuenta Atmosferas

    # ── Formato Odoo ──
    if "mobile_number" in data or "display_name" in data:
        telefono    = data.get("mobile_number") or data.get("display_name", "")
        texto_raw   = data.get("body", "")
        texto       = limpiar_html(texto_raw)
        odoo_msg_id = data.get("id")

    # ── Formato Meta directo ──
    elif "entry" in data:
        try:
            value = data["entry"][0]["changes"][0]["value"]
            if "messages" not in value:
                return jsonify({"status": "ok"}), 200
            mensaje_obj = value["messages"][0]
            telefono    = mensaje_obj["from"]
            if mensaje_obj["type"] != "text":
                enviar_whatsapp(telefono, "Por el momento solo puedo leer mensajes de texto. ¿En qué te puedo ayudar?")
                return jsonify({"status": "ok"}), 200
            texto = mensaje_obj["text"]["body"]
        except (KeyError, IndexError) as e:
            print(f"[Error Meta] {e}")
            return jsonify({"status": "ok"}), 200

    if not telefono or not texto:
        print("[Webhook] Sin teléfono o mensaje, ignorando.")
        return jsonify({"status": "ok"}), 200

    print(f"[Mensaje] De {telefono}: {texto}")
    respuesta = obtener_respuesta_ia(telefono, texto)
    print(f"[IA] Respuesta: {respuesta}")

    enviar_whatsapp(telefono, respuesta)

    if odoo_msg_id:
        registrar_en_odoo(telefono, respuesta, odoo_msg_id, wa_account_id)

    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
