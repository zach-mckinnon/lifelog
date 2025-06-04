# lifelog.utils/environmental.py
'''
Lifelog Environmental Data Fetching Module
This module provides functionality to fetch various environmental data such as weather, air quality, moon phases, and solar radiation.
It uses external APIs to retrieve the data and returns it in a structured format.
'''

import requests


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
