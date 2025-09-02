# Contributing to Lifelog

Thank you for your interest in contributing to Lifelog! This document provides comprehensive guidelines for contributing to the project.

## 🚀 Getting Started

### Prerequisites

- Python 3.9+
- Git
- Basic understanding of CLI applications and SQLite

### Development Setup

```bash
# Fork and clone the repository
git clone https://github.com/zach-mckinnon/lifelog.git
cd lifelog

# Create development environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# Install in development mode
pip install -e .

# Run initial setup
llog setup

# Test your installation
llog --help
```

## 🛠️ Development Workflow

### 1. Create a Feature Branch

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/bug-description
```

### 2. Make Your Changes

- Follow existing code style and patterns
- Add tests for new functionality (when possible)
- Update documentation if needed
- Test on multiple platforms if possible

### 3. Test Your Changes

```bash
# Test basic functionality
llog setup
llog time start "test"
llog task add "test task" --cat work
llog time stop
llog report summary

# Test Pi compatibility (if available)
# Run on resource-constrained environment
```

### 4. Commit Your Changes

```bash
git add .
git commit -m "Description of your changes"
```

## 📋 Contribution Guidelines

### Code Style

- Follow existing patterns in the codebase
- Use clear, descriptive variable and function names
- Add docstrings for new functions and classes
- Keep functions focused and single-purpose

### Architecture Patterns

- **Repository Pattern**: Database access through `*_repository.py` files
- **Configuration**: Use `config_manager.py` for settings
- **CLI Commands**: Add new commands in `commands/` directory
- **Error Handling**: Use the error handling decorators in `utils/error_handler.py`

### Database Changes

If you need to modify the database:

1. Update schema in `database_manager.py:initialize_schema()`
2. Add/update dataclass in `models.py`
3. Update repository methods
4. Ensure sync compatibility with `uid` and `updated_at` fields

### Security Requirements

- No hardcoded passwords, tokens, or secrets
- No personal file paths or system-specific code
- All new dependencies must be justified and minimal
- No breaking changes without migration path
- Security implications must be considered and documented

### Testing Guidelines

While we don't have formal tests, please verify:

- Installation works: `pip install -e .`
- Setup completes: `llog setup`
- Core commands function: time tracking, tasks, reports
- Cross-platform compatibility
- Performance on resource-constrained devices

## 🎯 Areas for Contribution

### High Priority

- **Export Functionality**: CSV/JSON data export
- **Mobile Sync Client**: Basic mobile app for data sync
- **Goal System Enhancements**: Milestones and progress tracking
- **Custom Report Builder**: User-defined analytics

### Medium Priority

- **Plugin System**: Custom hooks and extensions
- **Data Visualization**: Additional chart types and formats
- **Import Tools**: Migration from other productivity apps
- **Performance Optimizations**: Further database and memory improvements

### Documentation

- **User Guides**: Tutorials and use cases
- **API Documentation**: Document sync API endpoints
- **Deployment Guides**: Docker, systemd service setup
- **Architecture Documentation**: System design and patterns

## 🐛 Bug Reports

When reporting bugs, please include:

- **Environment**: OS, Python version, hardware (especially Pi)
- **Steps to Reproduce**: Clear, step-by-step instructions
- **Expected vs Actual**: What should happen vs what happens
- **Logs**: Any error messages or relevant output
- **Configuration**: Relevant settings from `~/.lifelog/config.toml`

## 💡 Feature Requests

For new features:

- **Use Case**: Describe the problem this solves
- **Proposed Solution**: How should it work?
- **Alternatives**: Other ways to solve the problem
- **Implementation Ideas**: Technical approach (optional)

## 🤝 Community Guidelines

- **Be Respectful**: This project serves the neurodivergent community
- **Be Patient**: Contributors work on this in their free time
- **Be Constructive**: Provide actionable feedback and suggestions
- **Ask Questions**: Don't hesitate to ask for clarification

## 🏷️ Pull Request Process

1. **Fork** the repository
2. **Create** a feature branch from `public`
3. **Make** your changes with clear commits
4. **Test** your changes thoroughly
5. **Submit** a pull request with:
   - Clear description of changes
   - Why the change is needed
   - How to test the changes
   - Any breaking changes or migration steps

### PR Review Criteria

- Code follows existing patterns
- Functionality works as described
- No obvious performance regressions
- Documentation updated if needed
- Commit messages are clear
- Security requirements met

## 🔒 Security Guidelines

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

## 🚀 Repository Management (For Maintainers)

### Branch Strategy

- `main` - Stable development branch (maintainer access)
- `public` - Public collaboration branch (open PRs)
- `release/*` - Release preparation branches
- Feature branches from `public`

### Workflow

1. Contributors fork and create branches from `public`
2. Submit PRs to `public` branch
3. Maintainers review and merge to `public`
4. Periodic merges from `public` to `main`
5. Releases cut from `main`

### GitHub Repository Setup

When setting up for public collaboration:

#### Settings Configuration

- **Default Branch**: Set `public` as default
- **Branch Protection**: Enable for `main` and `public`
  - Require PR reviews
  - Dismiss stale reviews
  - Require status checks
- **Security**: Enable all scanning features
- **Issues**: Enable with templates
- **Discussions**: Enable for community Q&A

#### Required Files

- ✅ Issue and PR templates
- ✅ CODEOWNERS file
- ✅ Security workflows
- ✅ Code of conduct
- ✅ Comprehensive documentation

## 📞 Getting Help

- **GitHub Discussions**: Ask questions and share ideas
- **GitHub Issues**: Report bugs and request features
- **Code Review**: Request feedback on your contributions
- **Security Issues**: Use private security advisory for vulnerabilities

## 🙏 Recognition

All contributors are recognized in our README and release notes. We value every contribution, from code to documentation to bug reports.

## 📋 First-Time Contributors

New to open source? Welcome! Here are some beginner-friendly ways to contribute:

### Good First Issues

Look for issues labeled `good first issue`:

- Documentation improvements
- Testing on different platforms
- Small bug fixes
- UI/UX enhancements

### Learning Resources

- [GitHub Flow Guide](https://guides.github.com/introduction/flow/)
- [First Contributions](https://github.com/firstcontributions/first-contributions)
- [How to Contribute to Open Source](https://opensource.guide/how-to-contribute/)

### What to Expect

- **Friendly community**: We're here to help you succeed
- **Learning opportunity**: Gain experience with real-world Python development
- **Recognition**: Your contributions matter and will be acknowledged
- **Growth**: Build your portfolio and programming skills

---

#### **Built with ❤️ for the neurodivergent community**

Thank you for helping make Lifelog better for everyone!
