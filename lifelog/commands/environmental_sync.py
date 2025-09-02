# lifelog/commands/environmental_sync.py

from datetime import date
import requests
import json
from lifelog.utils.db import environment_repository
import lifelog.config.config_manager as cf
from rich import print
import typer

app = typer.Typer(help="Environment data sync utilities.")

WEATHERCODE_MAP = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Drizzle: light",
    53: "Drizzle: moderate",
    55: "Drizzle: dense",
    56: "Freezing drizzle: light",
    57: "Freezing drizzle: dense",
    61: "Rain: slight",
    63: "Rain: moderate",
    65: "Rain: heavy",
    66: "Freezing rain: light",
    67: "Freezing rain: heavy",
    71: "Snow fall: slight",
    73: "Snow fall: moderate",
    75: "Snow fall: heavy",
    77: "Snow grains",
    80: "Rain showers: slight",
    81: "Rain showers: moderate",
    82: "Rain showers: violent",
    85: "Snow showers: slight",
    86: "Snow showers: heavy",
    95: "Thunderstorm: slight or moderate",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def fetch_today_forecast(lat, lon):
    """
    Fetch hourly forecast from Open-Meteo for today and return entries every 4 hours.
    Also save the raw hourly data into environment_data under source "weather_hourly".
    Returns list of dicts: {'time': 'YYYY-MM-DDThh:MM', 'temperature': float, 'precip_prob': int, 'description': str}
    """
    hourly_vars = "temperature_2m,weathercode,precipitation_probability"
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&hourly={hourly_vars}"
        f"&timezone=auto"
    )
    try:
        import os
        timeout = int(os.getenv('LIFELOG_NETWORK_TIMEOUT', '15'))
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        raise RuntimeError(f"Failed to fetch weather: {e}")

    try:
        environment_repository.save_environment_data("weather_full", data)
        hourly_data = data.get("hourly", {})
        environment_repository.save_environment_data(
            "weather_hourly", hourly_data)
    except Exception as save_err:
        print(f"[warn]Failed to save weather data: {save_err}")

    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    temps = hourly.get("temperature_2m", [])
    precip_probs = hourly.get("precipitation_probability", [])
    codes = hourly.get("weathercode", [])

    today_str = date.today().isoformat()
    results = []
    for idx, t_str in enumerate(times):
        if not t_str.startswith(today_str + "T"):
            continue
        try:
            hour = int(t_str[11:13])
        except Exception:
            continue
        if hour % 4 != 0:
            continue
        temp = temps[idx] if idx < len(temps) else None
        precip = precip_probs[idx] if idx < len(precip_probs) else None
        code = codes[idx] if idx < len(codes) else None
        desc = WEATHERCODE_MAP.get(
            code, f"Code {code}") if code is not None else "-"
        results.append({
            "time": t_str,
            "temperature": temp,
            "precip_prob": precip,
            "description": desc,
        })
    return results


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
    try:
        import os
        timeout = int(os.getenv('LIFELOG_NETWORK_TIMEOUT', '15'))
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to fetch weather data: {e}")


def fetch_air_quality_data(lat, lon):
    url = f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}&longitude={lon}&hourly=pm10,pm2_5,carbon_monoxide,nitrogen_dioxide,ozone"
    try:
        import os
        timeout = int(os.getenv('LIFELOG_NETWORK_TIMEOUT', '15'))
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to fetch air quality data: {e}")


def fetch_moon_data(lat, lon, api_key):
    url = f"https://api.openweathermap.org/data/2.5/onecall?lat={lat}&lon={lon}&exclude=hourly,daily,minutely,alerts&appid={api_key}"
    try:
        import os
        timeout = int(os.getenv('LIFELOG_NETWORK_TIMEOUT', '15'))
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to fetch moon data: {e}")


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
