# Lifelog CLI – Development Notes and Roadmap

## ✅ What’s Implemented

### 🔢 Metrics

- Custom metric types: `int`, `float`, `bool`, `str`
- Range validation (min/max)
- Log individual metrics with optional notes and tags
- View trends with terminal-friendly charts using `termplotlib`

### ⏱ Time Tracking

- Start/stop commands per category
- Tracks category, start time, end time, duration
- View time totals by day/week/month

### 🔁 Habits

- Define habits with optional description
- Mark them as "done" anytime
- Track habit completions
- Summary of completions by day/week/month

### 📊 Reporting

- `summary metric` shows trend chart per metric
- `summary time` shows time spent by category
- `summary habits` shows how often each habit was done
- ✅ `summary daily` gives a complete view of today's:
  - Metric averages
  - Time spent
  - Habit completions

## 🔜 Planned Features

### 🧠 Form Modules

- `llog form mental`, `form physical`, `form sleep`
- Prompt user for multiple metrics in one session
- Ideal for morning/evening check-ins

### 📋 Custom Task Tracker

- Create, list, and complete tasks from CLI
- Track time spent per task like Timewarrior
- Categories, tags, priorities, deadlines
- Daily and weekly reports for productivity

### 📥 External Context Data

- Fetch and store daily weather, light, or noise conditions
- Add these to logs for correlation with mood, sleep, etc.

### 🔁 Habit Streaks

- Track streaks per habit
- Optionally reset daily/weekly
- Display longest streaks

### 📤 Exporting & Syncing

- Export logs and summaries to JSON or CSV
- Future integration with simple web dashboard or synced journal

## 💡 Additional Cool Ideas

- 📅 Cron-based summaries (auto-run `summary daily` to file)
- 🧠 Correlation viewer (compare mood vs sleep vs tasks)
- 🎯 Goals module (link habits/tasks to longer-term goals)
- 🔔 Notification support ("Don't forget to log mood!")
- 🧩 Plugin system (allow user scripts per form/task/etc.)

## 🧠 Vision

Lifelog is a **minimal, neurodivergent-friendly CLI tool** to help:

- Track _all dimensions_ of your life
- Reflect on what helps/hurts your functioning
- Stay accountable in a lightweight, structured, and personalized way

Building a system for true self-awareness, not just productivity.
