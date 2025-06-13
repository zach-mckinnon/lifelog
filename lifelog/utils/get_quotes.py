# # lifelog/commands/yutils/get_quotes.py
'''
Lifelog Report Generation Module
This module provides functionality to generate various reports based on the user's data.
It includes features for generating daily, weekly, and monthly reports, as well as custom date range reports.
The module uses JSON files for data storage and integrates with a cron job system for scheduling report generation.
'''

from datetime import datetime
import json
import random
from typing import Dict, List, Optional
import requests
import lifelog.config.config_manager as cf

# feedback.py
from datetime import datetime
import json
import sqlite3
from lifelog.utils.db import database_manager
from lifelog.utils.db.db_helper import get_connection


def load_feedback_sayings():
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT context, sayings FROM feedback_sayings")
        rows = cur.fetchall()
    return {r['context']: json.loads(r['sayings']) for r in rows}


_sayings_cache: Optional[Dict[str, List[str]]] = None


def get_feedback_saying(context: str, *, fallback: str = "encouragement") -> str:
    """
    Return a random saying for the given *context*.
    • Loads from DB once, then serves from memory.
    • Falls back to the *fallback* context, then to a generic phrase.
    """
    global _sayings_cache
    if _sayings_cache is None:
        try:
            _sayings_cache = load_feedback_sayings()
        except Exception:
            _sayings_cache = default_feedback_sayings()

    pool = _sayings_cache.get(context) or _sayings_cache.get(fallback)
    if not pool:
        return "Keep going!"

    return random.choice(pool)


def save_feedback_sayings(sayings: dict):
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            for context, saying_list in sayings.items():
                cur.execute("""
                    INSERT OR REPLACE INTO feedback_sayings (context, sayings)
                    VALUES (?, ?)
                """, (context, json.dumps(saying_list)))
    except sqlite3.Error as e:
        print(f"Database error saving feedback: {e}")


def save_motivation_quote(date: str, quote: str):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO daily_quotes (date, quote)
            VALUES (?, ?)
        """, (date, quote))


def get_motivational_quote(date: str = None):
    date = date or str(datetime.now().date())
    with get_connection() as conn:
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


def default_feedback_sayings():
    """Returns the default positive feedback sayings dictionary."""
    return {
        "task_added": [
            "Got it!",
            "New task added!",
            "Another small step forward! 🌱",
            "Task successfully added!",
            "Added to your journey!",
            "Task noted and ready!",
            "New goal registered!",
            "Task added to your path!",
            "One more step toward success!",
            "Task added. You're planning well!",
            "Added to your accomplishments list!",
            "New task in the system!",
            "Task recorded. Ready when you are!",
            "Added! Your roadmap is growing!",
            "Task noted. You're being proactive!"
        ],
        "task_completed": [
            "Well done!",
            "Task completed successfully.",
            "Victory is yours! 🏆",
            "Great job completing that task!",
            "Nice work on finishing that!",
            "Task complete! Keep up the good work!",
            "Another task down, well done!",
            "Excellent progress today!",
            "You're on a roll!",
            "Task finished - you're making great strides!",
            "Fantastic job staying on track!",
            "Well done on completing your task!",
            "Progress noted! Keep moving forward!",
            "Awesome job on finishing that task!",
            "Task complete! You're making progress!"
        ],
        "time_tracking_started": [
            "You've started strong!",
            "Focus time: engaged!",
            "Every journey begins with a single step.",
            "Time tracking activated!",
            "Clock is running - you've got this!",
            "Focus mode: ON!",
            "Time tracking started. Make it count!",
            "Your productive time begins now!",
            "Timer started. Your focus matters!",
            "Time tracking engaged. Ready, set, go!",
            "Clock is ticking on your success!",
            "Time tracking initiated. Flow state ahead!",
            "Your focused session has begun!",
            "Tracking started. Your time is valuable!",
            "Focus time activated. You're in control!"
        ],
        "time_tracking_stopped": [
            "Nice work tracking your time!",
            "Progress recorded! 📜",
            "You made your effort visible today.",
            "Time successfully logged. Way to stay organized!",
            "Time entry recorded. You're crushing it!",
            "Time logged successfully. You're doing great!",
            "Time tracking complete. Productivity win!",
            "Successfully logged! You're on top of things!",
            "Well tracked! Your consistency is impressive!",
            "Time logged. You're building great habits!",
            "Time entry successful. You're staying accountable!",
            "Time tracked. You're mastering your schedule!",
            "Perfectly logged! Keep that momentum going!",
            "Time successfully recorded. You're doing amazing!",
            "Time logged! Your organization skills are impressive!"
        ],
        "tracker_logged": [
            "Tracker logged! 🔥",
            "Consistency wins!",
            "Small steps, big change!",
            "Tracker updated!",
            "You're building something great!",
            "Your streak continues!",
            "Another brick in your foundation!",
            "Tracker logged. You're forming excellence!",
            "Consistency noted. This is how you grow!",
            "Tracker recorded. Your future self thanks you!",
            "That's another check for your trackers!",
            "Tracker maintained. You're becoming unstoppable!",
            "Daily practice recorded. Progress in action!",
            "Tracker logged successfully. Compound effect in motion!",
            "Consistency is your superpower! Tracker logged."
        ],
        "first_command_of_day": [
            "Welcome back, adventurer! 🧙‍♂️",
            "Ready to shape your day?",
            "New day, new opportunities! 🌅",
            "Good to see you today!",
            "Ready for a productive day?",
            "Today's page is blank - ready to write it?",
            "Welcome to a fresh start!",
            "Hello! Ready to tackle today's challenges?",
            "A new day of possibilities begins!",
            "Welcome back! Today is full of potential.",
            "Good to have you back! Ready to begin?",
            "Another day, another chance to excel!",
            "Welcome! Today is yours to conquer.",
            "Hello again! Let's make today count.",
            "Fresh day, fresh energy! Ready to begin?"
        ],
        "encouragement": [
            "You're doing your best, and that's enough.",
            "It's okay to go slow — you're still moving.",
            "Proud of you for showing up.",
            "Your progress is a journey, not a race.",
            "Every small step matters in the long run.",
            "You're building something meaningful.",
            "Your consistency is your strength.",
            "Remember why you started. You've got this!",
            "Progress over perfection. Always.",
            "You're doing better than you think.",
            "Trust your process. Growth takes time.",
            "Your efforts today shape your tomorrow.",
            "Showing up is half the battle. Well done!",
            "Small consistent steps lead to big changes.",
            "Your dedication will pay off. Keep going!"
        ]
    }
