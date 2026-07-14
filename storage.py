"""Almacenamiento del estado del bot: historiales, números pausados y
deduplicación de mensajes.

Se usa Redis si REDIS_URL está definido (recomendado en producción: el
estado sobrevive reinicios y se comparte entre todos los workers de
gunicorn). Si no hay Redis, se usa un archivo JSON como respaldo, que
solo es seguro con una instancia y un worker.
"""
import json
import logging
import os
import threading
import time

import config

log = logging.getLogger(__name__)

# Los IDs de mensajes procesados (y los leads creados) se recuerdan 24 h.
DEDUP_TTL_SEGUNDOS = 24 * 3600

# Archivo de pausados de la versión anterior del bot; se migra si existe.
LEGACY_PAUSADOS_FILE = "/tmp/pausados.json"


class FileStorage:
    """Estado en un archivo JSON local. Respaldo cuando no hay Redis."""

    def __init__(self, ruta):
        self._ruta = ruta
        self._lock = threading.Lock()
        self._historiales = {}
        self._pausados = set()
        self._procesados = {}  # clave -> timestamp
        self._cargar()

    def _cargar(self):
        try:
            with open(self._ruta, "r") as f:
                data = json.load(f)
            self._historiales = data.get("historiales", {})
            self._pausados = set(data.get("pausados", []))
            self._procesados = data.get("procesados", {})
            return
        except FileNotFoundError:
            pass
        except (OSError, json.JSONDecodeError) as e:
            log.warning("No se pudo leer el estado de %s: %s", self._ruta, e)
        # Migración desde el archivo de pausados de la versión anterior.
        try:
            with open(LEGACY_PAUSADOS_FILE, "r") as f:
                self._pausados = set(json.load(f))
            log.info("Pausados migrados desde %s", LEGACY_PAUSADOS_FILE)
        except (OSError, json.JSONDecodeError):
            pass

    def _guardar(self):
        try:
            tmp = self._ruta + ".tmp"
            with open(tmp, "w") as f:
                json.dump({
                    "historiales": self._historiales,
                    "pausados": sorted(self._pausados),
                    "procesados": self._procesados,
                }, f, ensure_ascii=False)
            os.replace(tmp, self._ruta)
        except OSError as e:
            log.warning("No se pudo guardar el estado en %s: %s", self._ruta, e)

    def historial(self, telefono):
        with self._lock:
            return list(self._historiales.get(telefono, []))

    def agregar_mensaje(self, telefono, role, content):
        with self._lock:
            h = self._historiales.setdefault(telefono, [])
            h.append({"role": role, "content": content})
            del h[:-config.HISTORIAL_MAX]
            self._guardar()

    def esta_pausado(self, telefono):
        with self._lock:
            return telefono in self._pausados

    def pausar(self, telefono):
        with self._lock:
            self._pausados.add(telefono)
            self._guardar()

    def reanudar(self, telefono):
        with self._lock:
            self._pausados.discard(telefono)
            self._guardar()

    def ya_procesado(self, clave):
        """Devuelve True si la clave ya se vio; si no, la marca y devuelve False."""
        ahora = time.time()
        with self._lock:
            self._procesados = {
                k: t for k, t in self._procesados.items()
                if ahora - t < DEDUP_TTL_SEGUNDOS
            }
            if clave in self._procesados:
                return True
            self._procesados[clave] = ahora
            self._guardar()
            return False


class RedisStorage:
    """Estado en Redis: compartido entre workers y persistente."""

    def __init__(self, url):
        import redis  # import tardío: solo se necesita con REDIS_URL
        self._r = redis.from_url(url, decode_responses=True)
        self._r.ping()

    def historial(self, telefono):
        items = self._r.lrange(f"chatbot:historial:{telefono}", 0, -1)
        return [json.loads(i) for i in items]

    def agregar_mensaje(self, telefono, role, content):
        clave = f"chatbot:historial:{telefono}"
        self._r.rpush(clave, json.dumps({"role": role, "content": content},
                                        ensure_ascii=False))
        self._r.ltrim(clave, -config.HISTORIAL_MAX, -1)

    def esta_pausado(self, telefono):
        return bool(self._r.sismember("chatbot:pausados", telefono))

    def pausar(self, telefono):
        self._r.sadd("chatbot:pausados", telefono)

    def reanudar(self, telefono):
        self._r.srem("chatbot:pausados", telefono)

    def ya_procesado(self, clave):
        # SET NX: solo escribe si la clave no existía. Operación atómica,
        # segura aunque dos workers reciban el mismo webhook a la vez.
        creado = self._r.set(f"chatbot:procesado:{clave}", "1",
                             nx=True, ex=DEDUP_TTL_SEGUNDOS)
        return not creado


_backend = None
_backend_lock = threading.Lock()


def _crear_backend():
    if config.REDIS_URL:
        try:
            backend = RedisStorage(config.REDIS_URL)
            log.info("Almacenamiento: Redis")
            return backend
        except Exception as e:
            log.error("No se pudo conectar a Redis (%s); usando archivo local", e)
    ruta = os.path.join(config.DATA_DIR, "estado_chatbot.json")
    log.info("Almacenamiento: archivo %s", ruta)
    return FileStorage(ruta)


def get_backend():
    global _backend
    with _backend_lock:
        if _backend is None:
            _backend = _crear_backend()
        return _backend


# Funciones de conveniencia para no manejar el backend en el resto del código.
def historial(telefono):
    return get_backend().historial(telefono)


def agregar_mensaje(telefono, role, content):
    get_backend().agregar_mensaje(telefono, role, content)


def esta_pausado(telefono):
    return get_backend().esta_pausado(telefono)


def pausar(telefono):
    get_backend().pausar(telefono)


def reanudar(telefono):
    get_backend().reanudar(telefono)


def ya_procesado(clave):
    return get_backend().ya_procesado(clave)
