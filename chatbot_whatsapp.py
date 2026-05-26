import os
import re
import json
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

FRASE_PAUSA    = "un asesor te atenderá"
FRASE_REANUDAR = "gracias por comunicarce a atmosferas"

PAUSADOS_FILE = "/tmp/pausados.json"

MENSAJE_BIENVENIDA = """¡Hola! 👋 Gracias por comunicarte con Atmosferas Muebles. Mi nombre es Anabel y con gusto te apoyaré.

Estamos para ayudarte a encontrar el mueble ideal para tu hogar u oficina.

Para brindarte una mejor atención, cuéntame por favor:
🔹 ¿Qué producto o modelo te interesa?
🔹 ¿Qué color o estilo buscas?
🔹 ¿En qué ciudad te encuentras?

Con gusto te confirmo precios, disponibilidad y tiempos de entrega 😊"""

def cargar_pausados():
    try:
        with open(PAUSADOS_FILE, "r") as f:
            return set(json.load(f))
    except:
        return set()

def guardar_pausados(pausados):
    try:
        with open(PAUSADOS_FILE, "w") as f:
            json.dump(list(pausados), f)
    except Exception as e:
        print(f"[Pausados] Error guardando: {e}")

numeros_pausados = cargar_pausados()

SYSTEM_PROMPT = """
Eres Anabel, asistente virtual de Atmósferas Muebles por WhatsApp.

Tu personalidad es cálida, amable, profesional y cercana. Usas emojis con moderación para dar un tono humano y amigable. Siempre te presentas como Anabel, nunca como ChatGPT ni como un bot.

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
Nombre completo, empresa o firma, correo electrónico, teléfono, RFC, ciudad y estado, giro profesional, página web o portafolio y comentarios adicionales.

TONO Y ESTILO:
- Responde siempre en español.
- Sé breve, cálida y profesional. Máximo 4-5 oraciones por mensaje.
- Usa emojis con moderación: 🔹✅😊👋 para dar calidez sin exagerar.
- Habla en primera persona como Anabel: "Con gusto te ayudo", "Te confirmo", "Me alegra que preguntes".
- No uses frases robóticas. Suena humana y cercana.
- NUNCA prometas stock, tiempos exactos, descuentos o envío gratis sin validación. Di: "Con gusto lo confirmo con nuestro equipo para darte información exacta 😊"
- Si el cliente pide cotización, solicita uno por uno: tipo de proyecto, espacio, medidas aproximadas, uso, ciudad, estilo, material preferido, presupuesto estimado, cantidad y fecha requerida.
- Si es arquitecto, interiorista, hotelero o desarrollador, preséntale el Programa de Profesionales con entusiasmo.
- Si quiere registrarse al programa, solicita los datos uno por uno con amabilidad.
- Si es seguimiento de pedido, solicita: nombre completo, número de pedido o proyecto y motivo del seguimiento.
- Si el cliente está molesto, pide disculpas con empatía y ofrece pasarlo con un asesor.
- Cuando pregunten por productos, primero identifica si busca exterior, interior, sombra, acabados arquitectónicos o desarrollo personalizado.
"""


def limpiar_html(texto: str) -> str:
    return re.sub(r"<[^>]+>", "", texto).strip()


def es_primer_mensaje(telefono: str) -> bool:
    return telefono not in conversaciones or len(conversaciones[telefono]) == 0


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
    print(f"[WhatsApp] Enviado a {telefono}: {resp.status_code}")
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
                {"body": respuesta_ia, "message_type": "comment", "author_id": uid}
            )
            print(f"[Odoo] Respuesta posteada en canal {channel_id}")
        else:
            models.execute_kw(
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
    except Exception as e:
        print(f"[Odoo] Error: {e}")


# ─── VERIFICACIÓN ───
@app.route("/webhook", methods=["GET"])
def verificar_webhook():
    mode      = request.args.get("hub.mode")
    token     = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Token inválido", 403


# ─── WEBHOOK SALIENTE (mensajes de asesores desde Odoo) ───
@app.route("/webhook-saliente", methods=["POST"])
def recibir_mensaje_saliente():
    data = request.get_json(silent=True) or {}
    print(f"[Saliente] Datos: {data}")
    telefono  = data.get("mobile_number") or data.get("display_name", "")
    texto_raw = data.get("body", "")
    texto     = limpiar_html(texto_raw).lower().strip()
    if not telefono or not texto:
        return jsonify({"status": "ok"}), 200
    if FRASE_PAUSA.lower() in texto:
        numeros_pausados.add(telefono)
        guardar_pausados(numeros_pausados)
        print(f"[Bot] PAUSADO para {telefono}")
    elif FRASE_REANUDAR.lower() in texto:
        numeros_pausados.discard(telefono)
        guardar_pausados(numeros_pausados)
        print(f"[Bot] REACTIVADO para {telefono}")
    return jsonify({"status": "ok"}), 200


# ─── MENSAJES ENTRANTES ───
@app.route("/webhook", methods=["POST"])
def recibir_mensaje():
    data = request.get_json(silent=True) or {}
    print(f"[Webhook] Datos: {data}")

    telefono      = None
    texto         = None
    odoo_msg_id   = None
    wa_account_id = 3

    if "mobile_number" in data or "display_name" in data:
        telefono    = data.get("mobile_number") or data.get("display_name", "")
        texto_raw   = data.get("body", "")
        texto       = limpiar_html(texto_raw)
        odoo_msg_id = data.get("id")
    elif "entry" in data:
        try:
            value = data["entry"][0]["changes"][0]["value"]
            if "messages" not in value:
                return jsonify({"status": "ok"}), 200
            mensaje_obj = value["messages"][0]
            telefono    = mensaje_obj["from"]
            if mensaje_obj["type"] != "text":
                enviar_whatsapp(telefono, "Por el momento solo puedo leer mensajes de texto. ¿En qué te puedo ayudar? 😊")
                return jsonify({"status": "ok"}), 200
            texto = mensaje_obj["text"]["body"]
        except (KeyError, IndexError) as e:
            print(f"[Error Meta] {e}")
            return jsonify({"status": "ok"}), 200

    if not telefono or not texto:
        print("[Webhook] Sin teléfono o mensaje, ignorando.")
        return jsonify({"status": "ok"}), 200

    if telefono in numeros_pausados:
        print(f"[Bot] Pausado para {telefono}, ignorando.")
        return jsonify({"status": "ok"}), 200

    # Mensaje de bienvenida al primer contacto
    primer_mensaje = es_primer_mensaje(telefono)

    print(f"[Mensaje] De {telefono}: {texto}")

    if primer_mensaje:
        enviar_whatsapp(telefono, MENSAJE_BIENVENIDA)
        if odoo_msg_id:
            registrar_en_odoo(telefono, MENSAJE_BIENVENIDA, odoo_msg_id, wa_account_id)
        # Inicializar conversación con contexto del primer mensaje
        conversaciones[telefono] = []

    respuesta = obtener_respuesta_ia(telefono, texto)
    print(f"[IA] Respuesta: {respuesta}")

    # Si es primer mensaje, ya mandamos bienvenida, ahora mandamos también la respuesta
    if not primer_mensaje:
        enviar_whatsapp(telefono, respuesta)
        if odoo_msg_id:
            registrar_en_odoo(telefono, respuesta, odoo_msg_id, wa_account_id)
    else:
        # En el primer mensaje solo mandamos la bienvenida
        pass

    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
