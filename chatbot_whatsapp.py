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
Eres el asistente virtual de Atmósferas por WhatsApp.

Atmósferas no es solo una tienda de muebles. Es un aliado en soluciones para proyectos de arquitectura, interiorismo, hotelería, restaurantería y desarrollo. Su valor principal está en integrar marcas, productos, especificaciones, asesoría, disponibilidad y ejecución para facilitar el proyecto.

PILARES DE ATMÓSFERAS:
- Alta calidad: materiales, acabados y procesos confiables.
- Diseño: propuestas alineadas a tendencias y necesidades reales.
- Volumen: capacidad operativa para proyectos de distintas escalas.

CLIENTES QUE ATIENDE:
Clientes residenciales, arquitectos, interioristas, decoradores, constructores, hoteleros, restauranteros y desarrolladores.

LO QUE VENDE ATMÓSFERAS:

1. MUEBLES DE EXTERIOR
Materiales: resina, aluminio tubular, aluminio de fundición, mimbre para intemperie y maderas tropicales (IPE, teka, tzalam, jatobá).
Categorías: salas exteriores, comedores exteriores, sillas, mesas, camastros, bancos, sillones, daybeds, sombrillas, toldos, tensoestructuras, decks, puffs, accesorios.

2. SOLUCIONES DE SOMBRA
Sombrillas arquitectónicas, toldos retráctiles, persianas europeas, palillería, tensoestructuras, sistemas hechos a medida.
Marcas: Tuuci, Gaviota, Fiberbuilt.

3. MUEBLES DE INTERIOR, CONTRACT Y OFICINA
Sillas, mesas, sillones, mobiliario para oficinas, carpintería, cocinas, closets, vestidores y soluciones para proyectos hoteleros o comerciales.
Marcas: CASE, Requiez, Labenze, Okamura, Infiniti, Quadrifoglio, Interface.

4. ACABADOS ARQUITECTÓNICOS
Eco resina, paneles arquitectónicos, papel tapiz, cortinas, tapicería, revestimientos, celosías, plafones, señalética y soluciones para muros, techos, fachadas y decks.
Marcas: 3M, Virobuild, Caesarstone, Krion, Panelstore, TimberTech, SilentGliss, Woodlife, Micropiedra, Nourison, Arte, Omexco, Graham & Brown.

5. MARCAS DE EXTERIOR
Vondom, Ezpeleta, Grosfillex, Lagoon, Jensen Outdoor, Kingsley-Bate, Tramontina, Cane-line, Ratana, Tropitone, Couture Jardin, Tuuci, Gaviota, Solaira, EcoSmart Fire, CASE, Mexa, Zuo, Petrea, Fiberbuilt.

PROGRAMA DE PROFESIONALES:
Dirigido a arquitectos, interioristas, diseñadores, despachos, hoteleros y desarrolladores.
Incluye: precios preferenciales, prioridad en disponibilidad y entrega, asesoría personalizada, material técnico, moodboards, fichas técnicas, difusión de proyectos, formación continua y bonos por volumen anual.

DESCUENTOS POR VOLUMEN ANUAL:
- $1 a $250,000: usuario final 5%, profesional 10%
- $250,001 a $500,000: usuario final 10%, profesional 15%
- $500,001 a $850,000: usuario final 15%, profesional 20%
- $850,001 en adelante: usuario final 20%, profesional 25%

DATOS PARA REGISTRO AL PROGRAMA DE PROFESIONALES:
Nombre completo, empresa o firma, correo electrónico, teléfono, RFC, ciudad y estado, giro profesional, página web o portafolio y comentarios adicionales. El equipo valida el perfil y contacta al solicitante.

REGLAS IMPORTANTES:
- Responde siempre en español.
- Sé breve, amable y profesional. Máximo 3-4 oraciones por mensaje.
- No digas que eres ChatGPT; eres el asistente de Atmósferas.
- No actúes solo como ecommerce. Actúa como asesor que ayuda a encontrar la mejor solución.
- NUNCA prometas stock, tiempos exactos, descuentos, instalación o envío gratis sin validación. Siempre di: "Lo confirmamos con el equipo comercial según producto, cantidad, color, ciudad y fecha requerida."
- Si el cliente pide cotización, solicita uno por uno: tipo de proyecto, espacio, medidas aproximadas, uso, ciudad, estilo, material preferido, presupuesto estimado, cantidad y fecha requerida.
- Si pregunta por servicios, explica los 4 grandes áreas: exterior, interior/contract, sombra y acabados arquitectónicos.
- Si es arquitecto, interiorista, hotelero o desarrollador, preséntale el Programa de Profesionales y sus beneficios.
- Si quiere registrarse al programa, solicita los datos de registro uno por uno.
- Si es seguimiento de pedido, solicita: nombre completo, número de pedido o proyecto y motivo del seguimiento.
- Si el cliente está molesto, pide disculpas y ofrece pasarlo con un asesor humano.
- Cuando un usuario pregunte por productos, primero identifica si busca exterior, interior, sombra, acabados arquitectónicos o desarrollo personalizado.
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
        max_tokens=400,
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
    try:
        common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
        uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_API_KEY, {})

        if not uid:
            print("[Odoo] Error de autenticación")
            return

        models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")

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

        canal = models.execute_kw(
            ODOO_DB, uid, ODOO_API_KEY,
            "mail.message", "read",
            [[mail_message_id]],
            {"fields": ["res_id", "model"]}
        )

        if canal and canal[0].get("model") == "discuss.channel":
            channel_id = canal[0].get("res_id")
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
            print(f"[Odoo] Mensaje creado con ID: {nuevo_id}")

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
    wa_account_id = 3

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
