# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.0.3] - 2025-01-16

### Fixed

- Skip brands check in HACS validation workflow

### Documentation

- Added comprehensive documentation for Forecast.Solar integration
- Documented supported solar sensors and required attributes (`wh_period`, `wh_today_remaining`, `watts`)
- Added setup instructions for solar optimization feature
- Documented solar-related sensor attributes (`solar_optimization_active`, `solar_forecast_total_wh`, `net_import_wh`)

## [2.0.2] - 2025-01-15

### Changed

- **BREAKING**: Renamed integration domain from `cheapest_energy_windows_tibber` to `cheapest_energy_windows_ng`
- **BREAKING**: Renamed folder from `custom_components/cheapest_energy_windows` to `custom_components/cheapest_energy_windows_ng`
- Updated all service calls to use new domain name
- Updated documentation and workflow files with new paths

### Migration

Users upgrading from 2.0.1 or earlier need to:
1. Remove the old integration from Home Assistant
2. Delete the old `custom_components/cheapest_energy_windows` folder
3. Install the new version
4. Re-add the integration through Settings > Devices & Services

## [2.0.1] - 2025-01-15

### Changed

- Renamed project to "Cheapest Energy Windows NG"
- Updated GitHub repository links to MrTango/cheapest_energy_windows
- Updated codeowners to @MrTango

### Added

- Automated release workflow via GitHub Actions
- CHANGELOG.md for version history
- CONTRIBUTING.md with development and release documentation

## [2.0.0] - 2025-01-11

### Added

- Tibber integration support for real-time electricity prices
- Solar forecast integration using Forecast.Solar sensor
- Solar optimization toggle switch
- Configuration options for:
  - Battery usable capacity
  - Consumption estimate
  - Skip charge solar threshold
- Solar forecast helper methods to calculation engine
- Charge window optimization considering solar forecast
- Discharge window optimization around solar gaps
- Net import calculation
- Solar forecast attributes to today/tomorrow sensors

### Changed

- Calculation engine now considers solar production when planning charge/discharge windows

### Fixed

- Pass solar forecast data correctly to calculation engine
- Unknown action error for rotate_tomorrow_settings service
- Continue on error in notifications

## [1.0.0] - 2025-01-01

### Added

- Initial release of Cheapest Energy Windows NG fork
- Tibber price integration
- Battery charge/discharge window calculation
- Cheapest and most expensive time window detection
- Tomorrow settings with automatic rotation
- Price override functionality
- Time override functionality
- Base usage strategies
- Configurable VAT, tax, and additional costs
- Notification system with quiet hours
- HACS compatibility
