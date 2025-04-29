import json
import subprocess
import smtplib
from email.mime.text import MIMEText
import time
from datetime import datetime
import os

# TODO: Move the config into the config.toml and use the config manager to load it.
# Configuration
TIMER_FILE = '/home/pi/pending_timers.json'
EMAIL_ADDRESS = 'your_raspberry_pi_email@gmail.com'  # Replace with your Raspberry Pi's Gmail address
EMAIL_SUBJECT = 'New Timer'
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587
SMTP_USERNAME = 'your_raspberry_pi_email@gmail.com'  # Replace with your Raspberry Pi's Gmail address
SMTP_PASSWORD = 'your_gmail_app_password'  # Use an App Password for Gmail

def check_internet_connectivity(host='8.8.8.8'):
    """Checks if the Raspberry Pi can reach the internet."""
    try:
        result = subprocess.run(['ping', '-c', '1', '-W', '2', host], capture_output=True, text=True, check=True)
        print(f"Ping to {host} successful.")
        return True
    except subprocess.CalledProcessError:
        print(f"Ping to {host} failed.")
        return False
    except FileNotFoundError:
        print("Error: 'ping' command not found.")
        return False

def load_pending_timers():
    """Loads pending timers from the JSON file."""
    if os.path.exists(TIMER_FILE):
        with open(TIMER_FILE, 'r') as f:
            try:
                timers = json.load(f)
                print(f"Loaded pending timers: {timers}")
                return timers
            except json.JSONDecodeError:
                print("Error decoding JSON from timer file. Assuming empty.")
                return []
    else:
        print("Timer file not found. Assuming empty.")
        return []

def save_pending_timers(timers):
    """Saves the list of pending timers to the JSON file."""
    with open(TIMER_FILE, 'w') as f:
        json.dump(timers, f, indent=4)
    print(f"Saved pending timers: {timers}")

def send_timer_email(timer_data):
    """Sends an email containing the timer details."""
    try:
        body = json.dumps(timer_data)  # Send the timer data as the email body
        msg = MIMEText(body)
        msg['Subject'] = EMAIL_SUBJECT
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = 'your_iphone_email@example.com'  # Replace with the email address your iPhone automation monitors

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()  # Use TLS encryption
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.sendmail(EMAIL_ADDRESS, ['your_iphone_email@example.com'], msg.as_string())
        print(f"Successfully sent email for timer: {timer_data}")
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

def main():
    if check_internet_connectivity():
        pending_timers = load_pending_timers()
        timers_sent = []
        for timer in pending_timers:
            if send_timer_email(timer):
                timers_sent.append(timer)

        # Remove the sent timers from the pending list
        updated_timers = [timer for timer in pending_timers if timer not in timers_sent]
        save_pending_timers(updated_timers)
    else:
        print("No internet connectivity. Cannot send timer emails.")

if __name__ == "__main__":
    main()