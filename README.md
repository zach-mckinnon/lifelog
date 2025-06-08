# Lifelog CLI — The Ultimate Neurodivergent Productivity & Insights App

**Lifelog** is your personal command-line home for all the essentials:

- Tasks, habits, health, time, mood, and environment
- Advanced, actionable reporting & AI-powered insights
- Multi-device syncing (your data, your way)
- Designed for neurodivergent folks who love the keyboard and want _real_ self-knowledge

---

## Why Lifelog?

- **Tame Your Life, On Your Terms:**  
  Track what matters—work, routines, sleep, mood, energy, symptoms, environmental factors—across all your devices.
- **Powerful Reporting & AI:**  
  Go beyond "to-do lists"—get _meaningful insights_ and _clinical behavioral patterns_ to drive real change and motivation.
- **Data Belongs to You:**  
  Local-first, privacy-respecting. Open source. No forced cloud. Sync only what you want, how you want.
- **Built for Real Brains:**  
  Inspired by and built for neurodivergent users (ADHD, Autism, chronic illness), where _clarity_ and _motivation_ matter most.
- **Extensible and Hackable:**  
  Powerful CLI, curses-based UI, modular architecture. If you can dream it, you can script it.

---

## Key Features

- **Track Everything:**
  - Custom "trackers" for mood, focus, sleep, pain, water, meds, more
  - Flexible time tracking (work, school, rest, etc.)
  - Pomodoro and "focus mode" support
  - Project, task, and habit management (including recurring tasks)
  - Environment/health event logging
- **Multi-Device Sync:**
  - Personal server mode: keep your data in sync between devices using a simple REST API
  - Built for privacy; you control your data location and security
- **Advanced Reporting & Insights:**
  - Correlation and trend analysis across all data types
  - Clinical behavioral metrics (streaks, routine adherence, mood trends, and more)
  - AI-powered feedback (optional)
  - Visualizations: charts, pie graphs, heatmaps—right in your terminal!
- **Hooks & Extensibility:**
  - Plug in custom scripts (e.g., push notifications, automation, etc.)
- **Designed for Real-World Use:**
  - Interactive setup wizard and tutorial
  - Keyboard-first, distraction-free UI
  - Export and backup options (CSV, JSON)
  - Rich CLI with colorful output and powerful search/filter

---

## Security & Privacy Warning

> **Lifelog is designed for local, single-user use only!**
>
> - **No "real" encryption:**  
>   API and AI keys are stored in your config folder (`~/.lifelog`). These are not strongly encrypted—anyone with access to your files can read them.
> - **Not for public internet/server deployment:**  
>   The API server is intended for _your own devices only_. Never expose to the public internet without an HTTPS reverse proxy, strong OS security, and careful firewalling.
> - **You own your data:**  
>   Protect your `~/.lifelog` folder using OS permissions (`chmod 700 ~/.lifelog`) and don't share your computer/login.

---

## Quick Start (after install)

### 1. Run the Setup Wizard

```bash
llog setup
```

Configure location, scheduled tasks, AI features, and multi-device sync. Walks you through every option, with clear explanations and help.

### 2. Start Logging Your Life

**Track a habit or metric:**

```bash
llog track add "Mood"
```

**Start a time session:**

```bash
llog time start "Work"
```

**Add a task:**

```bash
llog task add "Write daily report"
```

**Launch the TUI (full-screen mode):**

```bash
llog ui
```

### 3. Sync Across Devices

**Start the API server on your "host" device:**

```bash
llog api-start --host 127.0.0.1 --port 5000
```

On other devices, set up as "client" mode and provide the host's URL.

For secure remote access, use an SSH tunnel or VPN (see advanced section below).

### 4. See Insights & Reports

**Generate a daily summary:**

```bash
llog report summary
```

**Get AI-driven feedback and prescriptive advice:**

```bash
llog report insight
```

---

## Advanced Usage

**Export your data:**

```bash
llog export --type=tasks --format=csv
```

**Hook in custom automations:**  
Drop scripts in `~/.lifelog/hooks` to run on events (see docs).

**Docker deployment:**  
Generated Dockerfiles make it easy to run your own API server.

**Customize everything:**  
Fully modular—extend with your own plugins, scripts, or UI tweaks.

---

## Contributing & Licensing

- **License:** GNU GPLv3 (no commercial resale or SaaS allowed without written permission)
- **CLA Required:** Contributors must sign a Contributor License Agreement; see CONTRIBUTING.md
- **No selling or closed forks permitted**
- PRs, bug reports, and feature requests are welcome!

---

## Security & Design Philosophy

- You control your data and your privacy
- No cloud. No ads. No forced sync. Just your data, on your terms
- All logging, AI keys, and data are stored in your own user folder, not sent to anyone unless you configure it
- **Advanced users:** For "real" encryption or multi-user use, please see Security Considerations and review the codebase for your needs

---

## Support & Community

**Issues?**  
File a ticket or start a discussion in the Issues section.

**Want to chat?**  
See the Discussions tab (or open a GitHub Discussion).

**Feature request?**  
Open an issue tagged `enhancement`.

---

## Final Note

Lifelog is built for real people with real brains, not just for "productivity hackers."  
If you want a tool that helps you understand yourself, not just get more done—  
You're in the right place.

**Ready to take control?**

```bash
llog setup
```

and start living with insight.
