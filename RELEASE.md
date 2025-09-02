# 🚀 Creating Releases for Testing

## Quick Release Process

### Option 1: Automated with GitHub Actions
1. **Tag a version**: `git tag v0.1.0`
2. **Push the tag**: `git push origin v0.1.0`
3. **GitHub Actions automatically creates the release** with built packages

### Option 2: Manual Release Creation
```bash
# 1. Build packages
python -m build

# 2. Create release using script
python scripts/create-release.py

# 3. Or manually upload to GitHub
# Go to https://github.com/yourusername/lifelog/releases/new
```

## 📦 For Testers - Easy Installation

Once the release is created, testers can install with:

### Method 1: Download and Install
```bash
# 1. Go to: https://github.com/yourusername/lifelog/releases
# 2. Download: lifelog-0.1.0-py3-none-any.whl
# 3. Install:
pip install lifelog-0.1.0-py3-none-any.whl
llog setup
```

### Method 2: Direct URL Install (if release assets are public)
```bash
pip install https://github.com/yourusername/lifelog/releases/download/v0.1.0/lifelog-0.1.0-py3-none-any.whl
llog setup
```

## 🛠️ Release Checklist

### Pre-Release
- [ ] All tests passing
- [ ] Version updated in `pyproject.toml`
- [ ] `CHANGELOG.md` updated (if you have one)
- [ ] Documentation updated
- [ ] Build packages: `python -m build`
- [ ] Test local install: `pip install dist/*.whl`

### Create Release
- [ ] Tag version: `git tag v0.1.0`
- [ ] Push tag: `git push origin v0.1.0`
- [ ] Create GitHub release (manual or automated)
- [ ] Upload wheel and tarball files
- [ ] Add release notes

### Post-Release
- [ ] Test installation from release
- [ ] Update installation instructions
- [ ] Announce to testers
- [ ] Monitor for feedback/issues

## 📋 Release Assets

Each release should include:
- **`lifelog-X.X.X-py3-none-any.whl`** - Universal wheel (recommended)
- **`lifelog-X.X.X.tar.gz`** - Source distribution (fallback)
- **Release notes** with installation instructions

## 🎯 Tester Instructions Template

```markdown
# 🧪 Testing Lifelog v0.1.0

## Quick Install
pip install lifelog-0.1.0-py3-none-any.whl
llog setup

## What to Test
1. **Installation**: Does `pip install` work smoothly?
2. **Setup**: Does `llog setup` complete without errors?
3. **Basic Commands**: Try `llog --help`, `llog time start "test"`
4. **Performance**: How does it feel on your system?
5. **Pi Testing**: If you have a Raspberry Pi, test there too!

## Feedback
- Report issues at: https://github.com/yourusername/lifelog/issues
- Share experiences in: https://github.com/yourusername/lifelog/discussions
```

## 🔄 Version Bumping

```bash
# Update version in pyproject.toml
# Then rebuild and release

# Example version progression:
# 0.1.0 -> 0.1.1 (bug fixes)
# 0.1.1 -> 0.2.0 (new features)
# 0.2.0 -> 1.0.0 (stable release)
```