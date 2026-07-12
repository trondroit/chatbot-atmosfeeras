import config
from storage import FileStorage


def test_historial_se_recorta_al_maximo(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HISTORIAL_MAX", 4)
    s = FileStorage(str(tmp_path / "estado.json"))
    for i in range(10):
        s.agregar_mensaje("555", "user", f"mensaje {i}")
    historial = s.historial("555")
    assert len(historial) == 4
    assert historial[-1]["content"] == "mensaje 9"


def test_historial_sobrevive_reinicio(tmp_path):
    ruta = str(tmp_path / "estado.json")
    s1 = FileStorage(ruta)
    s1.agregar_mensaje("555", "user", "hola")
    s1.pausar("777")

    s2 = FileStorage(ruta)  # simula un reinicio del proceso
    assert s2.historial("555") == [{"role": "user", "content": "hola"}]
    assert s2.esta_pausado("777")
    assert not s2.esta_pausado("555")


def test_ya_procesado(tmp_path):
    s = FileStorage(str(tmp_path / "estado.json"))
    assert s.ya_procesado("meta:wamid.x") is False
    assert s.ya_procesado("meta:wamid.x") is True
    assert s.ya_procesado("meta:wamid.y") is False


def test_pausar_y_reanudar(tmp_path):
    s = FileStorage(str(tmp_path / "estado.json"))
    s.pausar("555")
    assert s.esta_pausado("555")
    s.reanudar("555")
    assert not s.esta_pausado("555")
