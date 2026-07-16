import os
import sys

# Variables de entorno de prueba: deben definirse ANTES de importar config.
os.environ["VERIFY_TOKEN"] = "test-verify"
os.environ["META_APP_SECRET"] = "secreto-test"
os.environ["WEBHOOK_SALIENTE_TOKEN"] = "token-odoo"
os.environ["OPENAI_API_KEY"] = "sk-test"
os.environ["PAGE_ACCESS_TOKEN"] = "page-token-test"
os.environ.pop("REDIS_URL", None)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hashlib
import hmac
import json

import pytest

import app as app_module
import storage


def firmar(body: bytes) -> str:
    return "sha256=" + hmac.new(b"secreto-test", body, hashlib.sha256).hexdigest()


def post_meta(client, payload):
    """POST /webhook con payload de Meta correctamente firmado."""
    body = json.dumps(payload).encode()
    return client.post(
        "/webhook",
        data=body,
        headers={"Content-Type": "application/json",
                 "X-Hub-Signature-256": firmar(body)},
    )


def payload_meta_texto(telefono="5215550001111", texto="hola", msg_id="wamid.1"):
    return {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "id": msg_id,
                        "from": telefono,
                        "type": "text",
                        "text": {"body": texto},
                    }],
                },
            }],
        }],
    }


def payload_messenger_texto(psid="PSID123", texto="hola", mid="m.1", echo=False,
                            app_id=None, obj="page"):
    mensaje = {"mid": mid}
    if echo:
        mensaje["is_echo"] = True
        if app_id:
            mensaje["app_id"] = app_id
    mensaje["text"] = texto
    evento = {"message": mensaje}
    if echo:
        evento["sender"] = {"id": "PAGE"}
        evento["recipient"] = {"id": psid}
    else:
        evento["sender"] = {"id": psid}
        evento["recipient"] = {"id": "PAGE"}
    return {"object": obj, "entry": [{"messaging": [evento]}]}


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    """Cliente de pruebas con almacenamiento limpio, IA y WhatsApp simulados,
    y procesamiento en línea (sin hilos) para poder hacer aserciones."""
    monkeypatch.setattr(
        storage, "_backend", storage.FileStorage(str(tmp_path / "estado.json"))
    )

    enviados = []
    monkeypatch.setattr(app_module.whatsapp_api, "enviar_mensaje",
                        lambda tel, txt: enviados.append((tel, txt)) or True)
    monkeypatch.setattr(app_module.whatsapp_api, "marcar_leido",
                        lambda mid: None)
    monkeypatch.setattr(app_module.messenger_api, "enviar_mensaje",
                        lambda psid, txt: enviados.append((psid, txt)) or True)
    monkeypatch.setattr(app_module.messenger_api, "marcar_visto",
                        lambda psid, escribiendo=True: None)
    monkeypatch.setattr(app_module.ai, "responder",
                        lambda tel, txt, *a, **k: (f"eco:{txt}", False))
    monkeypatch.setattr(app_module.odoo_client, "registrar_respuesta",
                        lambda *a, **k: None)
    monkeypatch.setattr(app_module, "_lanzar", lambda f, *args: f(*args))

    return app_module.app.test_client(), enviados
