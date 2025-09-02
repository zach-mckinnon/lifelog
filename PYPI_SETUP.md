# 📦 PyPI Publishing Setup

## Making `pip install lifelog` Work

To enable users to install with just `pip install lifelog`, you need to publish to PyPI (Python Package Index).

## 🚀 One-Time PyPI Setup

### 1. Create PyPI Account

- Go to https://pypi.org/account/register/
- Verify email address
- Enable 2FA (strongly recommended)

### 2. Create Test PyPI Account

- Go to https://test.pypi.org/account/register/
- This is for testing releases before going live

### 3. Generate API Tokens

```bash
# PyPI Main (for production releases)
# Go to: https://pypi.org/manage/account/token/
# Create token with scope: "Entire account"

# Test PyPI (for testing)
# Go to: https://test.pypi.org/manage/account/token/
# Create token with scope: "Entire account"
```

### 4. Configure Local Environment

```bash
# Install publishing tools
pip install twine build

# Configure credentials (one-time setup)
# Create ~/.pypirc
cat > ~/.pypirc << EOF
[distutils]
index-servers =
    pypi
    testpypi

[pypi]
username = __token__
password = pypi-your-api-token-here

[testpypi]
repository = https://test.pypi.org/legacy/
username = __token__
password = pypi-your-test-token-here
EOF

chmod 600 ~/.pypirc
```

## 🧪 Test Publishing Process

### 1. Build Package

```bash
# Clean previous builds
rm -rf dist/ build/ *.egg-info/

# Build wheel and source distribution
python -m build

# Verify package
ls dist/
# Should show: lifelog-0.1.0-py3-none-any.whl and lifelog-0.1.0.tar.gz
```

### 2. Test Upload to Test PyPI

```bash
# Upload to test PyPI first
python -m twine upload --repository testpypi dist/*

# Test installation from Test PyPI
pip install --index-url https://test.pypi.org/simple/ lifelog
llog --help
```

### 3. If Test Successful, Upload to Production

```bash
# Upload to production PyPI
python -m twine upload dist/*

# Now users can install with:
pip install lifelog
```

## 🤖 Automated PyPI Publishing

### GitHub Actions Workflow

Create `.github/workflows/publish-pypi.yml`:

```yaml
name: Publish to PyPI

on:
  release:
    types: [published]

jobs:
  deploy:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install build twine

      - name: Build package
        run: python -m build

      - name: Publish to Test PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          password: ${{ secrets.TEST_PYPI_API_TOKEN }}
          repository_url: https://test.pypi.org/legacy/

      - name: Publish to PyPI
        if: startsWith(github.ref, 'refs/tags')
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          password: ${{ secrets.PYPI_API_TOKEN }}
```

### GitHub Secrets Setup

In your repository settings → Secrets and variables → Actions:

- `PYPI_API_TOKEN`: Your PyPI production token
- `TEST_PYPI_API_TOKEN`: Your Test PyPI token

## 📋 PyPI Package Requirements

### Update pyproject.toml

Make sure your `pyproject.toml` includes:

```toml
[project]
name = "lifelog"
version = "0.1.0"
description = "A terminal-based health, habit, task, life tracker."
authors = [{name = "Zach McKinnon", email = "your-email@example.com"}]
readme = "README.md"
license = "MIT"
requires-python = ">=3.9"
keywords = ["productivity", "cli", "time-tracking", "habits", "raspberry-pi"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: End Users/Desktop",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.9",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Topic :: Office/Business :: Scheduling",
    "Topic :: Utilities",
]

[project.urls]
Homepage = "https://github.com/zach-mckinnon/lifelog"
Repository = "https://github.com/zach-mckinnon/lifelog.git"
Issues = "https://github.com/zach-mckinnon/lifelog/issues"
Changelog = "https://github.com/zach-mckinnon/lifelog/releases"

[project.scripts]
llog = "lifelog.llog:lifelog_app"
```

## 🚀 Publishing Workflow

### Manual Release Process

```bash
# 1. Update version in pyproject.toml
# 2. Create git tag
git tag v0.1.0
git push origin v0.1.0

# 3. Build and test
python -m build
python -m twine upload --repository testpypi dist/*

# 4. Test installation
pip install --index-url https://test.pypi.org/simple/ lifelog

# 5. If good, publish to production
python -m twine upload dist/*
```

### Automated Release Process

1. Create GitHub release (triggers workflow)
2. Workflow automatically publishes to PyPI
3. Users can immediately `pip install lifelog`

## ✅ Benefits of PyPI Publishing

### For Users:

```bash
# Instead of:
pip install https://github.com/zach-mckinnon/lifelog/releases/download/v0.1.0/lifelog-0.1.0-py3-none-any.whl

# Just:
pip install lifelog
```

### For Package Managers:

- Homebrew can reference PyPI
- System package managers can build from PyPI
- Docker images can install directly
- CI/CD systems can easily include it

## 🔒 Security Considerations

### API Token Security:

- Store tokens as GitHub secrets, never in code
- Use scoped tokens (project-specific when possible)
- Rotate tokens regularly
- Enable 2FA on PyPI account

### Package Integrity:

- Always build locally and verify contents
- Test on Test PyPI before production
- Monitor download stats for unusual activity
- Keep build environment clean

## 📈 Once Published

### Monitor Your Package:

- **PyPI Statistics**: https://pypistats.org/packages/lifelog
- **Downloads**: Track adoption
- **Issues**: Monitor GitHub for user feedback
- **Security**: Watch for vulnerability reports

### Update Process:

1. Increment version in `pyproject.toml`
2. Create git tag and GitHub release
3. Automated workflow publishes to PyPI
4. Users get updates with `pip install --upgrade lifelog`

---

**Once on PyPI, your app becomes as easy to install as any major Python package! 🎉**
