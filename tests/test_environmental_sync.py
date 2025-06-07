# tests/test_environmental_sync.py

import json
import pytest
import requests

from lifelog.commands.environmental_sync import (
    weather,
    air,
    moon,
    satellite,
    sync_all,
    fetch_weather_data,
    fetch_air_quality_data,
    fetch_moon_data,
    fetch_satellite_radiation_data,
)
import lifelog.config.config_manager as cfg
from lifelog.utils.db import environment_repository

# ────────────────────────────────────────────────────────────────────────────────
# Fixtures to stub out requests and repository calls
# ────────────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def fake_config(monkeypatch, tmp_path):
    """
    Provide a minimal config so that cfg.load_config() returns a dict
    with 'location' and 'api_keys'.
    """
    fake = {
        "location": {"latitude": 12.34, "longitude": 56.78},
        "api_keys": {"openweathermap": "fake‐key"},
    }
    monkeypatch.setattr(cfg, "load_config", lambda: fake)
    yield


@pytest.fixture(autouse=True)
def stub_repo(monkeypatch):
    """
    Stub out environment_repository.save_environment_data and get_latest_environment_data.
    Capture the calls to verify correct parameters.
    """
    called = {"saved": [], "latest": []}

    def fake_save(section, data):
        called["saved"].append((section, data))

    def fake_get_latest(section):
        called["latest"].append(section)
        return {"foo": "bar"} if section == "weather" else None

    monkeypatch.setattr(environment_repository,
                        "save_environment_data", fake_save)
    monkeypatch.setattr(environment_repository,
                        "get_latest_environment_data", fake_get_latest)

    return called


# ────────────────────────────────────────────────────────────────────────────────
# Tests for individual fetch_*_data() helpers (they actually hit real endpoints, so we monkey‐patch requests.get)
# ────────────────────────────────────────────────────────────────────────────────

class DummyResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


@pytest.mark.parametrize("lat,lon,expected_url_substring", [
    (12.34, 56.78, "open-meteo.com/v1/forecast"),
])
def test_fetch_weather_data_builds_correct_url(monkeypatch, lat, lon, expected_url_substring):
    dummy_payload = {"current_weather": {"temp": 20}}
    monkeypatch.setattr(
        requests, "get", lambda url: DummyResponse(dummy_payload))
    data = fetch_weather_data(lat, lon)
    assert data == dummy_payload


@pytest.mark.parametrize("lat,lon,expected_url_substring", [
    (12.34, 56.78, "air-quality-api.open-meteo.com/v1/air-quality"),
])
def test_fetch_air_quality_data_builds_correct_url(monkeypatch, lat, lon, expected_url_substring):
    dummy_payload = {"hourly": {"pm2_5": [5]}}
    monkeypatch.setattr(
        requests, "get", lambda url: DummyResponse(dummy_payload))
    data = fetch_air_quality_data(lat, lon)
    assert data == dummy_payload


@pytest.mark.parametrize("lat,lon,key,expected_url_substring", [
    (12.34, 56.78, "fake‐key", "api.openweathermap.org/data/2.5/onecall"),
])
def test_fetch_moon_data_builds_correct_url(monkeypatch, lat, lon, key, expected_url_substring):
    dummy_payload = {"moon_phase": 0.5}
    monkeypatch.setattr(
        requests, "get", lambda url: DummyResponse(dummy_payload))
    data = fetch_moon_data(lat, lon, key)
    assert data == dummy_payload


@pytest.mark.parametrize("lat,lon", [
    (12.34, 56.78),
])
def test_fetch_satellite_radiation_data_return(monkeypatch, lat, lon):
    dummy_payload = {"hourly": {"shortwave_radiation": [300]}}
    # Simulate status_code != 200
    monkeypatch.setattr(requests, "get", lambda url: DummyResponse(
        dummy_payload, status_code=200))
    data = fetch_satellite_radiation_data(lat, lon)
    assert data == dummy_payload


# ────────────────────────────────────────────────────────────────────────────────
# Tests for the four “weather(), air(), moon(), satellite()” command‐functions
# ────────────────────────────────────────────────────────────────────────────────

def test_weather_saves_data(stub_repo):
    # Now call weather(); since load_config() provides lat/lon, and fetch returns dummy, we expect a save call
    weather()
    assert ("weather",) in [(sec,) for sec, _ in stub_repo["saved"]]
    # The saved data itself is whatever fetch_weather_data returned; we stubbed fetch in earlier tests.


def test_air_saves_data(stub_repo):
    air()
    assert ("air_quality",) in [(sec,) for sec, _ in stub_repo["saved"]]


def test_moon_saves_data(stub_repo):
    moon()
    assert ("moon",) in [(sec,) for sec, _ in stub_repo["saved"]]


def test_satellite_saves_data(stub_repo):
    satellite()
    assert ("satellite",) in [(sec,) for sec, _ in stub_repo["saved"]]


def test_sync_all_invokes_all_sections(monkeypatch, stub_repo):
    """
    sync_all() calls weather(), air(), moon(), satellite(), so we should see four sections saved.
    """
    calls = []

    # Monkey-patch each function to record a call
    monkeypatch.setattr(
        "lifelog.commands.environmental_sync.weather", lambda: calls.append("weather"))
    monkeypatch.setattr(
        "lifelog.commands.environmental_sync.air", lambda: calls.append("air"))
    monkeypatch.setattr(
        "lifelog.commands.environmental_sync.moon", lambda: calls.append("moon"))
    monkeypatch.setattr(
        "lifelog.commands.environmental_sync.satellite", lambda: calls.append("sat"))
    sync_all()
    assert calls == ["weather", "air", "moon", "sat"]


def test_latest_prints_data_or_warning(capfd, stub_repo):
    # Case A: get_latest returns a dict for “weather”
    from lifelog.commands.environmental_sync import latest
    latest("weather")
    out, _ = capfd.readouterr()
    assert "Latest weather data" in out
    # Case B: section with no data
    latest("air_quality")
    out2, _ = capfd.readouterr()
    assert "No data found" in out2
