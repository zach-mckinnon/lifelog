# Contributing to Lifelog

Thank you for your interest in contributing to Lifelog! This document provides guidelines for contributing to the project.

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
2. **Create** a feature branch
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

## 🚀 Release Process

Releases are managed by maintainers:

1. Version bumping in `pyproject.toml`
2. Building packages: `python -m build`
3. Creating GitHub releases with built packages
4. Updating installation documentation

## 📞 Getting Help

- **GitHub Discussions**: Ask questions and share ideas
- **GitHub Issues**: Report bugs and request features
- **Code Review**: Request feedback on your contributions

## 🙏 Recognition

All contributors are recognized in our README and release notes. We value every contribution, from code to documentation to bug reports.

---

**Built with ❤️ for the neurodivergent community**
