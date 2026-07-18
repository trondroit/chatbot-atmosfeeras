import time

import pytest

import config
import ig_token
import storage


@pytest.fixture(autouse=True)
def _backend_limpio(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "_backend",
                        storage.FileStorage(str(tmp_path / "estado.json")))


def test_obtener_token_desde_env(monkeypatch):
    monkeypatch.setattr(config, "IG_ACCESS_TOKEN", "env-token")
    assert ig_token.obtener_token() == "env-token"


def test_obtener_token_prefiere_el_guardado(monkeypatch):
    monkeypatch.setattr(config, "IG_ACCESS_TOKEN", "env-token")
    storage.guardar_ig_token({"token": "guardado", "expires_at": None,
                              "refreshed_at": 0})
    assert ig_token.obtener_token() == "guardado"


def test_refresca_y_guarda_el_nuevo(monkeypatch):
    monkeypatch.setattr(config, "IG_ACCESS_TOKEN", "viejo")
    monkeypatch.setattr(ig_token, "_llamar_refresh",
                        lambda t: {"access_token": "nuevo", "expires_in": 5000000})
    ig_token._refrescar_si_necesario()
    assert ig_token.obtener_token() == "nuevo"


def test_refresca_si_esta_por_vencer(monkeypatch):
    storage.guardar_ig_token({"token": "porvencer",
                              "expires_at": time.time() + 2 * 86400,
                              "refreshed_at": 0})
    monkeypatch.setattr(ig_token, "_llamar_refresh",
                        lambda t: {"access_token": "renovado", "expires_in": 5000000})
    ig_token._refrescar_si_necesario()
    assert ig_token.obtener_token() == "renovado"


def test_no_refresca_si_tiene_margen(monkeypatch):
    storage.guardar_ig_token({"token": "vigente", "expires_at": 10**12,
                              "refreshed_at": 0})

    def _boom(_):
        raise AssertionError("no debería refrescar cuando aún hay margen")

    monkeypatch.setattr(ig_token, "_llamar_refresh", _boom)
    ig_token._refrescar_si_necesario()
    assert ig_token.obtener_token() == "vigente"
