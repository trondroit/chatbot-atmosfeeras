"""Punto de entrada de compatibilidad.

El código vive ahora en módulos separados (app.py, config.py, ai.py,
whatsapp_api.py, odoo_client.py, storage.py, prompts.py). Este archivo
existe solo para que los comandos de arranque anteriores sigan
funcionando, p. ej.:

    gunicorn chatbot_whatsapp:app
    python chatbot_whatsapp.py
"""
from app import app  # noqa: F401

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
