import config
import messenger_api


def test_url_y_token_messenger():
    url, token = messenger_api._url_y_token("msgr")
    assert "graph.facebook.com" in url
    assert token == config.PAGE_ACCESS_TOKEN


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
