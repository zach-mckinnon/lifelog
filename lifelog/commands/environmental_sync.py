
from lifelog.commands.utils.environmental import (
    fetch_weather_data,
    fetch_air_quality_data,
    fetch_moon_data,
    fetch_satellite_radiation_data,
)
import lifelog.config.config_manager as cf
from pathlib import Path
import json
from rich import print
import typer

app = typer.Typer(help="Environment data sync utilities.")

DATA_DIR = Path.home() / ".lifelog"
ENV_DATA_FILE = DATA_DIR / "environment.json"

crcfg = cf.load_cron_config()
cfg = cf.load_config()

def save_env_data(section, data):
    if not ENV_DATA_FILE.exists():
        ENV_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        json.dump({}, open(ENV_DATA_FILE, "w"))

    with open(ENV_DATA_FILE, "r") as f:
        existing = json.load(f)

    existing[section] = data

    with open(ENV_DATA_FILE, "w") as f:
        json.dump(existing, f, indent=2)

    print(f"[green]✅ Saved {section} data to environment.json[/green]")

def weather():
    location = crcfg.get("location", {})
    lat = location.get("latitude")
    lon = location.get("longitude")
    if not lat or not lon:
        print("[red]❌ Latitude/Longitude not set in config.[/red]")
        return
    data = fetch_weather_data(lat, lon)
    save_env_data("weather", data)

def air():
    location = crcfg.get("location", {})
    lat = location.get("latitude")
    lon = location.get("longitude")
    if not lat or not lon:
        print("[red]❌ Latitude/Longitude not set in config.[/red]")
        return
    data = fetch_air_quality_data(lat, lon)
    save_env_data("air_quality", data)

def moon():
    location = crcfg.get("location", {})
    lat = location.get("latitude")
    lon = location.get("longitude")
    key = crcfg.get("api_keys", {}).get("openweathermap")
    if not key:
        print("[red]❌ OpenWeatherMap API key missing in config.[/red]")
        return
    data = fetch_moon_data(lat, lon, key)
    save_env_data("moon", data)

def satellite():
    location = crcfg.get("location", {})
    lat = location.get("latitude")
    lon = location.get("longitude")
    if not lat or not lon:
        print("[red]❌ Latitude/Longitude not set in config.[/red]")
        return
    data = fetch_satellite_radiation_data(lat, lon)
    save_env_data("satellite_radiation", data)
