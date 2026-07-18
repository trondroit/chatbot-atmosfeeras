"""Auto-renovador del token de Instagram.

El token de acceso de Instagram (Instagram Login API) caduca a los ~60 días.
Este módulo lo refresca solo, antes de que expire, y guarda el token nuevo en
el almacenamiento (Redis en producción). Así el bot nunca deja de responder
por Instagram sin que nadie tenga que tocar nada.

Flujo:
- El token vigente se guarda en storage bajo {token, expires_at, refreshed_at}.
- Un hilo en segundo plano revisa cada 12 h si le quedan pocos días de vida y,
  si es así, llama al endpoint refresh_access_token de Instagram (extiende otros
  ~60 días) y guarda el nuevo.
- messenger_api usa siempre el token vigente vía obtener_token().
"""
import logging
import threading
import time

import requests

import config
import storage

log = logging.getLogger(__name__)

INTERVALO_SEGUNDOS = 12 * 3600
_iniciado = False
_lock = threading.Lock()


def obtener_token():
    """Token de Instagram vigente: el renovado si existe, si no el de la
    variable de entorno."""
    info = storage.leer_ig_token()
    if info and info.get("token"):
        return info["token"]
    return config.IG_ACCESS_TOKEN


def _llamar_refresh(token):
    """Pide a Instagram extender el token 60 días más. Devuelve el JSON de la
    respuesta ({access_token, expires_in}) o None si falla."""
    try:
        resp = requests.get(
            f"{config.IG_GRAPH_HOST}/refresh_access_token",
            params={"grant_type": "ig_refresh_token", "access_token": token},
            timeout=30,
        )
        if resp.status_code >= 400:
            log.warning("No se pudo refrescar el token de Instagram (%s): %s",
                        resp.status_code, resp.text[:200])
            return None
        return resp.json()
    except requests.RequestException as e:
        log.warning("Error al refrescar el token de Instagram: %s", e)
        return None


def _refrescar_si_necesario():
    info = storage.leer_ig_token() or {}
    token = info.get("token") or config.IG_ACCESS_TOKEN
    if not token:
        return

    ahora = time.time()
    expires_at = info.get("expires_at")
    margen = config.IG_TOKEN_DIAS_MARGEN * 86400
    if expires_at and (expires_at - ahora) > margen:
        return  # aún tiene margen de sobra; no hace falta refrescar

    nuevo = _llamar_refresh(token)
    if nuevo and nuevo.get("access_token"):
        storage.guardar_ig_token({
            "token": nuevo["access_token"],
            "expires_at": ahora + int(nuevo.get("expires_in", 5000000)),
            "refreshed_at": ahora,
        })
        log.info("Token de Instagram renovado; vence en ~%d días",
                 int(nuevo.get("expires_in", 0)) // 86400)
    elif not info:
        # Aún no se pudo refrescar (p. ej. el token es muy nuevo, <24 h);
        # siembra el token actual para no perder el rastro y reintentar luego.
        storage.guardar_ig_token({"token": token, "expires_at": None,
                                  "refreshed_at": ahora})


def _bucle():
    while True:
        try:
            _refrescar_si_necesario()
        except Exception as e:
            log.error("Auto-renovador de Instagram: %s", e)
        time.sleep(INTERVALO_SEGUNDOS)


def iniciar_renovador():
    """Arranca el hilo de renovación (una sola vez). No hace nada si no hay
    token de Instagram configurado."""
    global _iniciado
    if not config.IG_ACCESS_TOKEN:
        return
    with _lock:
        if _iniciado:
            return
        _iniciado = True
    threading.Thread(target=_bucle, daemon=True).start()
    log.info("Auto-renovador del token de Instagram iniciado")
