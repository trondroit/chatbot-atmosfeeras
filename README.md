# Chatbot WhatsApp — Atmósferas Muebles

Asesor virtual de ventas por WhatsApp. Recibe los mensajes de los clientes
vía webhook (Meta WhatsApp Cloud API u Odoo), genera la respuesta con
OpenAI y la envía por WhatsApp; opcionalmente registra la conversación en
Odoo y crea leads en el CRM.

## Estructura del proyecto

| Archivo | Qué hace |
|---|---|
| `app.py` | Servidor Flask: rutas, seguridad de webhooks, orquestación |
| `config.py` | Variables de entorno y configuración de logging |
| `prompts.py` | Prompt del sistema (personalidad y conocimiento del asesor) |
| `ai.py` | Llamadas a OpenAI: respuestas, análisis de fotos, transcripción de audios |
| `whatsapp_api.py` | API de WhatsApp Cloud: enviar, marcar leído, descargar media |
| `messenger_api.py` | Send API de Facebook Messenger: enviar, indicadores, descargar adjuntos |
| `odoo_client.py` | XML-RPC de Odoo: registrar respuestas y crear leads |
| `storage.py` | Estado persistente: historiales, pausados y deduplicación (Redis o archivo) |
| `chatbot_whatsapp.py` | Shim de compatibilidad para los comandos de arranque anteriores |
| `tests/` | Pruebas automatizadas (pytest) |

## Variables de entorno

### Obligatorias

| Variable | Descripción |
|---|---|
| `VERIFY_TOKEN` | Token de verificación del webhook de Meta |
| `WHATSAPP_TOKEN` | Token de acceso de la WhatsApp Cloud API |
| `PHONE_NUMBER_ID` | ID del número de teléfono en Meta |
| `OPENAI_API_KEY` | API key de OpenAI |

### Seguridad (muy recomendadas)

| Variable | Descripción |
|---|---|
| `META_APP_SECRET` | App Secret de la app de Meta. Si está definido, se valida la firma `X-Hub-Signature-256` de cada webhook y se rechaza cualquier petición no firmada por Meta. **Sin esto, cualquiera que conozca la URL puede hacer que el bot responda.** |
| `WEBHOOK_SALIENTE_TOKEN` | Token compartido para los webhooks que manda Odoo. Odoo debe enviarlo en el header `X-Webhook-Token` (o como `?token=...` en la URL). Protege la pausa/reactivación del bot y el webhook de mensajes vía Odoo. |

### Facebook Messenger (opcional)

| Variable | Descripción |
|---|---|
| `PAGE_ACCESS_TOKEN` | Token de acceso de la Página de Facebook. Si está definido, el bot atiende también los mensajes de Messenger que Meta entrega en `/webhook` (evento `object: "page"`). La verificación del webhook y la firma se comparten con WhatsApp (`VERIFY_TOKEN` y `META_APP_SECRET`). Sin este token, los eventos de Messenger se ignoran. |

Para conectarlo en Meta for Developers: agrega el producto **Messenger** a la
misma app, genera el **Page Access Token** de tu Página, y en **Webhooks**
suscribe el objeto **page** a los campos `messages` y `messaging_postbacks`
(y `message_echoes` si quieres que un agente humano pueda pausar/reactivar el
bot desde la Bandeja de entrada de Meta Business Suite). El Callback URL es el
mismo `/webhook` de este servicio.

Instagram usa exactamente esta misma Send API y llega al mismo `/webhook`
(evento `object: "instagram"`); se puede habilitar con muy pocos cambios.

### Odoo (opcionales)

| Variable | Descripción |
|---|---|
| `ODOO_URL`, `ODOO_DB`, `ODOO_USER`, `ODOO_API_KEY` | Credenciales XML-RPC |
| `WA_ACCOUNT_ID` | ID de la cuenta de WhatsApp en Odoo (default: `3`) |
| `ODOO_CREAR_LEADS` | `1` para crear un lead en el CRM cuando el bot ofrece canalizar con un asesor (máx. uno por número cada 24 h). Default: desactivado |

### Otras (opcionales)

| Variable | Descripción |
|---|---|
| `REDIS_URL` | URL de Redis (p. ej. `redis://...`). **Recomendado en producción**: el historial y los números pausados sobreviven reinicios y se comparten entre workers. Sin Redis se usa un archivo JSON en `DATA_DIR`, que solo es seguro con 1 worker |
| `DATA_DIR` | Carpeta del archivo de estado si no hay Redis (default: `/tmp`) |
| `OPENAI_MODEL` | Modelo de chat (default: `gpt-4o-mini`) |
| `OPENAI_TRANSCRIBE_MODEL` | Modelo de transcripción de audios (default: `whisper-1`) |
| `OPENAI_TIMEOUT` | Timeout en segundos para OpenAI (default: `30`) |
| `HISTORIAL_MAX` | Mensajes de historial que se conservan por número (default: `30`) |
| `GRAPH_API_VERSION` | Versión de la Graph API (default: `v22.0`) |
| `LOG_LEVEL` | Nivel de logging (default: `INFO`) |

## Cómo correr

```bash
pip install -r requirements.txt

# Desarrollo
python app.py

# Producción (los webhooks se procesan en hilos; usar --threads)
gunicorn app:app --workers 1 --threads 8
```

El comando anterior `gunicorn chatbot_whatsapp:app` sigue funcionando
(es un alias de `app:app`).

> **Nota sobre workers:** sin `REDIS_URL`, usar `--workers 1` (el estado en
> archivo no se comparte entre procesos). Con Redis se puede escalar a
> varios workers sin problema.

## Funcionamiento

- **Mensajes entrantes** (`POST /webhook`): se valida la firma de Meta, se
  descartan duplicados (Meta reintenta si no recibe el 200 rápido) y se
  responde `200` de inmediato; la IA y el envío corren en segundo plano.
- **Fotos**: se descargan y se analizan con el modelo de visión para afinar
  la recomendación.
- **Notas de voz**: se transcriben con Whisper y se responden como texto.
- **Leído/escribiendo**: el mensaje del cliente se marca como leído y se
  muestra el indicador de "escribiendo…" mientras se genera la respuesta.
- **Pausa del bot** (`POST /webhook-saliente`): cuando un asesor escribe
  desde Odoo una frase que contiene «un asesor te atenderá», el bot se pausa
  para ese número; «gracias por comunicarse a atmosferas» lo reactiva (se
  acepta también la variante histórica «comunicarce»). También funcionan los
  comandos `#bot-off` y `#bot-on`. Las comparaciones ignoran mayúsculas y
  acentos.
- **El cliente pide un asesor**: cuando el cliente expresa que quiere hablar
  con una persona (el modelo lo detecta y responde con el marcador interno
  `[PASAR_A_ASESOR]`), el bot se **pausa solo** para ese número y le confirma
  al cliente que un asesor le atenderá. El equipo ve la conversación en Odoo
  y la toma; luego reactiva el bot con la frase de siempre o con `#bot-on`.
- **Facebook Messenger** (si `PAGE_ACCESS_TOKEN` está configurado): el mismo
  bot atiende los mensajes de Messenger directo desde Meta (texto, fotos y
  notas de voz). El estado se guarda por canal (`msgr:<psid>`), así que un
  usuario de Messenger nunca se cruza con un número de WhatsApp. El paso a
  asesor funciona igual; y si un agente humano responde desde la Bandeja de
  Meta Business Suite, sus frases («un asesor te atenderá», `#bot-off`,
  `#bot-on`, etc.) pausan/reactivan el bot igual que un asesor en Odoo
  (requiere suscribir `message_echoes`).
- **Leads**: con `ODOO_CREAR_LEADS=1`, cuando el bot ofrece canalizar con un
  asesor se crea automáticamente un lead en el CRM de Odoo con el resumen de
  la conversación.

## Pruebas

```bash
pip install -r requirements-dev.txt
pytest
```
