"""Configuración central del chatbot: variables de entorno y logging."""
import logging
import os

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

# ─── WhatsApp / Meta ───
VERIFY_TOKEN      = os.environ.get("VERIFY_TOKEN")
WHATSAPP_TOKEN    = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID   = os.environ.get("PHONE_NUMBER_ID")
# App Secret de la app de Meta. Si está definido, se valida la firma
# X-Hub-Signature-256 de cada webhook entrante (muy recomendado).
META_APP_SECRET   = os.environ.get("META_APP_SECRET")
# La API de Instagram firma sus webhooks con el "Instagram App Secret", que
# es distinto del App Secret de Facebook. Si se define, también se acepta.
IG_APP_SECRET     = os.environ.get("IG_APP_SECRET")
GRAPH_API_VERSION = os.environ.get("GRAPH_API_VERSION", "v22.0")
GRAPH_API_URL     = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

# ─── Facebook Messenger e Instagram (opcional) ───
# Token de acceso de la Página de Facebook. Si está definido, el bot
# atiende también los mensajes de Messenger (object: "page") que Meta
# entrega en /webhook. La verificación del webhook y la firma se comparten
# con WhatsApp (VERIFY_TOKEN y META_APP_SECRET).
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
# ID numérico de la Página de Facebook. Si se define, Messenger envía por
# /{PAGE_ID}/messages en vez de /me/messages; así funciona también con
# tokens de usuario del sistema (donde "me" no resuelve a la Página).
PAGE_ID           = os.environ.get("PAGE_ID")

# Token propio de la cuenta de Instagram (se genera aparte del de la Página).
# Instagram envía por su propia API (graph.instagram.com). Si no se define,
# Instagram intenta usar PAGE_ACCESS_TOKEN por la Graph de Facebook (sirve
# cuando la cuenta de IG está ligada a la Página con ese token).
IG_ACCESS_TOKEN = os.environ.get("IG_ACCESS_TOKEN")
IG_GRAPH_HOST   = "https://graph.instagram.com"
IG_GRAPH_URL    = f"{IG_GRAPH_HOST}/{GRAPH_API_VERSION}"
# El token de Instagram caduca (~60 días). El auto-renovador lo refresca
# solo cuando le quedan menos de estos días de vida.
IG_TOKEN_DIAS_MARGEN = int(os.environ.get("IG_TOKEN_DIAS_MARGEN", "20"))

# ─── OpenAI ───
OPENAI_API_KEY          = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL            = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_TRANSCRIBE_MODEL = os.environ.get("OPENAI_TRANSCRIBE_MODEL", "whisper-1")
OPENAI_TIMEOUT          = float(os.environ.get("OPENAI_TIMEOUT", "30"))

# ─── Odoo ───
ODOO_URL      = os.environ.get("ODOO_URL")
ODOO_DB       = os.environ.get("ODOO_DB")
ODOO_USER     = os.environ.get("ODOO_USER")
ODOO_API_KEY  = os.environ.get("ODOO_API_KEY")
WA_ACCOUNT_ID = int(os.environ.get("WA_ACCOUNT_ID", "3"))
# Si vale "1", al detectar que el bot ofrece canalizar con un asesor
# se crea un lead en el CRM de Odoo (máximo uno por número cada 24 h).
ODOO_CREAR_LEADS = os.environ.get("ODOO_CREAR_LEADS", "0") == "1"

# Token compartido para los webhooks que llegan desde Odoo
# (/webhook con payload de Odoo y /webhook-saliente). Si está definido,
# Odoo debe mandarlo en el header X-Webhook-Token o como ?token=...
WEBHOOK_SALIENTE_TOKEN = os.environ.get("WEBHOOK_SALIENTE_TOKEN")

# ─── Almacenamiento ───
# Si REDIS_URL está definido se usa Redis (recomendado en producción:
# sobrevive reinicios y se comparte entre workers de gunicorn).
# Si no, se usa un archivo JSON en DATA_DIR como respaldo.
REDIS_URL = os.environ.get("REDIS_URL")
DATA_DIR  = os.environ.get("DATA_DIR", "/tmp")

# Cuántos mensajes de historial se conservan por número de teléfono.
HISTORIAL_MAX = int(os.environ.get("HISTORIAL_MAX", "30"))
