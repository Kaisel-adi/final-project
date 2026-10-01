import os
import threading
from wsgi import start_keep_alive, _ping_loop, app


def test_wsgi_app_initialization():
    assert app is not None
    assert app.name == "app"


def test_start_keep_alive_no_url(monkeypatch):
    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
    monkeypatch.delenv("KEEP_ALIVE_URL", raising=False)
    monkeypatch.delenv("TESTING", raising=False)
    res = start_keep_alive()
    assert res is None


def test_start_keep_alive_disabled_in_testing(monkeypatch):
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://garuda-app.onrender.com")
    monkeypatch.setenv("TESTING", "True")
    res = start_keep_alive()
    assert res is None


def test_start_keep_alive_spawns_daemon_thread(monkeypatch):
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://garuda-app.onrender.com")
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.setenv("DISABLE_KEEP_ALIVE", "false")

    spawned = {}

    def mock_thread_start(self):
        spawned["target"] = self._target
        spawned["args"] = self._args
        spawned["daemon"] = self.daemon
        spawned["name"] = self.name

    monkeypatch.setattr(threading.Thread, "start", mock_thread_start)

    thread = start_keep_alive()
    assert thread is not None
    assert spawned["daemon"] is True
    assert spawned["target"] == _ping_loop
    assert spawned["args"][0] == "https://garuda-app.onrender.com"
