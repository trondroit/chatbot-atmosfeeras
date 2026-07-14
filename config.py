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
GRAPH_API_VERSION = os.environ.get("GRAPH_API_VERSION", "v22.0")
GRAPH_API_URL     = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

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
