# lifelog/commands/environmental_sync.py

import requests
import json
from lifelog.utils.db import environment_repository
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


def fetch_weather_data(lat, lon):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
    response = requests.get(url)
    return response.json()


def fetch_air_quality_data(lat, lon):
    url = f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}&longitude={lon}&hourly=pm10,pm2_5,carbon_monoxide,nitrogen_dioxide,ozone"
    response = requests.get(url)
    return response.json()


def fetch_moon_data(lat, lon, api_key):
    url = f"https://api.openweathermap.org/data/2.5/onecall?lat={lat}&lon={lon}&exclude=hourly,daily,minutely,alerts&appid={api_key}"
    response = requests.get(url)
    return response.json()


def fetch_satellite_radiation_data(lat, lon):
    url = (
        f"https://api.open-meteo.com/v1/satellite?"
        f"latitude={lat}&longitude={lon}&hourly=shortwave_radiation,direct_radiation,"
        f"diffuse_radiation,direct_normal_irradiance,global_tilted_irradiance,"
        f"terrestrial_radiation&timezone=auto"
    )
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error fetching data: {response.status_code}")
        return None
