from worker.main import target_url


def test_defaults_to_demo_app(monkeypatch):
    monkeypatch.delenv("DEMO_URL", raising=False)
    assert target_url() == "http://localhost:5173"


def test_reads_env(monkeypatch):
    monkeypatch.setenv("DEMO_URL", "http://localhost:9999")
    assert target_url() == "http://localhost:9999"
