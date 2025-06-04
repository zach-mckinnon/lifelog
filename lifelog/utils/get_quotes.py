# # lifelog/commands/yutils/get_quotes.py
'''
Lifelog Report Generation Module
This module provides functionality to generate various reports based on the user's data.
It includes features for generating daily, weekly, and monthly reports, as well as custom date range reports.
The module uses JSON files for data storage and integrates with a cron job system for scheduling report generation.
'''

from datetime import datetime
import json
import requests
import lifelog.config.config_manager as cf

# feedback.py
from datetime import datetime
import json
import sqlite3
from lifelog.utils.db import database_manager


def load_feedback_sayings():
    conn = database_manager.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT context, sayings FROM feedback_sayings")
    conn.close()
    return {row['context']: json.loads(row['sayings']) for row in cur.fetchall()}


def save_feedback_sayings(sayings: dict):
    try:
        conn = database_manager.get_connection()
        cur = conn.cursor()
        for context, saying_list in sayings.items():
            cur.execute("""
                INSERT OR REPLACE INTO feedback_sayings (context, sayings)
                VALUES (?, ?)
            """, (context, json.dumps(saying_list)))
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database error saving feedback: {e}")
    finally:
        conn.close()


def save_motivation_quote(date: str, quote: str):
    conn = database_manager.get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO daily_quotes (date, quote)
        VALUES (?, ?)
    """, (date, quote))
    conn.commit()
    conn.close()


def get_motivational_quote(date: str = None):
    date = date or str(datetime.now().date())
    conn = database_manager.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT quote FROM daily_quotes WHERE date = ?", (date,))
    row = cur.fetchone()

    # If no quote in DB, fetch a new one
    if not row:
        new_quote = fetch_daily_zen_quote()
        if new_quote:
            save_motivation_quote(date, new_quote)
            return new_quote
        return None

    return row[0]


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
    api_url = "https://zenquotes.io/api/random"
    try:
        response = requests.get(api_url)
        response.raise_for_status()
        data = response.json()
        if data and isinstance(data, list) and len(data) > 0:
            return data[0]["q"] + " — " + data[0]["a"]
        else:
            print(
                "[yellow]⚠️ Warning[/yellow]: Could not parse quote from ZenQuotes API.")
            return None
    except requests.exceptions.RequestException as e:
        print(
            f"[yellow]⚠️ Warning[/yellow]: Could not fetch quote from ZenQuotes API: {e}")
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
                print(
                    "[yellow]⚠️ Warning[/yellow]: Could not decode stored daily quote.")

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
        print(
            f"[yellow]⚠️ Warning[/yellow]: Could not save daily quote to {DAILY_QUOTE_FILE}")
