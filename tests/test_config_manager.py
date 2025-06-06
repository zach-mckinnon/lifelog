# tests/test_config_manager.py

import os
import json
import toml
import pytest
import importlib
from pathlib import Path

import lifelog.config.config_manager as cfg


@pytest.fixture
def temp_config_file(tmp_path, monkeypatch):
    """
    Create a temporary config.toml file and monkey‐patch
    config_manager.BASE_DIR and USER_CONFIG so that load_config()
    uses a fresh file under tmp_path instead of ~/.lifelog/config.toml.
    """
    # 1) Point BASE_DIR to a temp directory
    temp_base = tmp_path / "config_dir"
    monkeypatch.setattr(cfg, "BASE_DIR", temp_base)

    # 2) The USER_CONFIG is BASE_DIR / "config.toml"
    temp_user_config = temp_base / "config.toml"
    monkeypatch.setattr(cfg, "USER_CONFIG", temp_user_config)

    # 3) Also override DEFAULT_CONFIG so load_config writes something minimal
    minimal = {
        "deployment": {"mode": "local", "server_url": "http://localhost:5000"},
        "category_importance": {"work": 1.2},
        "ai": {"enabled": True, "provider": "openai", "api_key": "encrypted_dummy"},
    }
    monkeypatch.setattr(cfg, "DEFAULT_CONFIG", toml.dumps(minimal))

    # 4) Reload module so constants take effect
    importlib.reload(cfg)

    yield temp_user_config

    # 5) Cleanup not needed—tmp_path is ephemeral


def test_load_config_creates_file(temp_config_file):
    # Before load_config, the file should not exist
    assert not temp_config_file.exists()

    # After load_config, file should be created
    conf = cfg.load_config()
    assert temp_config_file.exists()
    assert isinstance(conf, dict)

    # The minimal DEFAULT_CONFIG we set should be loaded
    assert conf["deployment"]["mode"] == "local"
    assert conf.get("category_importance", {}).get("work") == 1.2


def test_get_and_set_config_value(temp_config_file):
    # load initial config
    conf = cfg.load_config()
    # set a new value under [settings]
    cfg.set_config_value("settings", "default_importance", 5)

    # reload config (load_config will read from the same file)
    conf2 = cfg.load_config()
    assert conf2["settings"]["default_importance"] == 5

    # get_config_value should return the newly set value
    val = cfg.get_config_value("settings", "default_importance")
    assert val == 5

    # get a non-existent key→ default
    missing = cfg.get_config_value("settings", "nonexistent", default="xyz")
    assert missing == "xyz"


def test_get_deployment_mode_and_url_defaults(temp_config_file):
    # By default (from minimal DEFAULT_CONFIG), mode="local", server_url="http://localhost:5000"
    mode, url = cfg.get_deployment_mode_and_url()
    assert mode == "local"
    assert url == "http://localhost:5000"

    # If we modify the TOML directly:
    doc = cfg.load_config()
    doc["deployment"]["mode"] = "client"
    doc["deployment"]["server_url"] = "http://example.com:4000"
    cfg.save_config(doc)

    m2, u2 = cfg.get_deployment_mode_and_url()
    assert m2 == "client"
    assert u2 == "http://example.com:4000"


def test_is_host_server_and_mode_functions(temp_config_file):
    # By default, deployment.host_server is not set
    assert cfg.is_host_server() is False

    # Change host_server to True
    doc = cfg.load_config()
    doc.setdefault("deployment", {})["host_server"] = True
    cfg.save_config(doc)

    assert cfg.is_host_server() is True

    # get_deployment_mode should reflect the "mode" field
    doc["deployment"]["mode"] = "client"
    cfg.save_config(doc)
    assert cfg.get_deployment_mode() == "client"

    # get_server_url returns our saved URL
    doc["deployment"]["server_url"] = "https://foo.bar"
    cfg.save_config(doc)
    assert cfg.get_server_url() == "https://foo.bar"


def test_category_importance_functions(temp_config_file):
    # Default from minimal DEFAULT_CONFIG: {"work":1.2}
    ci = cfg.get_category_importance("work")
    assert ci == 1.2

    # Non-existent category → 1.0
    ci2 = cfg.get_category_importance("nonexistent")
    assert ci2 == 1.0

    # set_category_importance and get_all_category_importance
    cfg.set_category_importance("gym", 0.8)
    all_ci = cfg.get_all_category_importance()
    assert all_ci["gym"] == 0.8
    assert isinstance(all_ci, dict)

    # set_category_description and list_config_section for [categories]
    cfg.set_category_description("testcat", "Test Category")
    cats = cfg.list_config_section("categories")
    assert cats["testcat"] == "Test Category"
    # delete_category
    cfg.delete_category("testcat")
    cats2 = cfg.list_config_section("categories")
    assert "testcat" not in cats2


def test_get_alias_map_and_tracker_definition(temp_config_file):
    # DEFAULT_CONFIG did not define any aliases, so get_alias_map() is {}
    aliases = cfg.get_alias_map()
    assert isinstance(aliases, dict)
    assert aliases == {}

    # Add an alias and test again
    doc = cfg.load_config()
    doc.setdefault("aliases", {})["x"] = "example"
    cfg.save_config(doc)
    aliases2 = cfg.get_alias_map()
    assert aliases2["x"] == "example"

    # DEFAULT_CONFIG sets [tracker], style is empty sections for mood, water, etc.
    # get_tracker_definition("mood") may be {} or None depending on how DEFAULT_CONFIG was structured.
    td = cfg.get_tracker_definition("mood")
    # In our minimal DEFAULT_CONFIG we didn't set tracker entries, so it should be None
    assert td is None


@pytest.mark.parametrize("value,expected", [
    (None, 1.0),
    ("not_a_float", 1.0),
    (2.5, 2.5),
    ("3.7", 3.7)
])
def test_get_category_importance_coercion(tmp_path, monkeypatch, value, expected):
    # Use a custom config that has category_importance
    temp_base = tmp_path / "cfg"
    monkeypatch.setattr(cfg, "BASE_DIR", temp_base)
    monkeypatch.setattr(cfg, "USER_CONFIG", temp_base / "config.toml")
    # Build a config where category_importance: {foo: value}
    sample = {"category_importance": {"foo": value}}
    monkeypatch.setattr(cfg, "DEFAULT_CONFIG", toml.dumps(sample))
    importlib.reload(cfg)

    got = cfg.get_category_importance("foo")
    # If conversion fails, returns 1.0; else float(value)
    assert pytest.approx(got, rel=1e-6) == expected
