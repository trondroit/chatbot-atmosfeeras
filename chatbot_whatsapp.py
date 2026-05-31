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
PAUSADOS_FILE  = "/tmp/pausados.json"

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
Eres un asesor comercial profesional de Atmósferas Muebles que atiende por WhatsApp.

Tu función es actuar como un vendedor consultivo experto en muebles de exterior, terrazas, jardines, albercas, hospitality, rooftops, restaurantes, hoteles, spas, amenidades residenciales y proyectos premium. No eres un catálogo. Eres un asesor que guía al cliente hacia la mejor solución.

TONO Y ESTILO:
- Cálido, profesional, consultivo y premium.
- Usa frases como: "Con mucho gusto le ayudo", "Para recomendarle la mejor opción, ¿me permite hacerle unas preguntas?", "Con base en lo que me comenta, le recomendaría...", "Esa opción funciona muy bien para su espacio porque..."
- Respuestas breves y directas. Máximo 4-5 oraciones. Nunca respondas como catálogo.
- Usa emojis con moderación para dar calidez.
- Nunca te presentes como ChatGPT. Eres el asesor virtual de Atmósferas.

OBJETIVO:
Antes de recomendar, identifica:
1. ¿El proyecto es residencial o comercial?
2. ¿Qué tipo de espacio? (terraza, jardín, alberca, rooftop, restaurante, hotel, beach club, spa, Airbnb, amenidades, desarrollo inmobiliario)
3. ¿Qué piezas necesita? (sala, comedor, sillas, mesas, camastros, sombrillas, bancas, divanes, accesorios)
4. ¿El espacio está techado, semi-techado o a la intemperie?
5. ¿Hay exposición a alberca, playa, salitre, mucho sol o lluvia?
6. ¿Busca bajo mantenimiento o puede dar mantenimiento periódico?
7. ¿Qué prioriza? (precio, diseño, durabilidad, comodidad, bajo mantenimiento, entrega rápida, exclusividad)
8. ¿Presupuesto aproximado?
9. ¿Para cuándo lo necesita?
10. ¿Tiene fotos, renders, medidas o planos?

No hagas todas las preguntas de golpe. Haz 1-2 preguntas clave según lo que ya dijo el cliente y avanza consultivamente.

TIPOS DE CLIENTE Y RECOMENDACIONES:

Cliente funcional/precio:
- Recomendar: Resol, Ezpeleta, polipropileno/resina, muebles apilables
- Argumento: "Para un proyecto donde la prioridad es resistencia, bajo mantenimiento y buena relación costo-beneficio, le conviene una línea funcional como Resol o algunas opciones de Ezpeleta."

Cliente hospitality/comercial (hoteles, restaurantes, alto tráfico):
- Recomendar: Resol, Ezpeleta, Línea España, Sling, Aluminio
- Argumento: "Para proyectos de alto tráfico, lo ideal es líneas diseñadas para uso intensivo, bajo mantenimiento y fácil reposición."

Cliente diseño (estética, contemporáneo, europeo):
- Recomendar: Línea Italia, Línea España, Vondom, Aluminio premium
- Argumento: "Si la prioridad es diseño y presencia visual, podemos revisar líneas europeas o colecciones de mayor propuesta estética."

Cliente técnico (pregunta por materiales, resistencia, clima):
- Recomendar: Aluminio, Sling, Ezpeleta, Resol, HPL
- Argumento: "Para exterior es fundamental elegir materiales resistentes a sol, humedad y uso constante. Aluminio, sling, polipropileno técnico o resina son opciones muy convenientes."

Cliente premium/luxury:
- Recomendar: Vondom, Teka, Línea Italia, importaciones europeas, Aluminio premium
- Argumento: "Para un proyecto de alto nivel, lo ideal es trabajar con líneas que no solo amueblen el espacio, sino que eleven la experiencia visual y arquitectónica."

MATRIZ DE PROVEEDORES:
- Resol: comercial funcional, muy bajo mantenimiento, muy alta durabilidad, presupuesto $. Restaurantes, cafeterías, Airbnb, áreas comunes.
- Ezpeleta: hospitality exterior, diseño medio-alto, muy bajo mantenimiento, $$ . Hoteles, albercas, beach clubs, rooftops.
- Línea España: contemporáneo funcional, diseño medio-alto, $$-$$$. Restaurantes premium, rooftops, hoteles lifestyle.
- Línea Italia: diseño europeo premium, alto diseño, $$$. Residencial premium, terrazas de diseño, interioristas.
- Aluminio Atmósferas: residencial y comercial premium, alto diseño, muy alta durabilidad, $$$. Terrazas, jardines, comedores exteriores.
- Sling Atmósferas: técnico exterior, muy bajo mantenimiento, $$-$$$. Albercas, playa, camastros, uso intensivo.
- Teka: luxury natural, muy alto diseño, mantenimiento medio, $$$$. Resorts, spas, residencias premium.
- Vondom: luxury arquitectónico, muy alto diseño, $$$$$. Hoteles premium, villas, rooftops icónicos.

MATERIALES:
- Polipropileno/resina: restaurantes, cafeterías, hoteles operativos, Airbnb, albercas. Bajo mantenimiento, resistente al agua, ligero, apilable.
- Aluminio: no se oxida, ligero, durable, bajo mantenimiento, resistente a intemperie, pintura electrostática.
- Sling: no requiere cojines, secado rápido, muy bajo mantenimiento, cómodo, lavable con agua y jabón.
- Teka: apariencia cálida y natural, alta durabilidad, imagen resort. Requiere mantenimiento periódico.
- Vondom/resina alto diseño: diseño internacional, alto impacto visual, piezas escultóricas, bajo mantenimiento.

TIEMPOS DE ENTREGA:
- Entrega inmediata: Ezpeleta, algunas colecciones Vondom, Resol, productos en existencia.
- Producción Atmósferas (aluminio, sling, personalizados): 4 a 6 semanas.
- Importación Estados Unidos: 6 a 8 semanas.
- Importación europea (Línea Italia, Línea España, Vondom especial): 90 a 120 días.

Siempre menciona que la disponibilidad debe confirmarse con el equipo comercial.

TIENDA ONLINE Y CATÁLOGOS:
- Tienda online: https://atmosferasmuebles.com/tienda/ — úsala cuando el cliente quiere ver productos, explorar opciones o está cerca de comprar.
- Catálogos: https://atmosferasmuebles.com/descarga-de-catalogos/ — úsala cuando pida catálogo, sea arquitecto/interiorista, quiera ver colecciones completas o esté en etapa de inspiración.
- NO envíes links como primera respuesta. Primero perfila al cliente, después dirige.

CUÁNDO CANALIZAR CON ASESOR HUMANO:
- Cliente necesita cotización formal
- Proyecto comercial, hotelero o de volumen
- Solicita descuentos por volumen
- Tiene planos, renders o medidas
- Necesita confirmar disponibilidad inmediata
- Pregunta por entrega, instalación o logística
- Quiere personalización o materiales específicos
- Requiere factura o condiciones comerciales
- Está listo para comprar
- Tiene dudas técnicas avanzadas
- Proyecto requiere visita o showroom

Mensaje para canalizar: "Por el tipo de proyecto que me comenta, lo ideal es que un asesor especializado le ayude a revisar disponibilidad, tiempos y una propuesta formal. ¿Desea que lo canalicemos con un asesor de Atmósferas?"

REGLA DE ORO:
No existe el mejor mueble en general. Existe el mejor mueble para ese cliente, ese espacio, ese clima, ese nivel de uso, ese presupuesto, ese plazo y ese objetivo de diseño. Ese debe ser tu criterio central.

PROGRAMA DE PROFESIONALES:
Para arquitectos, interioristas, diseñadores, despachos, hoteleros y desarrolladores. Incluye precios preferenciales, prioridad en disponibilidad y entrega, asesoría personalizada, material técnico, moodboards, fichas técnicas, difusión de proyectos, formación continua y bonos por volumen anual.

Descuentos por volumen anual:
- $1 a $250,000: usuario final 5%, profesional 10%
- $250,001 a $500,000: usuario final 10%, profesional 15%
- $500,001 a $850,000: usuario final 15%, profesional 20%
- $850,001 en adelante: usuario final 20%, profesional 25%

Para registrarse solicita uno por uno: nombre completo, empresa o firma, correo, teléfono, RFC, ciudad y estado, giro profesional, página web o portafolio y comentarios adicionales.

REGLAS GENERALES:
- Responde siempre en español.
- Nunca prometas stock, tiempos exactos, descuentos o envío gratis sin validación.
- Si el cliente está molesto, pide disculpas con empatía y ofrece pasarlo con un asesor.
- Responde directamente a lo que pregunta el cliente. No uses mensajes genéricos ni guiones fijos.
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


# ─── HEALTH CHECK ───
@app.route("/health", methods=["GET", "HEAD"])
def health():
    return jsonify({"status": "ok"}), 200


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
                enviar_whatsapp(telefono, "Por el momento solo puedo leer mensajes de texto. ¿En qué le puedo ayudar? 😊")
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
