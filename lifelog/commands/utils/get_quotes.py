# # lifelog/commands/yutils/get_quotes.py
'''
Lifelog Report Generation Module
This module provides functionality to generate various reports based on the user's data.
It includes features for generating daily, weekly, and monthly reports, as well as custom date range reports.
The module uses JSON files for data storage and integrates with a cron job system for scheduling report generation.
'''

from datetime import datetime
import json
from pathlib import Path
import requests
import lifelog.config.config_manager as cf

def fetch_on_this_day():
    today = datetime.now()
    url = f"https://today.zenquotes.io/api/{today.month}/{today.day}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        return data.get("data", {})
    except requests.RequestException as e:
        print(f"Warning: Could not fetch 'On This Day' data: {e}")
        return {}

def fetch_daily_zen_quote():
    """Fetches the quote of the day from ZenQuotes."""
    api_url="https://zenquotes.io/api/random"
    try:
        response = requests.get(api_url)
        response.raise_for_status()
        data = response.json()
        if data and isinstance(data, list) and len(data) > 0:
            return data[0]["q"] + " — " + data[0]["a"]
        else:
            print("[yellow]⚠️ Warning[/yellow]: Could not parse quote from ZenQuotes API.")
            return None
    except requests.exceptions.RequestException as e:
        print(f"[yellow]⚠️ Warning[/yellow]: Could not fetch quote from ZenQuotes API: {e}")
        return None
    
def get_motivational_quote():
    """
    Retrieves a daily quote.
    - Fetches fresh quote from API if possible.
    - Falls back to last saved quote if API is unreachable.
    """
    today = datetime.now().date()
    DAILY_QUOTE_FILE = cf.get_motivational_quote_file()
    stored_quote_data = {}

    # Try to fetch a fresh quote first
    new_quote = fetch_daily_zen_quote()
    if new_quote:
        # Check if already saved
        if DAILY_QUOTE_FILE.exists():
            try:
                with open(DAILY_QUOTE_FILE, "r") as f:
                    stored_quote_data = json.load(f)
                if stored_quote_data.get("quote") == new_quote:
                    # Same quote, don't resave
                    return new_quote
            except json.JSONDecodeError:
                print("[yellow]⚠️ Warning[/yellow]: Could not decode stored daily quote.")

        # Save only if new or no existing quote
        save_motivation_quote({"date": str(today), "quote": new_quote})
        return new_quote

    # If fetching fails, try loading the stored one
    if DAILY_QUOTE_FILE.exists():
        try:
            with open(DAILY_QUOTE_FILE, "r") as f:
                stored_quote_data = json.load(f)
            if stored_quote_data.get("quote"):
                return stored_quote_data["quote"]
        except json.JSONDecodeError:
            print("[yellow]⚠️ Warning[/yellow]: Stored daily quote file is corrupt.")
    
    return None

def save_motivation_quote(quote_data):
    """Saves the daily ZenQuote to a JSON file."""
    DAILY_QUOTE_FILE = cf.get_motivational_quote_file()
    DAILY_QUOTE_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(DAILY_QUOTE_FILE, "w") as f:
            json.dump(quote_data, f, indent=2)
    except IOError:
        print(f"[yellow]⚠️ Warning[/yellow]: Could not save daily quote to {DAILY_QUOTE_FILE}")