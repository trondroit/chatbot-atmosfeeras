import pytest

import config
import messenger_api
import storage


@pytest.fixture(autouse=True)
def _backend_limpio(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "_backend",
                        storage.FileStorage(str(tmp_path / "estado.json")))


def test_url_y_token_messenger():
    url, token = messenger_api._url_y_token("msgr")
    assert "graph.facebook.com" in url
    assert token == config.PAGE_ACCESS_TOKEN


def test_url_messenger_usa_page_id_si_esta_definido(monkeypatch):
    monkeypatch.setattr(config, "PAGE_ID", "210051202192476")
    url, _ = messenger_api._url_y_token("msgr")
    assert url.endswith("/210051202192476/messages")


def test_url_messenger_usa_me_sin_page_id(monkeypatch):
    monkeypatch.setattr(config, "PAGE_ID", None)
    url, _ = messenger_api._url_y_token("msgr")
    assert url.endswith("/me/messages")


def test_url_y_token_instagram_con_token_propio(monkeypatch):
    monkeypatch.setattr(config, "IG_ACCESS_TOKEN", "ig-token-xyz")
    url, token = messenger_api._url_y_token("ig")
    assert "graph.instagram.com" in url
    assert token == "ig-token-xyz"


def test_url_y_token_instagram_sin_token_cae_a_pagina(monkeypatch):
    monkeypatch.setattr(config, "IG_ACCESS_TOKEN", None)
    url, token = messenger_api._url_y_token("ig")
    assert "graph.facebook.com" in url
    assert token == config.PAGE_ACCESS_TOKEN
