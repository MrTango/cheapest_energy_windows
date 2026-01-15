# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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


## [1.0.0] - 2025-01-01

### Added

- Initial release
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
