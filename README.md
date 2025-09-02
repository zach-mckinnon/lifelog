# 🚀 Lifelog CLI — The Ultimate Neurodivergent Productivity & Insights App

**Lifelog** is your personal command-line home for comprehensive life tracking with a **Beautiful CLI interface**, advanced analytics, and multi-device sync—designed for neurodivergent users who demand both power and clarity.

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Raspberry Pi](https://img.shields.io/badge/Raspberry%20Pi-Optimized-red.svg)](https://www.raspberrypi.org/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

## ✨ Recent Updates

- **🎨 Enhanced CLI**: CLI interface with loading states, progress indicators, and beautiful visual feedback
- **🔧 Pi Optimization**: Full Raspberry Pi Zero 2W support with automatic performance tuning
- **⚡ Database Performance**: 23 strategic indexes for lightning-fast queries
- **🛡️ Robust Error Handling**: Comprehensive validation and graceful error recovery
- **📊 Advanced Analytics**: Rich reporting with correlation analysis and behavioral insights

---

## 🎯 Why Lifelog?

### **For Real Brains, Real Life**
- **Tame Complexity**: Track tasks, habits, health, time, mood, and environment across all devices
- **Meaningful Insights**: Go beyond to-do lists with clinical behavioral patterns and actionable analytics
- **Data Ownership**: Local-first, privacy-respecting. Your data, your rules, your devices
- **Neurodivergent-First**: Built by and for users with ADHD, Autism, chronic illness—where clarity and motivation matter most

### **Modern CLI Experience**
```bash
┌─────────────────────────────────────────────────────────────────┐
│                    Starting Time Tracking                       │
│              Initialize new time tracking session               │
└─────────────────────────────────────────────────────────────────┘
✅ Started tracking: 'Deep Work Session'
┌───────────────────── Time Tracking Session ─────────────────────┐
│  Activity: Deep Work Session                                   │
│  Category: work                                                 │
│  Duration: 1h 23m                                             │
│  Efficiency: 94.2%                                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🎛️ Core Features

### **📊 Time Tracking & Focus**
- **Smart Time Sessions**: Enhanced start/stop with automatic efficiency calculations
- **Focus Mode**: Distraction-free CLI with ASCII timers and Pomodoro support
- **Real-time Status**: Beautiful status cards showing current activity and productivity metrics
- **Advanced Analytics**: Track focused vs. distracted time with detailed reporting

```bash
llog time start "Deep Work"        # Start with enhanced interface
llog time status                   # Beautiful status dashboard
llog time stop                     # Detailed completion summary
```

### **✅ Task Management**
- **Smart Task Creation**: Interactive setup with validation and category management
- **Priority Algorithms**: Intelligent ranking based on importance and urgency
- **Recurring Tasks**: Flexible scheduling with multiple patterns
- **Focus Integration**: Seamless time tracking integration

```bash
llog task add "Write quarterly report" --cat work --due "next friday"
llog task agenda                   # Calendar view with priorities
llog task focus "Task Title"       # Distraction-free focus mode
```

### **📈 Habit & Health Tracking**
- **Custom Trackers**: Create measurements for mood, energy, symptoms, medications
- **Goal Systems**: Multiple goal types (streaks, averages, milestones, ranges)
- **Smart Reminders**: Automated recurring tracker prompts
- **Correlation Analysis**: Discover patterns between different tracked metrics

```bash
llog track add "Mood" --type scale
llog track add "Sleep Quality" --type number
llog track add "Medication" --type bool
```

### **📋 Advanced Reporting**
- **Daily Summaries**: Comprehensive activity and productivity reports
- **Trend Analysis**: Long-term pattern recognition and behavioral insights
- **Correlation Reports**: Discover relationships between tracked metrics
- **Visual Charts**: Terminal-based graphs, charts, and heatmaps

```bash
llog report summary               # Daily overview
llog report correlation           # Pattern analysis
llog report daily-tracker "Mood"  # Specific metric trends
```

### **🔄 Multi-Device Sync**
- **Server/Client Architecture**: Host device serves data to client devices
- **Real-time Sync**: Automatic synchronization with conflict resolution
- **Device Pairing**: Secure token-based authentication
- **Offline Support**: Queue operations when disconnected

```bash
llog api start --host 0.0.0.0     # Start sync server
llog api pair                     # Pair client device
llog sync                         # Manual sync trigger
```

### **🌍 Environment Integration**
- **Weather Sync**: Automatic local weather data collection
- **Location Tracking**: Configure timezone and location settings
- **Environmental Correlations**: Link external factors to mood and productivity

---

## ⚡ Performance & Optimization

### **🎯 Raspberry Pi Ready**
- **Automatic Detection**: Recognizes Pi hardware and optimizes accordingly
- **Memory Management**: Intelligent lazy loading and resource cleanup
- **Database Optimization**: 23 strategic indexes for fast queries on limited hardware
- **Power Efficiency**: Optimized for Pi Zero 2W with minimal resource usage

### **🔧 Technical Excellence**
- **Sub-millisecond Queries**: Comprehensive database indexing strategy
- **Memory Efficiency**: Lazy loading for pandas, numpy, and heavy dependencies  
- **Error Recovery**: Graceful handling of database locks, network issues, and hardware constraints
- **Timezone Handling**: Robust UTC-aware datetime management throughout

---

## 🚀 Installation & Quick Start

### **Prerequisites**
- Python 3.9+ (optimized for Raspberry Pi compatibility)
- SQLite (included with Python)

### **Install**
```bash
pip install -e .
```

### **Initial Setup**
```bash
llog setup
```
*Interactive wizard configures location, sync, categories, and preferences*

### **Start Tracking**
```bash
# Time tracking
llog time start "Morning routine"
llog time status
llog time stop

# Task management  
llog task add "Plan weekend trip" --cat personal --due tomorrow
llog task list --status active

# Habit tracking
llog track add "Energy Level" --type scale
llog track add "Water Intake" --type number
```

### **View Insights**
```bash
llog report summary              # Today's overview
llog start-day                   # Guided morning routine
```

---

## 🔧 Advanced Configuration

### **Multi-Device Setup**

**Host Device (Raspberry Pi or main computer):**
```bash
llog api start --host 0.0.0.0 --port 5000
llog api get-server-url  # Get connection details for other devices
```

**Client Devices:**
```bash
llog api pair  # Enter pairing code from host
llog sync      # Manual sync (automatic in background)
```

### **Customization**
- **Categories**: Customize work, personal, health categories with importance weights
- **Hooks**: Drop scripts in `~/.lifelog/hooks/` for event automation
- **Configuration**: Full TOML-based config in `~/.lifelog/config.toml`

### **Data Export**
```bash
llog backup backup_2024.db       # Full database backup
# Future: CSV/JSON export options
```

---

## 📊 Command Reference

### **Time Commands**
| Command | Description |
|---------|-------------|
| `llog time start <activity>` | Start tracking with enhanced interface |
| `llog time stop` | Stop with detailed completion summary |
| `llog time status` | Current session dashboard |
| `llog time summary` | Time analysis by category/project |
| `llog time distracted` | Log distraction without stopping |

### **Task Commands**
| Command | Description |
|---------|-------------|
| `llog task add <title>` | Create task with smart validation |
| `llog task list` | Filterable task list |
| `llog task agenda` | Calendar view with priorities |
| `llog task focus <id>` | Distraction-free focus mode |
| `llog task done <id>` | Mark complete |

### **Tracking Commands**
| Command | Description |
|---------|-------------|
| `llog track add <name>` | Create new tracker |
| `llog track list` | View all trackers |
| `llog track goals-help` | Goal type documentation |

### **System Commands**
| Command | Description |
|---------|-------------|
| `llog setup` | Initial configuration wizard |
| `llog config-edit` | Interactive settings editor |
| `llog backup <path>` | Database backup |
| `llog sync` | Manual device sync |

---

## 🛡️ Security & Privacy

### **Data Ownership**
- **Local-First**: All data stored in `~/.lifelog/` on your devices
- **No Cloud Dependencies**: Sync only between your own devices
- **Open Source**: Full code transparency and auditability

### **Multi-Device Security**
- **Token Authentication**: Secure device pairing with rotating tokens
- **Private Networks Only**: Designed for home networks, VPNs, or SSH tunnels
- **No Public Internet**: Never expose the API server to public internet

### **File Permissions**
```bash
chmod 700 ~/.lifelog    # Restrict access to your user only
```

---

## 🎨 Interface Examples

### **Enhanced Time Tracking**
```bash
$ llog time start "Research project"
┌─────────────────────────────────────────────────────────────┐
│                Starting Time Tracking                       │
│          Initialize new time tracking session               │
└─────────────────────────────────────────────────────────────┘
✅ Started tracking: 'Research project'
┌─────────────── Time Tracking Session ───────────────────────┐
│  Activity: Research project                                │
│  Category: work                                            │
│  Started: 14:30:15                                         │
│  Tags: None                                                │
└─────────────────────────────────────────────────────────────┘
```

### **Task Focus Mode**
```bash
$ llog task focus 5
╔══════════════════════════════════════════════════════════════╗
║                     FOCUS MODE                               ║
║  Task: Write quarterly report                                ║
║  Time: 00:25:30 / 01:00:00                                  ║
║  ████████████████░░░░░░░░ 85%                               ║
╚══════════════════════════════════════════════════════════════╝
```

### **Performance Monitoring**
```bash
┌────────────── Database Operation Performance ───────────────┐
│  Duration: 0.15s                                           │
│  System Memory: 512MB                                      │
│  Database Cache: 5000 pages                                │
│  Platform: Raspberry Pi (Optimized)                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 🤝 Contributing

### **Development Setup**
```bash
git clone <repository>
cd lifelog
pip install -e .
llog setup
```

### **Testing**
- All features tested on Python 3.9+ and Raspberry Pi Zero 2W
- Comprehensive error handling and edge case validation
- Performance optimized for low-memory environments

### **License**
- **GNU GPLv3**: No commercial resale or SaaS without permission
- **CLA Required**: Contributors must sign Contributor License Agreement
- **Community-Driven**: PRs, bug reports, and feature requests welcome

---

## 💡 Philosophy

**Lifelog isn't just another productivity app.**

It's built for real people with real brains—those who need clarity over chaos, insight over metrics, and control over their data. Whether you're managing ADHD, autism, chronic illness, or just want to understand yourself better, Lifelog provides the structure and insights you need.

**Your data. Your insights. Your life.**

---

## 🚀 Ready to Start?

```bash
pip install -e .
llog setup
```

**Begin your journey of self-understanding today.**

---

## 📞 Support & Community

- **Issues**: [GitHub Issues](https://github.com/your-repo/issues)
- **Discussions**: [GitHub Discussions](https://github.com/your-repo/discussions)  
- **Feature Requests**: Tag with `enhancement`
- **Pi Support**: Optimized and tested on Raspberry Pi Zero 2W

**Built with ❤️ for the neurodivergent community**
