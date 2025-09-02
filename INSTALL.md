# 🚀 Lifelog Installation Guide

Multiple installation methods for different use cases and testing scenarios.

## 🚀 Release Installation (Recommended for Testers)

### Install from GitHub Release
```bash
# Download the latest wheel file from GitHub releases
# https://github.com/yourusername/lifelog/releases

# Install the downloaded wheel
pip install lifelog-0.1.0-py3-none-any.whl

# Run setup
llog setup
```

### One-Command Install (when available)
```bash
# Future: Direct install from GitHub releases
pip install https://github.com/yourusername/lifelog/releases/latest/download/lifelog-0.1.0-py3-none-any.whl

# Run setup  
llog setup
```

---

## 📦 Development Installation Methods

### Method 1: Direct from Source (Recommended for Development)
```bash
# Clone or download the project
cd lifelog-project-directory

# Install in development mode (editable)
pip install -e .

# Run initial setup
llog setup
```

### Method 2: From Built Package (Testing/Distribution)
```bash
# Install from wheel file
pip install dist/lifelog-0.1.0-py3-none-any.whl

# Or install from source distribution
pip install dist/lifelog-0.1.0.tar.gz

# Run initial setup
llog setup
```

### Method 3: Virtual Environment Setup (Raspberry Pi Compatible)
```bash
# Create Python 3.9 virtual environment (Pi Zero 2W compatible)
python3.9 -m venv venv39
source venv39/bin/activate  # Linux/Mac
# venv39\Scripts\activate   # Windows

# Install from source
pip install -e .

# Run setup
llog setup
```

## 🔧 Development Installation

### For Contributors and Testers
```bash
# Clone repository
git clone <repository-url>
cd lifelog

# Install in development mode with all dependencies
pip install -e .

# Install build tools (optional, for packaging)
pip install build twine

# Run initial setup
llog setup

# Test installation
llog --help
llog time start "Test session"
llog time stop
```

## 🏗️ Building from Source

### Create Distribution Packages
```bash
# Install build tools
pip install build

# Build both wheel and source distributions
python -m build

# Files created in dist/:
# - lifelog-0.1.0-py3-none-any.whl (wheel package)
# - lifelog-0.1.0.tar.gz (source distribution)
```

## 🥧 Raspberry Pi Installation

### Raspberry Pi Zero 2W Optimized Setup
```bash
# Ensure Python 3.9+ is installed
python3 --version

# Create virtual environment (recommended)
python3 -m venv lifelog-env
source lifelog-env/bin/activate

# Install with Pi optimizations
pip install -e .

# Run setup with Pi detection
llog setup

# The app automatically detects Pi hardware and optimizes performance
```

### Pi-Specific Notes
- **Memory Management**: Heavy dependencies (numpy, pandas) are lazy-loaded
- **Performance**: 23 database indexes optimize for limited hardware
- **Storage**: Database stored in `~/.lifelog/` with automatic cleanup

## 🌐 Network/Multi-Device Setup

### Host Device (Pi or Main Computer)
```bash
# Install lifelog
pip install -e .
llog setup

# Start API server for other devices
llog api start --host 0.0.0.0 --port 5000

# Get connection details
llog api get-server-url
```

### Client Devices
```bash
# Install on each device
pip install -e .
llog setup

# Pair with host device
llog api pair  # Enter pairing code from host

# Test sync
llog sync
```

## ✅ Post-Installation Verification

### Basic Functionality Test
```bash
# Check installation
llog --help

# Initialize (if not done during install)
llog setup

# Test core features
llog task add "Test task" --cat work
llog time start "Test session"
llog time status
llog time stop

# Test reporting
llog report summary

# Test tracking
llog track add "Test Tracker" --type bool
llog track list
```

### Performance Test (Pi)
```bash
# Check Pi optimization status
llog report summary  # Should show Pi-optimized performance info

# Test database performance
llog task list  # Should be fast even with many tasks
```

## 🛠️ Troubleshooting

### Common Issues

**Import Error: Missing Dependencies**
```bash
# Install missing packages
pip install psutil rich typer pendulum

# Or reinstall completely
pip uninstall lifelog
pip install -e .
```

**Permission Errors**
```bash
# Ensure proper permissions for config directory
chmod 700 ~/.lifelog
```

**Database Issues**
```bash
# Backup and reset if needed
llog backup backup_$(date +%Y%m%d).db
rm ~/.lifelog/lifelog.db
llog setup
```

**Sync Issues**
```bash
# Check network connectivity
llog api pair  # Re-pair devices if needed
llog sync --verbose  # Debug sync issues
```

## 📋 System Requirements

### Minimum Requirements
- **Python**: 3.9+
- **RAM**: 512MB (Pi Zero 2W compatible)
- **Storage**: 50MB for app + database storage
- **OS**: Windows, macOS, Linux, Raspberry Pi OS

### Recommended Requirements
- **RAM**: 1GB+ for heavy analytics
- **Python**: 3.10+ for best performance
- **Network**: For multi-device sync

## 🚀 Quick Start After Installation

```bash
# 1. Initial setup
llog setup

# 2. Start tracking immediately
llog time start "My first session"

# 3. Add a task
llog task add "Try out lifelog" --cat personal

# 4. Create a custom tracker
llog track add "Mood" --type scale

# 5. View your progress
llog report summary
```

**You're ready to start tracking your life! 🎉**

---

For support, check the [README.md](README.md) or create an issue in the repository.