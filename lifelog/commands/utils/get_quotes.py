from datetime import datetime
import json
from pathlib import Path
import requests

DAILY_QUOTE_FILE = Path.home() / ".lifelog" / "daily_zen_quote.json"

def fetch_daily_zen_quote(api_url="https://zenquotes.io/api/today"):
    """Fetches the quote of the day from ZenQuotes."""
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
    
def get_daily_quote():
    """Retrieves the daily ZenQuote, fetching if it's a new day."""
    today = datetime.now().date()
    stored_quote_data = {}
    if DAILY_QUOTE_FILE.exists():
        try:
            with open(DAILY_QUOTE_FILE, "r") as f:
                stored_quote_data = json.load(f)
        except json.JSONDecodeError:
            print("[yellow]⚠️ Warning[/yellow]: Could not decode stored daily quote.")

    if stored_quote_data.get("date") == str(today) and stored_quote_data.get("quote"):
        return stored_quote_data["quote"]
    else:
        new_quote = fetch_daily_zen_quote()
        if new_quote:
            save_daily_quote({"date": str(today), "quote": new_quote})
            return new_quote
        return None

def save_daily_quote(quote_data):
    """Saves the daily ZenQuote to a JSON file."""
    DAILY_QUOTE_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(DAILY_QUOTE_FILE, "w") as f:
            json.dump(quote_data, f, indent=2)
    except IOError:
        print(f"[yellow]⚠️ Warning[/yellow]: Could not save daily quote to {DAILY_QUOTE_FILE}")