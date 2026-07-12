"""Cliente XML-RPC de Odoo: registro de respuestas del bot en el chat
de WhatsApp de Odoo y creación de leads en el CRM.

La autenticación (uid) se cachea para no re-autenticar en cada mensaje;
si una llamada falla, se invalida la sesión y se reintenta una vez.
"""
import logging
import threading
import xmlrpc.client

import config

log = logging.getLogger(__name__)

_lock = threading.Lock()
_uid = None


def _conectar():
    global _uid
    with _lock:
        if _uid is None:
            common = xmlrpc.client.ServerProxy(f"{config.ODOO_URL}/xmlrpc/2/common")
            uid = common.authenticate(config.ODOO_DB, config.ODOO_USER,
                                      config.ODOO_API_KEY, {})
            if not uid:
                raise RuntimeError("autenticación de Odoo rechazada")
            _uid = uid
        models = xmlrpc.client.ServerProxy(f"{config.ODOO_URL}/xmlrpc/2/object")
        return _uid, models


def _invalidar_sesion():
    global _uid
    with _lock:
        _uid = None


def _execute(models, uid, modelo, metodo, args, kwargs=None):
    return models.execute_kw(config.ODOO_DB, uid, config.ODOO_API_KEY,
                             modelo, metodo, args, kwargs or {})


def registrar_respuesta(telefono, respuesta_ia, odoo_message_id,
                        wa_account_id=None):
    """Publica la respuesta del bot en el canal de Odoo del cliente, o la
    registra como mensaje saliente de WhatsApp si no hay canal."""
    wa_account_id = wa_account_id or config.WA_ACCOUNT_ID
    for intento in (1, 2):
        try:
            uid, models = _conectar()
            mensaje_original = _execute(
                models, uid, "whatsapp.message", "read",
                [[odoo_message_id]],
                {"fields": ["mail_message_id", "wa_account_id"]},
            )
            if not mensaje_original:
                return
            mail_message_id = mensaje_original[0].get("mail_message_id")
            if isinstance(mail_message_id, list):
                mail_message_id = mail_message_id[0]
            canal = _execute(
                models, uid, "mail.message", "read",
                [[mail_message_id]],
                {"fields": ["res_id", "model"]},
            )
            if canal and canal[0].get("model") == "discuss.channel":
                channel_id = canal[0].get("res_id")
                _execute(
                    models, uid, "discuss.channel", "message_post",
                    [channel_id],
                    {"body": respuesta_ia, "message_type": "comment",
                     "author_id": uid},
                )
                log.info("Respuesta posteada en canal Odoo %s", channel_id)
            else:
                _execute(
                    models, uid, "whatsapp.message", "create",
                    [{
                        "mobile_number": telefono,
                        "body": respuesta_ia,
                        "message_type": "outbound",
                        "state": "sent",
                        "wa_account_id": wa_account_id,
                        "parent_id": odoo_message_id,
                    }],
                )
            return
        except Exception as e:
            _invalidar_sesion()
            if intento == 2:
                log.error("Error registrando respuesta en Odoo: %s", e)


def crear_lead(telefono, descripcion):
    """Crea un lead en el CRM cuando el bot detecta un cliente listo para
    hablar con un asesor. Solo si ODOO_CREAR_LEADS=1."""
    if not config.ODOO_CREAR_LEADS:
        return
    for intento in (1, 2):
        try:
            uid, models = _conectar()
            lead_id = _execute(
                models, uid, "crm.lead", "create",
                [{
                    "name": f"WhatsApp {telefono} — cliente pide asesor",
                    "phone": telefono,
                    "description": descripcion,
                    "type": "lead",
                }],
            )
            log.info("Lead creado en Odoo: %s", lead_id)
            return
        except Exception as e:
            _invalidar_sesion()
            if intento == 2:
                log.error("Error creando lead en Odoo: %s", e)
