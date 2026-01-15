# Cheapest Energy Windows NG for Home Assistant

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=MrTango&repository=cheapest_energy_windows&category=integration)
[![GitHub Release](https://img.shields.io/github/release/MrTango/cheapest_energy_windows.svg)](https://github.com/MrTango/cheapest_energy_windows/releases)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Optimize your energy consumption and battery storage by automatically identifying the cheapest charging windows and most expensive discharging periods based on dynamic electricity prices from Nord Pool or ENTSO-E.

## 🌟 Why Cheapest Energy Windows NG?

Unlike other energy management solutions, this integration provides:

1. **True Automation** - Not just sensors, but a complete automated control system
2. **No Code Required** - Link your battery control through the UI, no YAML editing
3. **Self-Maintaining** - Automation updates itself, survives restarts, and self-heals
4. **Universal Compatibility** - Works with any battery system that has Home Assistant control
5. **Multi-Source Support** - Nord Pool and ENTSO-E sensors supported with automatic normalization
6. **Professional Features** - SOC safety, quiet hours, price overrides, time scheduling
7. **Beautiful Dashboard** - Comprehensive control interface included

This is not just another energy monitor - it's a complete battery management system that runs itself.

## Table of Contents

- [Dashboard Preview](#dashboard-preview)
- [Supported Price Sensors](#supported-price-sensors)
- [Features](#features)
- [Installation](#installation)
  - [HACS Installation](#hacs-installation-recommended)
  - [Manual Installation](#manual-installation)
- [Configuration](#configuration)
  - [Initial Setup](#initial-setup)
- [Dashboard Installation](#dashboard-installation)
  - [Getting the Dashboard File](#getting-the-dashboard-file)
  - [Installation Steps](#installation-steps)
  - [Required Frontend Components](#required-frontend-components)
- [How It Works](#how-it-works)
  - [Window Selection Algorithm](#window-selection-algorithm)
  - [Entities Created](#entities-created)
- [Services](#services)
- [Automation System](#automation-system)
  - [How Automations Work](#how-automations-work)
  - [Initial Setup: Notification-Only Mode](#initial-setup-notification-only-mode)
  - [Adding Battery Control Actions](#adding-battery-control-actions)
- [Solar Forecast Optimization](#solar-forecast-optimization)
  - [How It Works](#how-solar-optimization-works)
  - [Configuration](#solar-configuration)
  - [Supported Sensors](#supported-solar-sensors)
- [Sensor Attributes](#sensor-attributes)
- [Dashboard Features](#dashboard-features)
- [Troubleshooting](#troubleshooting)
- [Performance](#performance)
- [Contributing](#contributing)
- [License](#license)
- [Support](#support)

## Dashboard Preview

![Cheapest Energy Windows NG Dashboard](CEW-Dashboard.jpg?v=2)

> **✨ NEW: Automated Dashboard Installation Available!**
> The dashboard is now available as a **separate HACS package** that automatically updates!
> Install it from: [Cheapest Energy Windows NG Dashboard](https://github.com/MrTango/cheapest_energy_windows_dashboard)
> See the [Dashboard Installation](#dashboard-installation) section below for details.

## Supported Price Sensors

This integration works with dynamic electricity pricing from multiple sources:

### Supported Integrations
- **[Nord Pool](https://github.com/custom-components/nordpool)** - Hourly electricity prices for Nordic and Baltic countries
- **[ENTSO-E Transparency Platform](https://github.com/JaccoR/hass-entso-e)** - European electricity market data with 15-minute intervals
- **[Tibber](https://www.tibber.com/)** - Real-time electricity prices and smart home integration

### Important Requirements
- **15-minute interval data required** - Even if you have an hourly pricing contract, the integration needs 15-minute price data for optimal calculations
- **Automatic aggregation** - The system automatically aggregates 15-minute data into hourly windows when configured for 1-hour intervals
- **EUR/kWh units only** - Price sensors must provide prices in EUR/kWh (not cents)
- **Tibber Support** - This fork includes support for Tibber's real-time pricing and smart home features

### Time Granularity Options
- **15-minute windows** (96 windows per day) - For contracts with 15-minute pricing intervals
- **1-hour windows** (24 windows per day) - For contracts with hourly pricing intervals

The integration automatically normalizes different sensor formats through a proxy sensor, ensuring compatibility with both Nord Pool and ENTSO-E data structures.

## Features

### 🎯 Key Highlights

- **🔋 Zero-Configuration Battery Control**: Automatically creates and manages battery automation - just link your existing battery scripts/automations
- **🔗 Battery Operations Linking**: Connect any automation, script, or scene to battery states directly from the dashboard
- **🤖 Auto-Managed Automation**: The integration creates, updates, and maintains the battery control automation automatically (even survives restarts and upgrades)
- **📱 Smart Notifications**: Configurable notifications for all state changes with quiet hours support
- **🛡️ SOC Safety Protection**: Automatic battery protection based on State of Charge limits
- **💰 Price Override**: Automatically charge when prices drop below threshold, regardless of calculated windows
- **☀️ Solar Forecast Optimization**: Skip grid charging when solar production will fill your battery; prioritize discharge during solar gaps

### Core Features

- **Multi-Vendor Support**: Works with Nord Pool and ENTSO-E price sensors
- **Flexible Window Duration**: Choose between 15-minute or 1-hour intervals
- **Smart Window Detection**: Automatically identifies optimal charge/discharge windows
- **Percentile-Based Selection**: Uses statistical analysis to find truly cheap/expensive periods
- **Progressive Window Selection**: Ensures spread requirements are met for profitability
- **Dual-Day Management**: Configure different settings for today and tomorrow
- **Time Overrides**: Force specific battery modes during set time periods (idle, charge, discharge, aggressive discharge, off)
- **Comprehensive Dashboard**: Full control interface with real-time status and analytics

## Installation

### HACS Installation (Recommended)

> ✨ Click the badge at the top for one-click HACS installation, or follow these steps:

1. Open HACS in your Home Assistant instance
2. Click on "Integrations"
3. Search for "Cheapest Energy Windows NG"
4. Click "Download"
5. Restart Home Assistant
6. Go to Settings > Devices & Services > "Add Integration"
7. Search for "Cheapest Energy Windows NG"
8. Follow the configuration wizard

### Manual Installation

1. Copy the `custom_components/cheapest_energy_windows_ng` folder to your Home Assistant `custom_components` directory
2. Restart Home Assistant
3. Go to Settings > Devices & Services
4. Click "Add Integration"
5. Search for "Cheapest Energy Windows NG"
6. Follow the configuration wizard

### Docker Configuration Note

If running Home Assistant in Docker and using ENTSO-E sensors:
- Ensure your container has the `TZ` environment variable set (e.g., `TZ=Europe/Amsterdam`)
- Nord Pool works without this setting, but ENTSO-E requires proper timezone configuration
- Without this, ENTSO-E timestamps may show UTC (+00:00) instead of local timezone

## Configuration

### Initial Setup

During the configuration flow, you'll be asked to:

1. **Select your price sensor**: The integration will auto-discover Nord Pool and ENTSO-E price sensors in your Home Assistant instance

2. **Link Battery Operations** (optional):
   - Select existing automations, scripts, or scenes for each battery mode
   - The integration will automatically trigger these when entering each state
   - Can be configured later from the dashboard

3. **Choose window duration**:
   - **15 minutes** (96 windows per day) - Recommended if your energy contract supports quarter-hourly trading/settlement
   - **1 hour** (24 windows per day) - Simpler management, suitable for hourly contracts

   > **Tip**: Most Nord Pool data includes 15-minute granularity. Choose 15-minute windows for maximum optimization flexibility, or 1-hour windows for simpler scheduling.

4. **Configure pricing parameters**:
   - VAT percentage
   - Additional tax (€/kWh)
   - Fixed additional costs (€/kWh)

5. **Battery settings** (optional):
   - Charge power (Watts)
   - Discharge power (Watts)
   - Round-trip efficiency (%)

You can change the window duration anytime after setup using the `Pricing Window Duration` selector in the dashboard or entity settings.

### What Happens During Setup

1. **Guided Configuration Wizard** walks you through all settings
2. **Automatic Automation Creation** - A complete battery control automation is created
3. **Battery Operations Linking** - Optionally link your existing battery control
4. **Dashboard Ready** - All entities created and ready for the dashboard
5. **Notifications Configured** - Ready to alert you about state changes

## Dashboard Installation

The integration includes a comprehensive pre-built dashboard for monitoring and controlling all features. The dashboard is distributed as a **separate HACS package** that automatically updates whenever improvements are made.

### Installation Steps

1. **Install the Dashboard Package**:
   - Open HACS in Home Assistant
   - Go to **Frontend** section
   - Click the 3 dots menu (top right) → **"Custom repositories"**
   - Add repository: `https://github.com/MrTango/cheapest_energy_windows_dashboard`
   - Select category: **"Dashboard"**
   - Click **"Add"** then find it in the list and click **"Download"**

2. **Create the Dashboard**:
   - Go to **Settings → Dashboards**
   - Click **"+ Add Dashboard"** (bottom right)
   - Fill in title (e.g., "Energy Windows"), icon, and URL
   - Toggle **"Show in sidebar"** ON and click **"Create"**
   - Click **⋮ menu** → **"Edit Dashboard"**
   - Click **⋮ menu** again → **"Raw configuration editor"**
   - Replace all content with:
   ```yaml
   strategy:
     type: custom:dashboard-cheapest-energy-windows
   views: []
   ```
   - Click **"Save"**

**Benefits**: Automatic updates via HACS, no manual copying, always up-to-date with the latest improvements!

### Required Frontend Components

The dashboard requires the following custom cards to be installed via HACS:

1. **[Mushroom Cards](https://github.com/piitaya/lovelace-mushroom)** - Modern card designs
2. **[Fold Entity Row](https://github.com/thomasloven/lovelace-fold-entity-row)** - Collapsible entity rows
3. **[ApexCharts Card](https://github.com/RomRider/apexcharts-card)** - Advanced chart rendering
4. **[Card Mod](https://github.com/thomasloven/lovelace-card-mod)** - Card styling

To install these:
- Go to **HACS > Frontend**
- Search for each card name
- Click **Download** and restart Home Assistant

## How It Works

### Window Selection Algorithm

The algorithm operates on either **15-minute or 1-hour intervals** depending on your configuration:

1. **Data Processing**:
   - **15-minute mode**: Uses Nord Pool's quarter-hourly data directly (96 data points per day)
   - **1-hour mode**: Aggregates four 15-minute periods into hourly averages (24 data points per day)

2. **Percentile Filtering**:
   - Identifies the cheapest X% of windows for charging
   - Identifies the most expensive Y% of windows for discharging

3. **Progressive Selection**:
   - Starts with most extreme prices
   - Adds windows while maintaining minimum spread requirements
   - Ensures profitability considering round-trip efficiency

4. **Spread Calculation**:
   ```
   Spread = ((expensive_price - cheap_price) / cheap_price) * 100
   ```

5. **State Determination**:
   - **Charge**: Current window is in cheap windows and spread requirement met
   - **Discharge**: Current window is in expensive windows and spread requirement met
   - **Discharge Aggressive**: Current window meets aggressive discharge spread
   - **Idle**: No conditions met
   - **Off**: Automation disabled

### Entities Created

The integration creates 69 configuration entities:

#### Sensors
- `sensor.cew_today`: Current state and window information for today
- `sensor.cew_tomorrow`: Window information for tomorrow (when available)

#### Input Numbers (27)
- Window counts (charging, expensive)
- Percentiles (cheap, expensive)
- Spreads (minimum, discharge, aggressive)
- Costs (VAT, tax, additional)
- Battery parameters (power, efficiency)
- Price overrides
- Solar optimization (battery capacity, consumption estimate, skip threshold)

#### Input Booleans (19)
- Automation enable/disable
- Notification settings
- Time override enables
- Tomorrow settings
- Solar optimization enabled

#### Input Selects (7)
- Window duration mode
- Time override modes

#### Input DateTimes (14)
- Time override periods
- Quiet hours

#### Input Text (2)
- Price sensor entity ID
- Solar forecast sensor entity ID

## Services

### cheapest_energy_windows.rotate_settings
Apply tomorrow's settings to today. Automatically triggered at midnight when enabled.

This service can be manually called if you want to:
- Force an immediate settings rotation
- Test the settings rotation functionality
- Reset today's settings to match tomorrow's configuration

## Automation System

### 🚀 Fully Automated Battery Control

The integration provides a **complete, zero-configuration automation system**:

1. **Automatic Creation**: On installation, creates a fully-functional battery control automation
2. **Auto-Updates**: Automation is automatically updated with new features during integration upgrades
3. **Self-Healing**: Recreated if deleted, ensuring your battery control never breaks
4. **State-Based Control**: Responds to calculated energy windows and manual overrides

### 🔗 Battery Operations Linking

**NEW: Link your existing battery control without editing YAML!**

Simply select your battery control method during setup or from the dashboard:
- Link existing **automations** (e.g., `automation.charge_battery`)
- Link existing **scripts** (e.g., `script.set_battery_mode`)
- Link existing **scenes** (e.g., `scene.battery_discharge`)

The integration will automatically trigger your linked actions when entering each mode:
- **Idle** → Your idle automation/script/scene
- **Charge** → Your charging automation/script/scene
- **Discharge** → Your discharge automation/script/scene
- **Aggressive Discharge** → Your peak discharge automation/script/scene

### 📱 Intelligent Notifications

- **Per-State Configuration**: Enable/disable notifications for each battery state
- **Quiet Hours**: Set times when notifications are suppressed
- **Smart Alerts**: Notifies about price overrides, SOC safety blocks, and state changes
- **Automation Status**: Get alerts when automation is disabled or battery is off

### 🛡️ Battery Protection Features

- **SOC Safety Limits**: Prevents discharge below configurable thresholds
- **Dual SOC Thresholds**: Separate limits for normal and aggressive discharge
- **Automatic Mode Reversion**: Returns to idle when SOC limits are reached
- **Configuration Validation**: Alerts if SOC safety is misconfigured

### Manual Control (Advanced)

#### Step 1: Find Your Battery Control Entities

First, identify the entities that control your battery:
- Battery charge switch/number (e.g., `switch.battery_charge`, `number.battery_charge_power`)
- Battery discharge switch/number (e.g., `switch.battery_discharge`, `number.battery_discharge_power`)
- Battery mode select (e.g., `select.battery_mode`)

#### Step 2: Edit the Automations

1. Go to **Settings > Automations & Scenes**
2. Find the automations created by CEW (look for "CEW" or "Cheapest Energy Windows NG" prefix)
3. Click on each automation to edit it
4. Add your battery control actions to the corresponding states

#### Step 3: Automation Examples

**Example 1: Simple Switch Control**

```yaml
automation:
  - alias: "CEW Battery Charge"
    description: "Start battery charging during cheap energy windows"
    trigger:
      - platform: state
        entity_id: sensor.cew_today
        to: 'charge'
    action:
      # Your battery charge action here
      - service: switch.turn_on
        target:
          entity_id: switch.battery_charge
      # Optional: Set charge power
      - service: number.set_value
        target:
          entity_id: number.battery_charge_power
        data:
          value: 2400  # Watts
      # Optional: Send notification
      - service: notify.mobile_app
        data:
          title: "Battery Charging"
          message: "Starting charge at €{{ state_attr('sensor.cew_today', 'avg_cheap_price') }}/kWh"

  - alias: "CEW Battery Discharge"
    description: "Start battery discharging during expensive energy windows"
    trigger:
      - platform: state
        entity_id: sensor.cew_today
        to: 'discharge'
    action:
      # Your battery discharge action here
      - service: switch.turn_on
        target:
          entity_id: switch.battery_discharge
      # Optional: Set discharge power
      - service: number.set_value
        target:
          entity_id: number.battery_discharge_power
        data:
          value: 2400  # Watts

  - alias: "CEW Battery Idle"
    description: "Stop battery activity during idle periods"
    trigger:
      - platform: state
        entity_id: sensor.cew_today
        to: 'idle'
    action:
      # Stop all battery activity
      - service: switch.turn_off
        target:
          entity_id:
            - switch.battery_charge
            - switch.battery_discharge
```

**Example 2: Mode-Based Control (Huawei, SolarEdge, etc.)**

```yaml
automation:
  - alias: "CEW Battery Mode Control"
    description: "Control battery mode based on CEW state"
    trigger:
      - platform: state
        entity_id: sensor.cew_today
    action:
      - choose:
          # Charge mode
          - conditions:
              - condition: state
                entity_id: sensor.cew_today
                state: 'charge'
            sequence:
              - service: select.select_option
                target:
                  entity_id: select.battery_working_mode
                data:
                  option: "Time of Use"
              - service: number.set_value
                target:
                  entity_id: number.battery_charge_power
                data:
                  value: 2400

          # Discharge mode
          - conditions:
              - condition: state
                entity_id: sensor.cew_today
                state: 'discharge'
            sequence:
              - service: select.select_option
                target:
                  entity_id: select.battery_working_mode
                data:
                  option: "Maximise Self Consumption"

          # Idle mode
          - conditions:
              - condition: state
                entity_id: sensor.cew_today
                state: 'idle'
            sequence:
              - service: select.select_option
                target:
                  entity_id: select.battery_working_mode
                data:
                  option: "Fully Fed To Grid"
```

**Example 3: Advanced - Using Time Overrides**

```yaml
automation:
  - alias: "CEW Force Charge Override"
    description: "Force charging during override period"
    trigger:
      - platform: state
        entity_id: input_boolean.cew_time_override_charge_enabled
        to: 'on'
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.battery_charge
      - service: notify.mobile_app
        data:
          title: "Battery Override Active"
          message: "Forcing charge until {{ states('input_datetime.cew_time_override_charge_end') }}"
```

### Using Window Attributes in Automations

You can access detailed window information in your automations:

```yaml
automation:
  - alias: "Morning Energy Report"
    trigger:
      - platform: time
        at: "07:00:00"
    action:
      - service: notify.mobile_app
        data:
          title: "Today's Energy Windows"
          message: >
            Charging at: {{ state_attr('sensor.cew_today', 'cheapest_times') | join(', ') }}
            Avg charge price: €{{ state_attr('sensor.cew_today', 'avg_cheap_price') | round(3) }}/kWh

            Discharging at: {{ state_attr('sensor.cew_today', 'expensive_times') | join(', ') }}
            Avg discharge price: €{{ state_attr('sensor.cew_today', 'avg_expensive_price') | round(3) }}/kWh

            Spread: {{ state_attr('sensor.cew_today', 'spread_percentage') }}%
            Net profit potential: €{{ (state_attr('sensor.cew_today', 'avg_expensive_price') - state_attr('sensor.cew_today', 'avg_cheap_price')) | round(3) }}/kWh
```

### Important Notes

⚠️ **Safety First**: Always test your battery control automations carefully:
- Start with low power values
- Monitor the first few cycles manually
- Ensure your battery BMS has proper protections
- Check that charge/discharge commands work correctly

💡 **Customization**: Every battery system is different. The examples above are templates - you MUST adapt them to your specific battery controller's entities and requirements.

🔔 **Notifications**: Keep notification actions even after adding battery control - they help you monitor that everything is working as expected.

## Solar Forecast Optimization

The integration can optimize charging and discharging decisions based on your solar production forecast. When enabled, it intelligently skips grid charging when solar will fill your battery and prioritizes discharge during periods of low solar production.

### How Solar Optimization Works

**For Charging:**
- Analyzes solar forecast for each potential charge window
- Skips cheap grid charging windows when solar production is expected to fill the battery above a configurable threshold
- Example: If solar forecast predicts enough production to fill 80%+ of your battery capacity, that charge window is skipped

**For Discharging:**
- Calculates a "solar gap score" for each discharge window candidate
- Prioritizes discharge during periods of low/no solar production (solar gaps)
- Uses a combined scoring: 70% price weight + 30% solar gap score
- Ensures battery discharge covers consumption when solar isn't producing

### Solar Configuration

| Entity | Description | Default |
|--------|-------------|---------|
| `switch.cew_solar_optimization_enabled` | Enable/disable solar optimization | Off |
| `text.cew_solar_forecast_sensor` | Entity ID of your Forecast.Solar sensor | not_configured |
| `number.cew_battery_usable_capacity` | Your battery's usable capacity in kWh | 10.0 |
| `number.cew_skip_charge_solar_threshold` | Skip charging when solar fills this % of battery | 80% |
| `number.cew_consumption_estimate` | Your average household consumption in Watts | 500 W |

### Setup Steps

1. **Install Forecast.Solar integration** in Home Assistant (if not already installed)
2. **Enable solar optimization**: Turn on `switch.cew_solar_optimization_enabled`
3. **Configure the sensor**: Enter your Forecast.Solar sensor entity ID in `text.cew_solar_forecast_sensor`
   - Example: `sensor.energy_production_today` or `sensor.energy_production_today_remaining`
4. **Set battery capacity**: Adjust `number.cew_battery_usable_capacity` to your actual usable battery capacity
5. **Set consumption estimate**: Configure `number.cew_consumption_estimate` to your average household load
6. **Adjust threshold** (optional): Lower `skip_charge_solar_threshold` to be more aggressive about skipping grid charges

### Supported Solar Sensors

The integration reads forecast data from **[Forecast.Solar](https://www.home-assistant.io/integrations/forecast_solar/)** sensors. It expects sensors with these attributes:

| Attribute | Description |
|-----------|-------------|
| `wh_period` | Wh production per hour period (preferred) |
| `watts` | Instantaneous watts forecast |
| `wh_days` | Daily production totals |

The integration automatically:
- Parses hourly forecast data
- Interpolates for 15-minute pricing windows
- Separates today and tomorrow forecasts
- Calculates proportional Wh for each price window

### Example Use Cases

**Self-Consumption Optimization:**
- Solar fills battery during the day for free
- Skip overnight grid charging on sunny days
- Discharge during evening peak when solar is gone

**Grid Export Optimization:**
- Prioritize discharge during high-price solar gaps
- Maximize revenue by discharging when both price is high AND solar is low

## Sensor Attributes

### sensor.cew_today

- `cheapest_times`: List of charging window times
- `cheapest_prices`: Corresponding prices for charging windows
- `expensive_times`: List of discharge window times
- `expensive_prices`: Corresponding prices for discharge windows
- `expensive_times_aggressive`: Aggressive discharge windows
- `expensive_prices_aggressive`: Prices for aggressive discharge
- `spread_avg`: Average spread percentage
- `spread_met`: Whether minimum spread requirement is met
- `current_price`: Current electricity price
- `avg_cheap_price`: Average price of cheap windows
- `avg_expensive_price`: Average price of expensive windows
- `completed_charge_windows`: Number of completed charge windows today
- `completed_discharge_windows`: Number of completed discharge windows
- `completed_charge_cost`: Total cost of charging today
- `completed_discharge_revenue`: Total revenue from discharging today
- `solar_optimization_active`: Whether solar optimization is currently active
- `solar_forecast_total_wh`: Total forecasted solar production in Wh
- `net_import_wh`: Expected net grid import (consumption minus solar)

## Dashboard Features

### CEW Control Dashboard

- **Status Overview**: Current state, price, and spread information
- **Window Configuration**: Adjust window counts and percentiles
- **Spread Settings**: Configure minimum spreads for profitability
- **Cost Settings**: VAT, tax, and additional costs
- **Battery Settings**: Power limits and efficiency
- **Tomorrow Settings**: Configure different parameters for tomorrow
- **Time Overrides**: Force charging/discharging during specific periods
- **Notifications**: Configure alerts for state changes
- **Analytics**: View windows, statistics, and price analysis

## Troubleshooting

### No Windows Detected

1. Check that your price sensor is providing data
2. Verify percentile settings aren't too restrictive
3. Ensure minimum spread isn't set too high
4. Check if price override is active

### Tomorrow Sensor Shows "Unavailable"

This is normal. Tomorrow's prices typically become available between 13:00-14:00 (varies by provider).

### Settings Not Rotating at Midnight

1. Ensure "Tomorrow Settings Enabled" is turned on
2. Check that automation is enabled
3. Verify Home Assistant time zone is correct

## Performance

The integration uses an optimized calculation engine with exceptional performance:

- **Update Interval**: 5 seconds - Fast response to state changes
- **Calculation Time**: Extremely fast (<10ms typical) thanks to NumPy optimization
- **Smart Caching**: Results are cached and only recalculated when prices or settings change
- **Efficient Architecture**:
  - Uses NumPy for vectorized array operations
  - Minimal overhead compared to template-based solutions
  - Handles both 15-minute (96 windows) and 1-hour (24 windows) modes efficiently

This means the integration is lightweight on your Home Assistant instance while providing rapid updates to automation states.

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## Releasing

This project uses an automated release workflow. To create a new release:

1. **Update CHANGELOG.md** with the new version and changes
2. **Trigger the release workflow**:
   - Go to **Actions** → **Release** workflow
   - Click **Run workflow**
   - Enter the version number (e.g., `2.1.0`)
   - Optionally add release notes (or leave empty to use CHANGELOG)
   - Click **Run workflow**

The workflow automatically:
- Updates version in `manifest.json` and `const.py`
- Commits the version bump
- Creates and pushes a git tag
- Creates a GitHub release with changelog notes

HACS will pick up the new release automatically.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.


## ☕ Support the Project

If you find this dashboard useful, consider supporting the main integration developer:

[![Buy Me A Coffee](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/cheapest_energy_windows)
