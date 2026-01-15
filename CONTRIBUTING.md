# Contributing to Cheapest Energy Windows NG

Thank you for your interest in contributing to Cheapest Energy Windows NG!

## Getting Started

1. Fork the repository
2. Clone your fork locally
3. Create a feature branch from `main`
4. Make your changes
5. Test your changes with Home Assistant
6. Submit a pull request

## Development Setup

1. Copy `custom_components/cheapest_energy_windows_ng` to your Home Assistant `custom_components` directory
2. Restart Home Assistant
3. Enable debug logging if needed:
   ```yaml
   logger:
     default: info
     logs:
       custom_components.cheapest_energy_windows_ng: debug
   ```

## Code Style

- Follow PEP 8 guidelines for Python code
- Use type hints where possible
- Add docstrings to functions and classes
- Keep functions focused and concise

## Pull Request Guidelines

- Create a descriptive PR title
- Reference any related issues
- Update documentation if needed
- Add entries to CHANGELOG.md under `[Unreleased]`

## Releasing

This project uses an automated GitHub Actions workflow for releases.

### Before Releasing

1. Ensure all changes are merged to `main`
2. Update `CHANGELOG.md`:
   - Move items from `[Unreleased]` to a new version section
   - Follow the format: `## [X.Y.Z] - YYYY-MM-DD`
   - Categorize changes: Added, Changed, Fixed, Removed

### Creating a Release

1. Go to **Actions** → **Release** workflow on GitHub
2. Click **Run workflow**
3. Enter the version number (e.g., `2.1.0`)
   - Must follow semantic versioning: `MAJOR.MINOR.PATCH`
4. Optionally enter release notes (leave empty to use CHANGELOG)
5. Click **Run workflow**

### What the Release Workflow Does

The workflow automatically:
1. Validates the version format
2. Updates version in `manifest.json`
3. Updates version in `const.py`
4. Commits the version bump to `main`
5. Creates and pushes a git tag (`vX.Y.Z`)
6. Creates a GitHub release with changelog notes

### After Releasing

- HACS will automatically pick up the new release
- Users can update through HACS or manually

## Versioning

This project follows [Semantic Versioning](https://semver.org/):

- **MAJOR**: Breaking changes or major new features
- **MINOR**: New features, backward compatible
- **PATCH**: Bug fixes, backward compatible

## Questions?

Open an issue on GitHub if you have questions or need help.
