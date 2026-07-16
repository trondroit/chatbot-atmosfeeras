import json

import app as app_module
from conftest import (firmar, payload_messenger_texto, payload_meta_texto,
                      post_meta)


# ─── Verificación del webhook (GET) ───

def test_verificacion_correcta(entorno):
    client, _ = entorno
    resp = client.get("/webhook", query_string={
        "hub.mode": "subscribe",
        "hub.verify_token": "test-verify",
        "hub.challenge": "reto-123",
    })
    assert resp.status_code == 200
    assert resp.get_data(as_text=True) == "reto-123"


def test_verificacion_token_incorrecto(entorno):
    client, _ = entorno
    resp = client.get("/webhook", query_string={
        "hub.mode": "subscribe",
        "hub.verify_token": "otro-token",
        "hub.challenge": "reto-123",
    })
    assert resp.status_code == 403


# ─── Firma de Meta ───

def test_mensaje_meta_con_firma_valida_se_responde(entorno):
    client, enviados = entorno
    resp = post_meta(client, payload_meta_texto(texto="busco camastros"))
    assert resp.status_code == 200
    assert enviados == [("5215550001111", "eco:busco camastros")]


def test_mensaje_meta_sin_firma_se_rechaza(entorno):
    client, enviados = entorno
    body = json.dumps(payload_meta_texto()).encode()
    resp = client.post("/webhook", data=body,
                       headers={"Content-Type": "application/json"})
    assert resp.status_code == 403
    assert enviados == []


def test_mensaje_meta_con_firma_invalida_se_rechaza(entorno):
    client, enviados = entorno
    body = json.dumps(payload_meta_texto()).encode()
    resp = client.post("/webhook", data=body, headers={
        "Content-Type": "application/json",
        "X-Hub-Signature-256": "sha256=" + "0" * 64,
    })
    assert resp.status_code == 403
    assert enviados == []


# ─── Deduplicación ───

def test_mensaje_duplicado_se_responde_una_sola_vez(entorno):
    client, enviados = entorno
    payload = payload_meta_texto(msg_id="wamid.repetido")
    post_meta(client, payload)
    post_meta(client, payload)
    assert len(enviados) == 1


def test_varios_mensajes_en_un_webhook_se_procesan_todos(entorno):
    client, enviados = entorno
    payload = payload_meta_texto(msg_id="wamid.a")
    payload["entry"][0]["changes"][0]["value"]["messages"].append({
        "id": "wamid.b",
        "from": "5215550002222",
        "type": "text",
        "text": {"body": "segundo"},
    })
    post_meta(client, payload)
    assert len(enviados) == 2


# ─── Pausa y reactivación desde Odoo ───

def _post_saliente(client, telefono, body):
    return client.post(
        "/webhook-saliente",
        json={"mobile_number": telefono, "body": body},
        headers={"X-Webhook-Token": "token-odoo"},
    )


def test_pausa_y_reactivacion(entorno):
    client, enviados = entorno
    tel = "5215550001111"

    _post_saliente(client, tel, "Hola, un asesor te atenderá en un momento")
    post_meta(client, payload_meta_texto(telefono=tel, msg_id="wamid.p1"))
    assert enviados == []  # pausado: el bot no responde

    # La frase corregida (sin el error de dedo histórico) también reactiva.
    _post_saliente(client, tel, "Gracias por comunicarse a Atmósferas")
    post_meta(client, payload_meta_texto(telefono=tel, msg_id="wamid.p2"))
    assert len(enviados) == 1


def test_reactivacion_con_typo_historico(entorno):
    client, enviados = entorno
    tel = "5215550001111"
    _post_saliente(client, tel, "un asesor te atenderá")
    _post_saliente(client, tel, "gracias por comunicarce a atmosferas")
    post_meta(client, payload_meta_texto(telefono=tel, msg_id="wamid.p3"))
    assert len(enviados) == 1


def test_comandos_bot_off_on(entorno):
    client, enviados = entorno
    tel = "5215550001111"
    _post_saliente(client, tel, "#bot-off")
    post_meta(client, payload_meta_texto(telefono=tel, msg_id="wamid.c1"))
    assert enviados == []
    _post_saliente(client, tel, "#bot-on")
    post_meta(client, payload_meta_texto(telefono=tel, msg_id="wamid.c2"))
    assert len(enviados) == 1


def test_cliente_pide_asesor_pausa_el_bot(entorno, monkeypatch):
    client, enviados = entorno
    tel = "5215550009999"
    # Simula que la IA detecta que el cliente quiere un humano.
    monkeypatch.setattr(app_module.ai, "responder",
                        lambda t, txt, *a, **k: (None, True))

    post_meta(client, payload_meta_texto(telefono=tel, texto="quiero un asesor",
                                         msg_id="wamid.h1"))
    # Se le confirma al cliente una sola vez con el mensaje de paso a asesor.
    assert enviados == [(tel, app_module.MENSAJE_PASO_ASESOR)]

    # Y a partir de ahí el bot queda pausado para ese número.
    monkeypatch.setattr(app_module.ai, "responder",
                        lambda t, txt, *a, **k: ("no debería enviarse", False))
    post_meta(client, payload_meta_texto(telefono=tel, texto="hola de nuevo",
                                         msg_id="wamid.h2"))
    assert len(enviados) == 1


def test_webhook_saliente_sin_token_se_rechaza(entorno):
    client, _ = entorno
    resp = client.post("/webhook-saliente",
                       json={"mobile_number": "5215550001111",
                             "body": "un asesor te atenderá"})
    assert resp.status_code == 403


# ─── Facebook Messenger ───

def test_messenger_texto_se_responde(entorno):
    client, enviados = entorno
    resp = post_meta(client, payload_messenger_texto(texto="hola bot"))
    assert resp.status_code == 200
    assert enviados == [("PSID123", "eco:hola bot")]


def test_messenger_sin_firma_se_rechaza(entorno):
    client, enviados = entorno
    body = json.dumps(payload_messenger_texto()).encode()
    resp = client.post("/webhook", data=body,
                       headers={"Content-Type": "application/json"})
    assert resp.status_code == 403
    assert enviados == []


def test_messenger_duplicado_se_ignora(entorno):
    client, enviados = entorno
    payload = payload_messenger_texto(mid="m.dup")
    post_meta(client, payload)
    post_meta(client, payload)
    assert len(enviados) == 1


def test_messenger_cliente_pide_asesor_pausa(entorno, monkeypatch):
    client, enviados = entorno
    monkeypatch.setattr(app_module.ai, "responder",
                        lambda t, txt, *a, **k: (None, True))
    post_meta(client, payload_messenger_texto(texto="quiero un asesor",
                                              mid="m.h1"))
    assert enviados == [("PSID123", app_module.MENSAJE_PASO_ASESOR)]
    # Queda pausado para ese PSID.
    monkeypatch.setattr(app_module.ai, "responder",
                        lambda t, txt, *a, **k: ("no enviar", False))
    post_meta(client, payload_messenger_texto(texto="hola", mid="m.h2"))
    assert len(enviados) == 1


def test_messenger_echo_de_agente_pausa_y_reactiva(entorno):
    client, enviados = entorno
    # Un agente humano escribe desde la Bandeja (eco sin app_id).
    post_meta(client, payload_messenger_texto(
        texto="En seguida un asesor te atenderá", mid="e.1", echo=True))
    post_meta(client, payload_messenger_texto(texto="hola", mid="m.1"))
    assert enviados == []  # pausado

    post_meta(client, payload_messenger_texto(
        texto="#bot-on", mid="e.2", echo=True))
    post_meta(client, payload_messenger_texto(texto="hola otra vez", mid="m.2"))
    assert len(enviados) == 1


def test_messenger_echo_propio_del_bot_se_ignora(entorno):
    client, enviados = entorno
    # Eco de un envío del propio bot (con app_id): no debe pausar nada.
    post_meta(client, payload_messenger_texto(
        texto="un asesor te atenderá", mid="e.9", echo=True, app_id="999"))
    post_meta(client, payload_messenger_texto(texto="hola", mid="m.9"))
    assert enviados == [("PSID123", "eco:hola")]


# ─── Instagram (mismo formato y misma Send API que Messenger) ───

def test_instagram_texto_se_responde(entorno):
    client, enviados = entorno
    resp = post_meta(client, payload_messenger_texto(
        psid="IGSID9", texto="hola por IG", mid="ig.1", obj="instagram"))
    assert resp.status_code == 200
    assert enviados == [("IGSID9", "eco:hola por IG")]


def test_instagram_e_messenger_no_se_cruzan(entorno):
    client, enviados = entorno
    # Mismo id en ambos canales: el estado se guarda por separado (msgr: vs ig:).
    post_meta(client, payload_messenger_texto(
        psid="MISMO", texto="soy messenger", mid="mx.1", obj="page"))
    post_meta(client, payload_messenger_texto(
        psid="MISMO", texto="soy instagram", mid="ig.2", obj="instagram"))
    assert ("MISMO", "eco:soy messenger") in enviados
    assert ("MISMO", "eco:soy instagram") in enviados
    assert len(enviados) == 2


# ─── Payload estilo Odoo en /webhook ───

def test_mensaje_via_odoo_requiere_token(entorno):
    client, enviados = entorno
    resp = client.post("/webhook", json={
        "mobile_number": "5215550003333",
        "body": "<p>hola desde odoo</p>",
        "id": 42,
    })
    assert resp.status_code == 403
    assert enviados == []


def test_mensaje_via_odoo_con_token_responde_y_limpia_html(entorno):
    client, enviados = entorno
    resp = client.post(
        "/webhook",
        json={"mobile_number": "5215550003333",
              "body": "<p>hola desde odoo</p>", "id": 42},
        headers={"X-Webhook-Token": "token-odoo"},
    )
    assert resp.status_code == 200
    assert enviados == [("5215550003333", "eco:hola desde odoo")]
