# 🚀 Release Management & Security Guide

## 🔒 Secure Release Process

### Pre-Release Security Checklist
```bash
# 1. Security scan
bandit -r lifelog/
safety check

# 2. Check for secrets
grep -r -i "password\|token\|secret\|key" --include="*.py" lifelog/

# 3. Dependency audit
pip-audit

# 4. Build and test
python -m build
pip install dist/*.whl
llog --help
```

### Version Management
```bash
# Update version in pyproject.toml
# Follow semantic versioning: MAJOR.MINOR.PATCH
# 0.1.0 -> 0.1.1 (bug fixes)
# 0.1.1 -> 0.2.0 (new features)  
# 0.2.0 -> 1.0.0 (stable release)

# Tag the release
git tag v0.1.0
git push origin v0.1.0
```

## 🤖 Automated Release (Recommended)

### GitHub Actions Workflow
```bash
# 1. Create and push tag
git tag v0.1.0
git push origin v0.1.0

# 2. GitHub Actions automatically:
# - Runs security checks
# - Builds packages
# - Creates GitHub release
# - Uploads wheel and source distribution
```

The `.github/workflows/release.yml` handles:
- ✅ Security scanning
- ✅ Dependency checks
- ✅ Build verification
- ✅ Package creation
- ✅ Release publishing

## 🛡️ Manual Release (With Security)

### Step 1: Security Verification
```bash
# Check for vulnerabilities
safety check --json

# Security linting
bandit -r lifelog/ -f json

# Verify no secrets
! grep -r -i "password.*=\|token.*=" --include="*.py" lifelog/
```

### Step 2: Build Verification
```bash
# Clean previous builds
rm -rf dist/ build/ *.egg-info/

# Build packages
python -m build

# Verify package contents
tar -tzf dist/lifelog-*.tar.gz | head -20
unzip -l dist/lifelog-*.whl | head -20
```

### Step 3: Local Testing
```bash
# Test installation in clean environment
python -m venv test_env
source test_env/bin/activate
pip install dist/lifelog-*.whl

# Verify functionality
llog --help
llog setup
deactivate && rm -rf test_env
```

### Step 4: Create GitHub Release
```bash
# Using GitHub CLI (if available)
gh release create v0.1.0 dist/*.whl dist/*.tar.gz \
  --title "Lifelog v0.1.0" \
  --notes-file release-notes.md

# Or manually at:
# https://github.com/zach-mckinnon/lifelog/releases/new
```

## 📋 Comprehensive Release Checklist

### Pre-Release Requirements
- [ ] **Code Quality**: All code reviews completed
- [ ] **Security**: Security scans pass (bandit, safety)  
- [ ] **Dependencies**: All dependencies up to date and secure
- [ ] **Documentation**: README, CONTRIBUTING, INSTALL updated
- [ ] **Version**: Updated in `pyproject.toml`
- [ ] **Branch Protection**: Ensure main/public branches protected
- [ ] **Local Testing**: Full functionality test completed

### Release Execution
- [ ] **Security Scan**: Run final security checks
- [ ] **Build**: Clean build with `python -m build`
- [ ] **Test Install**: Verify installation in clean environment
- [ ] **Git Tag**: Create and push version tag
- [ ] **GitHub Release**: Create with proper assets and notes
- [ ] **Package Verification**: Verify downloadable packages work

### Post-Release Verification
- [ ] **Download Test**: Install from GitHub release URL
- [ ] **Functionality Test**: Core features work after install
- [ ] **Documentation**: Update installation links if needed
- [ ] **Community**: Announce in discussions/README
- [ ] **Monitor**: Watch for issues and feedback

## 🎯 Distribution Methods

### 1. GitHub Releases (Current)
```bash
# Users install with:
pip install https://github.com/zach-mckinnon/lifelog/releases/download/v0.1.0/lifelog-0.1.0-py3-none-any.whl
```

### 2. Future: PyPI Distribution
```bash
# Setup (one-time):
pip install twine
python -m twine upload --repository testpypi dist/*

# Users would install with:
pip install lifelog
```

### 3. Future: System Packages
```bash
# Debian/Ubuntu (future):
sudo apt install lifelog

# Homebrew (future):
brew install lifelog

# Snap (future):
sudo snap install lifelog
```

## 🧪 Testing Instructions for Users

### Quick Start Testing
```markdown
# 🧪 Testing Lifelog v0.1.0

## Installation
```bash
# Download wheel from GitHub releases
pip install lifelog-0.1.0-py3-none-any.whl
```

## Basic Test Suite
```bash
# 1. Setup
llog setup

# 2. Time tracking
llog time start "Testing session"
llog time status
llog time stop

# 3. Task management
llog task add "Test task" --cat work
llog task list

# 4. Reporting
llog report summary
```

## What to Report
- ✅ **Installation success/failure**
- ✅ **Performance on your hardware**
- ✅ **Any error messages**
- ✅ **UI/UX feedback**
- ✅ **Feature requests**

## Feedback Channels
- **Bugs**: GitHub Issues
- **Questions**: GitHub Discussions  
- **Features**: GitHub Issues (enhancement label)
```

## 🚨 Security-First Releases

### Never Release With:
❌ Hardcoded secrets or credentials  
❌ Personal file paths  
❌ Unvetted dependencies  
❌ Known security vulnerabilities  
❌ Untested installation process  

### Always Include:
✅ Security scan reports  
✅ Dependency vulnerability checks  
✅ Clean build verification  
✅ Installation testing  
✅ Proper version tagging  

## 📞 Release Support

### For Users Having Issues:
1. Check GitHub Issues for known problems
2. Verify system requirements (Python 3.9+)
3. Try installation in clean virtual environment
4. Report with full error logs and system info

### For Contributors:
1. Follow security guidelines in SECURITY.md
2. Test on multiple platforms when possible
3. Verify no secrets in commits
4. Request review from maintainers

---

**Security and quality first - every release represents our commitment to users! 🛡️**