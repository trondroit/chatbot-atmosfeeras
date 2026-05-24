import os
import json
import requests
from flask import Flask, request, jsonify
from openai import OpenAI

app = Flask(__name__)

# ─────────────────────────────────────────
#  PON TUS CREDENCIALES AQUÍ
# ─────────────────────────────────────────
VERIFY_TOKEN    = os.environ.get("VERIFY_TOKEN")
WHATSAPP_TOKEN  = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
OPENAI_API_KEY  = os.environ.get("OPENAI_API_KEY")
# ─────────────────────────────────────────

client = OpenAI(api_key=OPENAI_API_KEY)

# Memoria de conversaciones por número de teléfono
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

CUANDO PIDAN COTIZACIÓN, solicita:
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

def obtener_respuesta_ia(telefono: str, mensaje_usuario: str) -> str:
    """Consulta a OpenAI manteniendo historial por cliente."""
    if telefono not in conversaciones:
        conversaciones[telefono] = []

    conversaciones[telefono].append({
        "role": "user",
        "content": mensaje_usuario
    })

    # Limitar historial a últimos 10 mensajes para no gastar tokens
    historial = conversaciones[telefono][-10:]

    response = client.chat.completions.create(
        model="gpt-4o-mini",  # Económico y rápido, cambia a gpt-4o si quieres más calidad
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT}
        ] + historial,
        max_tokens=300,
        temperature=0.7
    )

    respuesta = response.choices[0].message.content

    conversaciones[telefono].append({
        "role": "assistant",
        "content": respuesta
    })

    return respuesta


def enviar_whatsapp(telefono: str, mensaje: str):
    """Envía un mensaje de texto libre por Meta WhatsApp Cloud API."""
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


# ─── VERIFICACIÓN DEL WEBHOOK (Meta lo llama una sola vez al configurar) ───
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
    data = request.get_json()

    try:
        entry    = data["entry"][0]
        changes  = entry["changes"][0]
        value    = changes["value"]

        # Ignorar si no hay mensajes (puede ser status update)
        if "messages" not in value:
            return jsonify({"status": "ok"}), 200

        mensaje_obj = value["messages"][0]
        telefono    = mensaje_obj["from"]          # Número del cliente
        tipo        = mensaje_obj["type"]

        # Solo procesar mensajes de texto
        if tipo != "text":
            enviar_whatsapp(telefono, "Por el momento solo puedo leer mensajes de texto. ¿En qué te puedo ayudar?")
            return jsonify({"status": "ok"}), 200

        texto = mensaje_obj["text"]["body"]
        print(f"[Mensaje] De {telefono}: {texto}")

        # Obtener respuesta de la IA
        respuesta = obtener_respuesta_ia(telefono, texto)
        print(f"[IA] Respuesta: {respuesta}")

        # Enviar respuesta al cliente
        enviar_whatsapp(telefono, respuesta)

    except (KeyError, IndexError) as e:
        print(f"[Error] Estructura inesperada: {e} | Data: {data}")

    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
