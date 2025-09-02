# Good First Issues for New Contributors

## 🔰 Documentation & Testing (Beginner-Friendly)

### Issue: "Add more usage examples to README"

**Labels:** `good first issue`, `documentation`  
**Description:** Our README could use 2-3 more real-world usage examples showing different workflows (student schedule, work tracking, habit building).  
**Skills needed:** Writing, basic CLI usage  
**Time estimate:** 1-2 hours

### Issue: "Test installation on Python 3.10, 3.11, 3.12"

**Labels:** `good first issue`, `testing`  
**Description:** Verify our app works correctly on newer Python versions and document any issues.  
**Skills needed:** Basic Python environment management  
**Time estimate:** 1 hour

### Issue: "Create beginner's tutorial video or guide"

**Labels:** `good first issue`, `documentation`, `help wanted`  
**Description:** Create a 5-minute walkthrough showing someone's first time using lifelog.  
**Skills needed:** Communication, screen recording (optional)  
**Time estimate:** 2-3 hours

## 🛠️ Small Features (Intermediate)

### Issue: "Add --json output option to report commands"

**Labels:** `enhancement`, `good first issue`  
**Description:** Allow users to export reports in JSON format for external processing.  
**Skills needed:** Python, CLI frameworks  
**Time estimate:** 3-4 hours  
**Files to look at:** `lifelog/commands/report.py`

### Issue: "Improve time tracking status display"

**Labels:** `enhancement`, `ui`  
**Description:** Make `llog time status` show more informative output (time elapsed, current activity, daily totals).  
**Skills needed:** Python, Rich library  
**Time estimate:** 2-3 hours  
**Files to look at:** `lifelog/commands/time_module.py`

### Issue: "Add basic CSV export for tasks"

**Labels:** `enhancement`, `export`  
**Description:** Implement `llog task export tasks.csv` command.  
**Skills needed:** Python, CSV handling  
**Time estimate:** 3-4 hours  
**Files to look at:** `lifelog/utils/db/task_repository.py`

## 🚀 Bigger Features (Advanced)

### Issue: "Implement data backup/restore commands"

**Labels:** `enhancement`, `help wanted`  
**Description:** Add `llog backup` and `llog restore` commands for full data management.  
**Skills needed:** Python, SQLite, file handling  
**Time estimate:** 6-8 hours

### Issue: "Add plugin/hook system"

**Labels:** `enhancement`, `architecture`  
**Description:** Design extensibility system for custom commands and data processing.  
**Skills needed:** Python, system design, plugin architectures  
**Time estimate:** 10+ hours

## 🥧 Raspberry Pi Specific

### Issue: "Performance testing on Pi Zero/Pi 4"

**Labels:** `raspberry-pi`, `testing`, `performance`  
**Description:** Test app performance on different Pi models and document optimization opportunities.  
**Skills needed:** Raspberry Pi, performance profiling  
**Hardware needed:** Raspberry Pi  
**Time estimate:** 4-6 hours

### Issue: "Create Pi installation script"

**Labels:** `raspberry-pi`, `automation`, `good first issue`  
**Description:** Create bash script to automate lifelog installation on fresh Pi OS.  
**Skills needed:** Bash scripting, Raspberry Pi OS  
**Time estimate:** 2-3 hours

## 🎨 UI/UX Improvements

### Issue: "Add color themes for terminal output"

**Labels:** `enhancement`, `ui`, `good first issue`  
**Description:** Implement different color schemes (dark, light, high-contrast).  
**Skills needed:** Python, Rich library, design sense  
**Time estimate:** 4-5 hours

### Issue: "Improve error messages and help text"

**Labels:** `enhancement`, `ux`, `good first issue`  
**Description:** Review all error messages for clarity and helpfulness.  
**Skills needed:** UX writing, CLI experience  
**Time estimate:** 3-4 hours

## 📱 Future Features

### Issue: "Research mobile companion app approaches"

**Labels:** `research`, `mobile`, `help wanted`  
**Description:** Research and document approaches for mobile companion (web app, native, API-only).  
**Skills needed:** Mobile development knowledge, API design  
**Time estimate:** 6-8 hours

### Issue: "Design API v2 with better REST patterns"

**Labels:** `api`, `architecture`, `enhancement`  
**Description:** Review current sync API and propose improvements.  
**Skills needed:** REST API design, Python Flask  
**Time estimate:** 8-10 hours
