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

---

Lifelog CLI - Comprehensive Requirements and Development Guide
This guide outlines the core principles, data consistency standards, and functional requirements for the Lifelog CLI application. It aims to ensure a cohesive, user-friendly, and neurodivergent-friendly experience focused on self-awareness.

I. Core Principles
These overarching principles should guide all development decisions:

Minimal Friction: The tool should minimize the effort required for logging data. Interactions should be quick, intuitive, and avoid unnecessary complexity.
Burnout-Safe: The design should be forgiving and encourage consistent use without creating pressure or guilt. Missing data should be handled gracefully.
Neurodivergent-Friendly: The interface and language should be clear, direct, and avoid ambiguous or overwhelming elements. Customization and flexibility are key to accommodating diverse needs.
Focus on Self-Awareness: The primary goal is to facilitate reflection and understanding of personal patterns and well-being, not just productivity tracking.
Data as a Foundation for Insight: All logged data should be structured and timestamped to enable meaningful analysis and the discovery of correlations.
Extensibility and Personalization: The architecture should allow for future expansion and user-specific customizations (e.g., aliases, custom reports, plugins).
Transparency and Clarity: The system should clearly communicate its assumptions, data completeness, and any limitations in reporting.
Consistent User Experience: Commands, options, and reporting should follow predictable patterns across all modules.
II. Data Consistency Standards
Maintaining consistent data structures is crucial for effective reporting and analysis. The following standards should be adhered to across all modules:

Timestamping: Every logged event (metric entry, habit completion, time log, etc.) MUST include a precise timestamp in ISO 8601 format (YYYY-MM-DDTHH:MM:SS). This ensures accurate chronological ordering.
Unified Data Storage: While separate JSON files per module are acceptable for organization, the underlying structure of the data within these files should be consistent where applicable. Aim for a common base structure that includes timestamp as a primary key.
Standardized Fields: Where data points are conceptually similar across modules, use consistent field names (e.g., notes, tags, category, value, start_time, end_time, duration).
Data Typing: Enforce data types for values (e.g., int, float, bool, str) as defined in the Metrics module. Validation should occur at the point of data entry.
Metadata Consistency: Allow for optional notes (free-form text) and tags (categorization keywords) for most data entries. Ensure a consistent way to add and query this metadata.
Handling Missing Data: When data is incomplete or missing, avoid introducing placeholder values that could skew analysis. Reports should explicitly indicate data confidence based on completeness.
Configuration Management: User-defined settings (aliases, preferred metrics, report configurations) should be stored in a consistent format (e.g., TOML) and be easily accessible by all modules.
Error Handling: Implement robust error handling that provides clear and user-friendly messages when data entry or processing fails. Avoid technical jargon.
III. Functional Module Requirements and Guidelines
This section details the requirements and guidelines for each module, ensuring consistency and adherence to the core principles.

1. Metrics
   Purpose: Track quantifiable self-reported data.
   Consistency:
   Must store timestamp, value (with appropriate type), optional notes, and optional tags.
   Adhere to defined metric types (int, float, bool, str) and range validation rules.
   Support user-defined aliases for metric names.
   Guidelines:
   Prioritize a concise logging syntax (e.g., llog mood 6 --notes "foggy").
   Implement a "quick log" functionality (llog quick) to prompt for commonly tracked metrics.
2. Habits
   Purpose: Track the completion of recurring actions.
   Consistency:
   Must store timestamp of completion, the habit name, and optionally whether a target was met.
   Future: Store habit definitions with optional descriptions, targets (quantity/frequency), and reset schedules.
   Guidelines:
   Simple "done" command (llog habit done <habit>).
   Support for defining new habits on the fly.
   Build towards streak tracking with consistent logic for calculating and displaying streaks.
3. Time
   Purpose: Log time spent in different categories.
   Consistency:
   Must store category, start_time (timestamp), end_time (timestamp), and calculated duration.
   Ensure clear categorization of time entries.
   Guidelines:
   Intuitive start, stop, and status commands.
   Consider auto-filling missing stop times or handling interrupted tracking gracefully.
   Future: Implement Pomodoro and reminder features while maintaining consistent logging.
4. Meds (To Build)
   Purpose: Manage and log medication usage.
   Consistency:
   Must store timestamp of when medication was taken, a reference to the medication (using a consistent identifier), and optionally dosage.
   Future: Store medication definitions with full name, dosage, frequency, and user-defined short references.
   Guidelines:
   Simple command to log medication intake (e.g., llog meds take <med_ref>).
   Support for adding new medications with relevant details.
5. External Context (To Build)
   Purpose: Automate environmental data collection.
   Consistency:
   Must store timestamp and the specific environmental data points (e.g., temperature, humidity, noise_level). Use consistent units where applicable.
   Clearly identify the source of the data (e.g., API, sensor).
   Guidelines:
   Configuration options for data sources and logging intervals.
   Ensure data is stored in a format that can be easily correlated with other log entries based on the timestamp.
6. Goals and Streaks (To Build)
   Purpose: Set achievement targets and track consistency.
   Consistency:
   Must link goals to specific modules (habits, metrics, time) and define target values or frequencies.
   Streak data should consistently track consecutive successful completions or adherence.
   Guidelines:
   Clear commands for defining and managing goals.
   Consistent visual representation of streaks in reports.
7. Correlation Viewer (To Build)
   Purpose: Explore relationships between tracked data.
   Consistency:
   Should be able to access and analyze data from all relevant modules based on timestamps.
   Clearly present the type of correlation and its strength.
   Guidelines:
   User-friendly syntax for specifying the data to compare (e.g., llog report compare mood --vs sleep).
8. Task Tracker (To Build)
   Purpose: Custom CLI task management.
   Consistency:
   Task data should include creation_timestamp, completion_timestamp (if applicable), status, category, tags, priority, and optionally deadline.
   Time spent per task should be logged consistently with the Time module.
   Guidelines:
   Commands for adding, listing, completing, and tracking time on tasks.
   Reporting that integrates task completion with time spent.
9. Form Modules (To Build)
   Purpose: Guided check-ins for multiple data points.
   Consistency:
   Data logged through forms should adhere to the consistency standards of the individual modules they are logging data for (e.g., llog form mental should log metrics with appropriate types and timestamps).
   Guidelines:
   Design prompt flows that are concise and easy to follow.
   Allow for customization of form contents.
10. ABC Behavioral Data (To Build)
    Purpose: Guided logging for Antecedent-Behavior-Consequence data.
    Consistency:
    Structure the logged data with clear fields for Antecedent, Behavior, and Consequence, along with relevant contextual information (intensity, setting, triggers).
    Ensure timestamping of each element.
    Guidelines:
    Implement a step-by-step prompting system to guide the user through the logging process.
11. Reporting
    Purpose: Summarize, visualize, and analyze logged data.
    Consistency:
    All reports should clearly state the time period and any filters applied.
    Report data completeness and confidence levels.
    Maintain a consistent style for CLI output (charts, summaries).
    Offer options to export report data (e.g., to JSON or CSV).
    Guidelines:
    Prioritize the development of core summary reports (summary metric, summary time, summary habits, summary daily).
    Design the reporting system to be modular and able to access data from all relevant modules.
    When implementing new reports (e.g., report compare, report correlations), focus on clear and interpretable output.
    IV. Steps to Align Existing Modules (as outlined in your notes)
    Continue following the outlined steps for renaming, cleaning, and updating existing modules to align with the unified module definitions and data consistency standards. Pay close attention to:

Renaming conventions: Use clear and consistent names (e.g., metrics.py).
Code refactoring: Update imports, function names, and help documentation.
Data migration (if necessary): If the underlying data structure needs to change, plan for a smooth migration process to avoid data loss.
V. Next Features to Build (Prioritization and Planning)
When building new modules, adhere to the principles and consistency guidelines outlined above. Consider the following for prioritization:

Core Functionality: Focus on modules that provide fundamental self-awareness capabilities (e.g., meds, improved habits with streaks, basic external context).
User Demand: Consider which features would provide the most immediate value to users.
Architectural Foundation: Build modules that establish key architectural patterns for later extensions (e.g., the reporting refactor).
For each new module:

Define the purpose and functionality clearly.
Plan the command structure and user interaction.
Design the data storage format, adhering to consistency standards.
Implement reporting hooks to allow for analysis of the new data.
Document the module and its commands thoroughly.
VI. Low Friction Usability Framework (Implementation)
Actively incorporate the principles of the Low Friction Usability Framework during development:

Implement shorthand and aliases: Allow users to define their own shortcuts.
Utilize smart defaults: Pre-fill common values and make optional prompts skippable.
Design concise prompt flows: Keep interactive logging brief.
Support backdated logging: Allow users to enter past data easily.
Consider a "fog mode" for low-energy logging: Implement a simplified logging option.
Use kind and encouraging language in prompts and feedback.
Display data confidence tags in reports.

metric

PY
report

PY
task

PY
time

PY

Provide me a cheat sheet so I can easily reference typer formatting and stuff for arguments so I can go through each of my modules and manually check they follow a unified formatting.
with explicit instructions on how I decide how arguments are formatted? like positional vs - vs -- vs param: vs other method of differentiating
can I make certain parameters that will exist on all "options" if they exist? For example, everything that involves a logging of some kind (not reports) should allow tags, which will be filterable when using any of the lists. I want tags to always be + then the tag they want to add, so +food and then keep a record of these tags somewhere for the user.

Another one might be notes, which might be like notes: then the note, for anything they log (even habits.)

Is there a way to create somewhat standard argument definitions like that?
