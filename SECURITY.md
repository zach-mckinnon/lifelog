# 🔒 Codebase Protection & Security Guidelines

## 🛡️ Branch Protection Setup

### GitHub Repository Settings

#### 1. Branch Protection Rules
```
Settings → Branches → Add Rule

Protected branches:
- main (production)
- public (collaboration)

Rules to enable:
✅ Require a pull request before merging
✅ Require approvals: 1 (minimum)
✅ Dismiss stale PR reviews when new commits are pushed
✅ Require review from code owners
✅ Restrict pushes that create files to admin only
✅ Require status checks to pass before merging
✅ Require branches to be up to date before merging
✅ Include administrators (applies rules to admins too)
```

#### 2. Required Status Checks
Set up these automated checks:
- **Build Test**: Ensures `python -m build` succeeds
- **Installation Test**: Verifies `pip install -e .` works
- **Basic Functionality**: Tests core commands work
- **Security Scan**: Dependency vulnerability checks

### 3. Repository Security Settings
```
Settings → Security & Analysis:

✅ Dependency graph
✅ Dependabot alerts
✅ Dependabot security updates
✅ Code scanning alerts
✅ Secret scanning alerts
✅ Push protection (blocks secret commits)
```

## 🔍 Automated Security Checks

### GitHub Actions Security Workflow
Create `.github/workflows/security.yml`:

```yaml
name: Security Checks

on:
  pull_request:
    branches: [ main, public ]
  push:
    branches: [ main, public ]

jobs:
  security:
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
        pip install safety bandit semgrep
        
    - name: Check for known vulnerabilities
      run: safety check --json
      
    - name: Run security linter
      run: bandit -r lifelog/ -f json
      
    - name: Verify no secrets in code
      run: |
        ! grep -r "password\|token\|secret\|key" --include="*.py" lifelog/ || exit 1
```

## 👥 Code Review Requirements

### CODEOWNERS File
Create `.github/CODEOWNERS`:
```
# Global ownership
* @yourusername

# Core system files require extra review
lifelog/utils/db/ @yourusername @trusted-contributor
lifelog/api/ @yourusername @trusted-contributor
pyproject.toml @yourusername
CLAUDE.md @yourusername

# Documentation can have lighter review
*.md @yourusername @doc-maintainer
```

### Review Checklist for Contributors
Add to `CONTRIBUTING.md`:

#### Before Submitting PR:
- [ ] No hardcoded passwords, tokens, or secrets
- [ ] No personal file paths or system-specific code
- [ ] All new dependencies justified and minimal
- [ ] No breaking changes without migration path
- [ ] Code follows existing patterns
- [ ] Security implications considered

#### For Reviewers:
- [ ] Code quality and style consistency
- [ ] Security implications reviewed
- [ ] No secrets or credentials exposed
- [ ] Dependencies are appropriate
- [ ] Breaking changes properly documented
- [ ] Installation and basic functionality tested

## 🚨 Security Guidelines for Contributors

### What to Avoid
❌ **Never commit:**
- Passwords, API keys, tokens
- Personal file paths (`/Users/john/...`)
- Database files or backups
- Private configuration files
- Hardcoded credentials of any kind

❌ **Code patterns to avoid:**
- `eval()`, `exec()`, or similar dynamic execution
- Unsafe file operations without validation
- Network operations without timeout/validation
- SQL injection vulnerabilities
- Path traversal vulnerabilities

### Safe Coding Practices
✅ **Always do:**
- Use configuration files for settings
- Validate all user inputs
- Use parameterized database queries
- Set appropriate file permissions
- Handle errors gracefully
- Use secure defaults

✅ **Database security:**
- Use SQLite with proper permissions
- Parameterized queries only
- No dynamic SQL construction
- Proper connection handling

## 🔧 Dependency Security

### Approved Dependencies
Core dependencies are vetted and approved:
- `typer`, `rich` - CLI framework
- `flask` - API server
- `sqlite3` - Database (built-in)
- `tomlkit` - Configuration
- `pendulum` - Date/time handling
- `psutil` - System monitoring

### Adding New Dependencies
Before adding new dependencies:
1. Check if really necessary
2. Verify it's actively maintained
3. Check for known vulnerabilities
4. Consider bundle size impact (Pi compatibility)
5. Get approval from maintainers

### Dependency Updates
- Dependabot handles security updates automatically
- Major version updates require review
- Test on Pi hardware before merging

## 🏗️ Development Environment Security

### Local Development
```bash
# Use virtual environments
python -m venv venv
source venv/bin/activate

# Install in development mode
pip install -e .

# Never commit .env files or local configs
echo ".env" >> .gitignore
echo "local_config.toml" >> .gitignore
```

### Testing Security
```bash
# Check for secrets before committing
grep -r "password\|token\|secret" --include="*.py" lifelog/

# Run security checks
bandit -r lifelog/
safety check

# Test with minimal permissions
chmod 600 ~/.lifelog/lifelog.db
```

## 🎯 Incident Response

### If Security Issue Found
1. **Don't** discuss publicly in issues
2. **Do** email maintainer directly
3. **Include** steps to reproduce
4. **Wait** for acknowledgment before disclosure

### For Maintainers
1. Acknowledge within 48 hours
2. Assess severity and impact
3. Develop fix privately
4. Coordinate disclosure timeline
5. Release security update
6. Publish security advisory

## 📋 Security Checklist for Releases

Before each release:
- [ ] Run security scanners (bandit, safety)
- [ ] Review dependency updates
- [ ] Check for hardcoded secrets
- [ ] Verify file permissions in package
- [ ] Test installation in clean environment
- [ ] Update security documentation if needed

## 🤝 Trusted Contributor Program

### Requirements to become trusted contributor:
- Multiple successful PRs merged
- Understanding of codebase architecture
- Demonstrated security awareness
- Active community participation
- Maintainer nomination

### Trusted contributor privileges:
- Can approve certain PRs
- Access to pre-release testing
- Input on security decisions
- Faster review process

## 📞 Security Contacts

- **Security issues**: [Create private security advisory]
- **General security questions**: Use GitHub Discussions
- **Urgent security concerns**: Contact maintainer directly

---

**Security is everyone's responsibility. When in doubt, ask!**