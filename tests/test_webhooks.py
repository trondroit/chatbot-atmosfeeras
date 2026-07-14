import json

from conftest import firmar, payload_meta_texto, post_meta


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


def test_webhook_saliente_sin_token_se_rechaza(entorno):
    client, _ = entorno
    resp = client.post("/webhook-saliente",
                       json={"mobile_number": "5215550001111",
                             "body": "un asesor te atenderá"})
    assert resp.status_code == 403


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
