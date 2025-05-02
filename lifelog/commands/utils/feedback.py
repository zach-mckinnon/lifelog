# # lifelog/commands/utils/feedback.py
'''
Lifelog Feedback Sayings Module
This module provides functionality to load and retrieve feedback sayings for various contexts.
It uses a JSON file to store the sayings and allows for easy retrieval of a random saying for a given context.
It is designed to be used in conjunction with the Lifelog CLI to provide user feedback and encouragement.
'''

import json
from pathlib import Path
import random
import lifelog.config.config_manager as cf


def load_feedback_sayings():
    """Loads the feedback sayings from the JSON file."""
    FEEDBACK_FILE = cf.get_feedback_file()
    if FEEDBACK_FILE.exists():
        try:
            with open(FEEDBACK_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("[yellow]⚠️ Warning[/yellow]: Could not decode feedback sayings.")
    return {}


def get_feedback_saying(context):
    """Retrieves a random feedback saying for a given context."""
    sayings = load_feedback_sayings()
    if context in sayings and sayings[context]:
        return random.choice(sayings[context])
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
