# 📦 Lifelog Module Definitions & Unification Plan

## ✅ Unified Module Definitions

### 1. **Metrics** (formerly "log" or "entry")

**Purpose:** Track continuous or regularly updated self-reported variables over time (e.g. mood, pain, energy, hydration).

- **Use for:** Anything tracked with a numeric, boolean, or simple value.
- **Examples:**
  - `llog mood 6 --notes "foggy"`
  - `llog hydration 40oz`

### 2. **Habits**

**Purpose:** Track recurring actions you want to complete regularly, optionally with targets (e.g. walk 30min/day).

- **Features:**
  - Track completion with `llog habit done <habit>`
  - Define targets (e.g. quantity or frequency)
  - Supports streak and goal tracking

### 3. **Time**

**Purpose:** Log time spent in various domains (work, rest, focus) and enable Pomodoro and stopwatch features.

- **Features:**
  - `llog time start focus`
  - `llog time stop`
  - `llog time status`
  - Domains for time categorization
  - Future: Pomodoro, reminders, domain summaries

### 4. **Meds** (to build)

**Purpose:** Manage and log medication usage.

- **Features:**
  - Define medications with short references
  - Track when meds are taken
  - Set frequency and compliance
  - Auto-log with shorthand or `metrics`

### 5. **External Context** (to build)

**Purpose:** Automate environmental data collection (weather, AQI, temp, noise).

- **Features:**
  - Configurable: sensors or API (zip code)
  - Automatically logs at intervals
  - Used for correlational insights

### 6. **Goals and Streaks** (to build)

**Purpose:** Set achievement targets across modules and track consistency.

- **Features:**
  - Tie to habits, time, or metrics
  - Visualize streaks
  - Reward with gamified feedback

### 7. **Correlation Viewer** (to build)

**Purpose:** Explore statistical relationships between tracked data.

- **Example:**
  - `llog report compare mood --vs sleep`

### 8. **Task Tracker** (to build)

**Purpose:** A fully custom CLI task system, integrated with time and reporting.

- **Features:**
  - `llog task add "Finish journal" --tags writing`
  - Time-based tracking like Timewarrior
  - Priority, tags, deadlines

### 9. **Form Modules** (to build)

**Purpose:** Allow quick, guided check-ins for multiple types of data at once.

- **Examples:**
  - `llog form mental`
  - `llog form physical`

### 10. **ABC Behavioral Data** (to build)

**Purpose:** Guided logging for Antecedent-Behavior-Consequence data tracking.

- **Example:** Prompt user step-by-step through:
  - What happened before, during, after
  - How intense, what setting, what triggers

### 11. **Reporting**

**Purpose:** Summarize, visualize, and analyze any kind of log data.

- Includes:
  - `summary` commands
  - Correlations, trends, insights
  - Heatmaps, pie charts, radar plots

---

## 🛠️ Steps to Align Existing Modules with This Plan

### ✅ Step 1: Rename `log.py` → `metrics.py`

- Update `llog.py`: `from commands import metrics` instead of `log`
- Rename internal help and function docs
- Rename all references to `log` or `entry` → `metric`

### ✅ Step 2: Clean Help Section

- Show `llog <metric> <value>` syntax
- Clarify that `metrics` is the primary module for anything numeric or recurring

### ✅ Step 3: Update `entry` function

- Support alias, shorthand, and tags/notes
- Validate against metric definitions from config

### 🧼 Step 4: Align `habit.py` logic

- Support `done`, `add`, `set-goal`, `list`
- Build toward streaks and progress checks

### ⏱ Step 5: Expand `time.py`

- Ensure time logs store domain/category clearly
- Add support for Pomodoro / reminders (to do)

### 🔁 Step 6: Reporting Hooks

- Make sure `summary.py` uses data from updated modules
- Add report commands for metrics, habits, and time first

---

## 📌 What's Next to Build

- [ ] `meds.py`
- [ ] `external.py` (for environment tracking)
- [ ] `tasks.py` (full custom task CLI)
- [ ] `form.py` (prompt-based group input)
- [ ] `abc.py` (ABC behavioral logging)
- [ ] `goals.py` + streak logic
- [ ] Reporting refactor under `report.py` with unified logic
