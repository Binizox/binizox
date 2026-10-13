import sys


def test_import_binizox_does_not_eagerly_import_knowledge(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delitem(sys.modules, "binizox", raising=False)
    monkeypatch.delitem(sys.modules, "binizox.knowledge", raising=False)

    import binizox

    assert binizox.get_version() == binizox.__version__
    assert "binizox.knowledge" not in sys.modules
