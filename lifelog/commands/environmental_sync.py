# lifelog/commands/environmental_sync.py

import json
from lifelog.commands.utils.environmental import (
    fetch_weather_data,
    fetch_air_quality_data,
    fetch_moon_data,
    fetch_satellite_radiation_data,
)
from lifelog.commands.utils.db import environment_repository
import lifelog.config.config_manager as cf
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


def weather():
    cfg = cf.load_config()
    location = cfg.get("location", {})
    lat = location.get("latitude")
    lon = location.get("longitude")
    if not lat or not lon:
        print("[red]❌ Latitude/Longitude not set in config.[/red]")
        return
    data = fetch_weather_data(lat, lon)
    environment_repository.save_environment_data("weather", data)
    print(f"[green]✅ Weather data saved.[/green]")


def air():
    cfg = cf.load_config()
    location = cfg.get("location", {})
    lat = location.get("latitude")
    lon = location.get("longitude")
    if not lat or not lon:
        print("[red]❌ Latitude/Longitude not set in config.[/red]")
        return
    data = fetch_air_quality_data(lat, lon)
    environment_repository.save_environment_data("air_quality", data)
    print(f"[green]✅ Air quality data saved.[/green]")


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
    environment_repository.save_environment_data("moon", data)
    print(f"[green]✅ Moon data saved.[/green]")


def satellite():
    cfg = cf.load_config()
    location = cfg.get("location", {})
    lat = location.get("latitude")
    lon = location.get("longitude")
    if not lat or not lon:
        print("[red]❌ Latitude/Longitude not set in config.[/red]")
        return
    data = fetch_satellite_radiation_data(lat, lon)
    environment_repository.save_environment_data("satellite", data)
    print(f"[green]✅ Satellite data saved.[/green]")


@app.command("latest")
def latest(section: str = typer.Argument(..., help="Section (weather, air_quality, moon, satellite)")):
    """
    Show the latest fetched environment data for a section.
    """
    try:
        data = environment_repository.get_latest_environment_data(section)
        if data:
            print(
                f"[green]Latest {section} data:[/green]\n{json.dumps(data, indent=2)}")
        else:
            print(f"[yellow]No data found for {section}.[/yellow]")
    except Exception as e:
        print(f"[red]❌ Failed to fetch latest data: {e}[/red]")
