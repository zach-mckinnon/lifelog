# Contributing to Lifelog

Thank you for your interest in contributing to Lifelog!

We welcome code, documentation, design, and community contributions. To protect the project's integrity and ensure it remains open source, **all contributors must agree to the terms below** before submitting code or documentation.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How to Contribute](#how-to-contribute)
- [Contributor License Agreement (CLA)](#contributor-license-agreement-cla)
- [Coding Guidelines](#coding-guidelines)
- [Pull Requests](#pull-requests)
- [Licensing](#licensing)
- [Reporting Bugs / Requesting Features](#reporting-bugs--requesting-features)
- [Contact](#contact)

---

## Code of Conduct

Be respectful, helpful, and open. Harassment, abuse, or discrimination of any kind will not be tolerated. See [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md) for more.

---

## How to Contribute

1. **Fork** the repo and clone your fork.
2. **Create a new branch** for each feature or fix.
3. **Write clear, documented code**.
4. **Test** your changes on Linux and Windows if possible.
5. **Sign the Contributor License Agreement (CLA)** – see below.
6. **Open a pull request** (PR) to the `main` branch.  
   - Link to related issues, if any.
   - Clearly describe what your PR does.
7. Participate in code review and address feedback.

---

## Contributor License Agreement (CLA)

To ensure Lifelog remains open source and to protect the project from proprietary forks, **all contributors must sign a CLA**. By submitting a contribution, you agree:

- Your contribution is licensed under the [GNU GPL v3](./LICENSE).
- You have the right to submit the code/documentation.
- You will not pursue patent claims against users or contributors for using Lifelog.
- You agree your contribution will not be re-licensed under a non-open-source license.

**To sign the CLA:**

- Submit a PR including your name and email in the `CONTRIBUTORS.md` file, with the line:  
    I agree to the Contributor License Agreement in CONTRIBUTING.md – [Your Name] <your@email.com>

- Or, sign using any system provided in the repository (e.g., GitHub CLA bot, if enabled).

If you have questions, open an issue or email the project maintainer.

---

## Coding Guidelines

- **Language**: Python 3.8+ (3.9+ for full path imports)
- **Style**: Follow [PEP8](https://pep8.org/), and keep code modular and documented.
- **Imports**: Always use full paths starting with `lifelog.` for internal modules.
- **Type Annotations**: Use type hints where practical.
- **Tests**: Add/maintain tests for your code, especially for critical logic.
- **Cross-platform**: Ensure changes work on both Linux and Windows (test with/without Windows-specific dependencies).

---

## Pull Requests

- **One logical change per PR.**
- Include **clear commit messages**.
- Reference any issues closed by your PR.
- Describe how to test the change.
- Make sure CI checks (if present) pass.

---

## Licensing

By contributing, you agree that your contributions are licensed under the **GNU General Public License, Version 3** (GPLv3) or any later version, as specified in the [LICENSE](./LICENSE) file.

---

## Reporting Bugs / Requesting Features

- **Bugs:**  
Open an issue and include OS, Python version, steps to reproduce, and logs if relevant.

- **Features:**  
Open an issue describing your feature and why it benefits users.

---

## Contact

Questions?  

- Open an issue  
- Or contact the maintainer: [Your Name] (<your@email.com>)

Thank you for contributing to Lifelog!
