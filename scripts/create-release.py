#!/usr/bin/env python3
"""
Script to create a GitHub release with built packages.
Run this after building packages with `python -m build`
"""
import subprocess
import sys
import os
from pathlib import Path

def run_command(cmd, check=True):
    """Run a command and return the result."""
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"Error: {result.stderr}")
        sys.exit(1)
    return result

def main():
    # Check if we're in the right directory
    if not Path("pyproject.toml").exists():
        print("Error: Run this script from the project root directory")
        sys.exit(1)
    
    # Check if dist files exist
    dist_dir = Path("dist")
    if not dist_dir.exists() or not list(dist_dir.glob("*.whl")):
        print("Building packages first...")
        run_command("python -m build")
    
    # Get version from pyproject.toml
    try:
        import tomllib
        with open("pyproject.toml", "rb") as f:
            config = tomllib.load(f)
        version = config["project"]["version"]
    except ImportError:
        # Fallback for Python < 3.11
        import toml
        with open("pyproject.toml", "r") as f:
            config = toml.load(f)
        version = config["project"]["version"]
    
    tag_name = f"v{version}"
    
    print(f"Creating release {tag_name}")
    
    # Create git tag if it doesn't exist
    result = run_command(f"git tag {tag_name}", check=False)
    if result.returncode != 0:
        print(f"Tag {tag_name} already exists or error creating tag")
    
    # Push tag
    run_command(f"git push origin {tag_name}", check=False)
    
    # Create GitHub release using gh CLI
    wheel_file = list(dist_dir.glob("*.whl"))[0]
    tar_file = list(dist_dir.glob("*.tar.gz"))[0]
    
    release_body = f"""## Lifelog Release {tag_name}

### Quick Install
```bash
# Download and install from this release
pip install {wheel_file.name}
llog setup
```

### Installation Options
1. **Wheel Package**: `pip install {wheel_file.name}`
2. **Source Distribution**: `pip install {tar_file.name}`
3. **Development**: `git clone <repo> && cd lifelog && pip install -e .`

### Quick Start
```bash
llog setup                    # Interactive setup wizard
llog time start "Work"        # Start time tracking
llog task add "Test task"     # Create tasks
llog track add "Mood"         # Custom tracking
llog report summary           # View insights
```

### What's Included
- Claude-inspired CLI with loading states and visual feedback  
- Raspberry Pi Zero 2W optimization with automatic detection
- Advanced analytics with correlation analysis
- Multi-device sync with secure pairing
- Lightning-fast database performance (23 optimized indexes)

See [INSTALL.md](https://github.com/zach-mckinnon/lifelog/blob/main/INSTALL.md) for detailed installation instructions.

**System Requirements:** Python 3.9+, 512MB RAM (Pi compatible)
"""
    
    try:
        # Try using gh CLI
        run_command(f'gh release create {tag_name} {wheel_file} {tar_file} --title "Lifelog {tag_name}" --notes "{release_body}"')
        print(f"✅ GitHub release {tag_name} created successfully!")
        print(f"📦 Wheel: {wheel_file}")
        print(f"📦 Source: {tar_file}")
        print("\n🚀 Testers can now install with:")
        print(f"   pip install {wheel_file.name}")
        
    except subprocess.CalledProcessError:
        print("\n❌ GitHub CLI (gh) not available or not authenticated.")
        print("Manual release creation:")
        print(f"1. Go to: https://github.com/zach-mckinnon/lifelog/releases/new")
        print(f"2. Tag: {tag_name}")
        print(f"3. Title: Lifelog {tag_name}")
        print(f"4. Upload files: {wheel_file}, {tar_file}")
        print("5. Use the release notes from release-notes.md")

if __name__ == "__main__":
    main()