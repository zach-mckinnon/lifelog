# # lifelog/commands/report.py
'''
Lifelog Report Generation Module
This module provides functionality to generate various reports based on the user's data.
It includes features for generating daily, weekly, and monthly reports, as well as custom date range reports.
The module uses JSON files for data storage and integrates with a cron job system for scheduling report generation.
'''


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


@app.command()
def sync_all():
    """
    Fetch all environmental data (weather, air, moon, satellite).
    """
    weather()
    air()
    moon()
    satellite()
    print("[green]✅ Synced all environment data.[/green]")


def save_env_data(section, data):
    ENV_DATA_FILE = cf.get_env_data_file()
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
    cfg = cf.load_config()
    location = cfg.get("location", {})
    lat = location.get("latitude")
    lon = location.get("longitude")
    if not lat or not lon:
        print("[red]❌ Latitude/Longitude not set in config.[/red]")
        return
    data = fetch_weather_data(lat, lon)
    save_env_data("weather", data)

def air():
    cfg = cf.load_config()
    location = cfg.get("location", {})
    lat = location.get("latitude")
    lon = location.get("longitude")
    if not lat or not lon:
        print("[red]❌ Latitude/Longitude not set in config.[/red]")
        return
    data = fetch_air_quality_data(lat, lon)
    save_env_data("air_quality", data)

def moon():
    cfg = cf.load_config()
    location = cfg.get("location", {})
    lat = location.get("latitude")
    lon = location.get("longitude")
    key = cfg.get("api_keys", {}).get("openweathermap")
    if not key:
        print("[red]❌ OpenWeatherMap API key missing in config.[/red]")
        return
    data = fetch_moon_data(lat, lon, key)
    save_env_data("moon", data)

def satellite():
    cfg = cf.load_config()
    location = cfg.get("location", {})
    lat = location.get("latitude")
    lon = location.get("longitude")
    if not lat or not lon:
        print("[red]❌ Latitude/Longitude not set in config.[/red]")
        return
    data = fetch_satellite_radiation_data(lat, lon)
    save_env_data("satellite", data)
