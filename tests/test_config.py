from scripts.config import DEFAULT_MODEL, get_config


def test_config_reads_env(monkeypatch):
    get_config.cache_clear()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
    monkeypatch.setenv("GOOGLE_SHEET_ID", "sheet")
    monkeypatch.setenv("VC_ACTIONS_TEST_MODE", "true")
    cfg = get_config()
    assert cfg.anthropic_api_key == "key"
    assert cfg.google_sheet_id == "sheet"
    assert cfg.test_mode is True
    assert cfg.dry_run is False
    assert cfg.anthropic_model == DEFAULT_MODEL
    get_config.cache_clear()


def test_config_defaults_when_unset(monkeypatch):
    get_config.cache_clear()
    for var in [
        "ANTHROPIC_API_KEY",
        "GOOGLE_SHEET_ID",
        "VC_ACTIONS_TEST_MODE",
        "VC_ACTIONS_DRY_RUN",
        "ANTHROPIC_MODEL",
    ]:
        monkeypatch.delenv(var, raising=False)
    cfg = get_config()
    assert cfg.anthropic_api_key == ""
    assert cfg.test_mode is False
    assert cfg.anthropic_model == DEFAULT_MODEL
    get_config.cache_clear()
