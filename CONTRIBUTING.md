# Contributing to Binsai

Thank you for your interest in contributing to Binsai! This document provides guidelines for contributing to the project.

## Development Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/codewithpatelo/binsai.git
   cd binsai
   ```

2. Install Poetry (if not already installed):
   ```bash
   pip install poetry
   ```

3. Install dependencies:
   ```bash
   poetry install
   ```

4. Run tests:
   ```bash
   poetry run pytest
   ```

## Code Style

- Use [Black](https://black.readthedocs.io/) for code formatting
- Use [isort](https://pycqa.github.io/isort/) for import sorting
- Follow [PEP 8](https://pep8.org/) style guidelines
- Add type hints to all public APIs

## Pre-commit Hooks

We use pre-commit hooks to ensure code quality:

```bash
poetry run pre-commit install
```

## Testing

- Write tests for all new functionality
- Maintain test coverage above 80%
- Use pytest for testing

## Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests and linting
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## Commit Messages

Use conventional commits format:
- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `test:` Test changes
- `refactor:` Code refactoring
- `chore:` Build/dependency changes

## Questions?

Join our [Discord](https://discord.gg/binsai) or open a [GitHub Discussion](https://github.com/codewithpatelo/binsai/discussions).

## Code of Conduct

Please read our [Code of Conduct](CODE_OF_CONDUCT.md) before contributing.
