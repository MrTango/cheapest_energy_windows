# Cheapest Energy Windows NG - Project Notes

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A Home Assistant custom component (`cheapest_energy_windows_ng`) for battery energy management. It identifies optimal charging windows (cheap electricity) and discharging windows (expensive electricity) based on dynamic pricing from multiple sources.

## Development Commands

```bash
# Copy to Home Assistant custom_components for testing
cp -r custom_components/cheapest_energy_windows_ng /path/to/homeassistant/config/custom_components/

# View Home Assistant logs for this integration
grep -i "cheapest_energy_windows" /path/to/homeassistant/config/home-assistant.log

# Validate manifest.json
python -c "import json; json.load(open('custom_components/cheapest_energy_windows_ng/manifest.json'))"
```

## Requirements

- Home Assistant 2024.1.0+
- NumPy >= 1.24.0
- Price sensor providing EUR/kWh (not cents)
- 15-minute granularity price data (even for hourly contracts)

## Data Flow

```
Price Sensor (Nord Pool/ENTSO-E/Tibber)
    |
    v
CEWPriceSensorProxy (sensor.py)
    | (normalizes to canonical format)
    v
CEWCoordinator (coordinator.py)
    | (polls every 10 seconds, tracks changes)
    v
CEWTodaySensor / CEWTomorrowSensor (sensor.py)
    | (calls calculation engine)
    v
WindowCalculationEngine (calculation_engine.py)
    | (NumPy-based window calculations)
    v
Battery Mode State (charge/discharge/idle/off)
```

## Supported Price Sensors

### 1. Nord Pool
- **Detection**: `raw_today` and `raw_tomorrow` attributes
- **Format**: Already in canonical format `{start, end, value}`
- **No normalization needed**

### 2. ENTSO-E Transparency Platform
- **Detection**: `prices_today` or `prices_tomorrow` attributes
- **Input format**: `{time, price}`
- **Normalized to**: `{start, end, value}`
- **Normalization method**: `_normalize_entsoe_to_nordpool()`

### 3. Tibber (Two Modes)

#### Tibber Sensor Mode
- **Detection**: `today` attribute containing list with `startsAt` key
- **Input format**: `{startsAt, total, energy, tax}`
- **Normalized to**: `{start, end, value}` (uses `total` for value)
- **Normalization method**: `_normalize_tibber_to_nordpool()`

#### Tibber Action Mode (Primary or Fallback)
- **Primary**: User explicitly selects "Tibber (via action)" in config flow
- **Fallback**: When sensor attributes are empty but `tibber.get_prices` service is available
- **API Response format**:
  ```yaml
  prices:
    "null":  # Note: key is literally "null" string
      - start_time: "2026-01-11T00:00:00.000+01:00"
        price: 0.2865
  ```
- **Requires two API calls** for day boundary:
  1. Today: 00:00 -> midnight
  2. Tomorrow: midnight -> 23:00
- **Normalization method**: `_normalize_tibber_action_response()`

## Canonical Price Data Format

All price sensors are normalized to this format before processing:
```json
{
  "raw_today": [
    {
      "start": "2026-01-11T00:00:00+01:00",
      "end": "2026-01-11T00:15:00+01:00",
      "value": 0.2865
    }
  ],
  "raw_tomorrow": [...],
  "tomorrow_valid": true
}
```

## Key Architecture Components

### sensor.py - CEWPriceSensorProxy
Central proxy sensor that:
1. Detects price sensor format via `_detect_sensor_format()`
2. Normalizes data to canonical Nord Pool format
3. Falls back to Tibber action if sensor data unavailable
4. Updates coordinator with normalized price data

**Key methods:**
- `_detect_sensor_format()` - Returns "nordpool", "entsoe", "tibber", or None
- `_should_use_tibber_action()` - Decides when to use API fallback
- `_call_tibber_get_prices()` - Low-level API call wrapper
- `_fetch_tibber_prices_via_action()` - Orchestrates two API calls
- `_normalize_tibber_action_response()` - Converts API response to canonical format

### coordinator.py - CEWCoordinator
- Polls proxy sensor every 10 seconds
- Tracks price/config changes to avoid spurious recalculations
- Passes `tibber_action_mode` flag to indicate data source
- Provides configuration from `config_entry.options`

### calculation_engine.py - WindowCalculationEngine
- Expects canonical format: `[{start, end, value}]`
- Uses NumPy for fast calculations
- Supports 15-minute or 1-hour window modes
- Calculates cheapest/expensive windows based on percentiles and spreads

### config_flow.py
- Auto-detects available price sensors by scanning entity attributes
- Detects `tibber.get_prices` service availability for action-based option
- Uses `SelectSelector` (not `EntitySelector`) to allow non-entity "tibber_action" option
- Validates sensor format before accepting (special case for "tibber_action")
- Supports Nord Pool, ENTSO-E, Tibber sensors, and Tibber action

### automation_handler.py
- Creates and maintains battery control automations
- Responds to state changes from sensors

## Constants (const.py)

Key Tibber constants:
```python
TIBBER_SERVICE_DOMAIN = "tibber"
TIBBER_SERVICE_GET_PRICES = "get_prices"
TIBBER_TOMORROW_END_HOUR = 23
```

State constants:
```python
STATE_CHARGE = "charge"
STATE_DISCHARGE = "discharge"
STATE_DISCHARGE_AGGRESSIVE = "discharge_aggressive"
STATE_IDLE = "idle"
STATE_OFF = "off"
```

## File Structure

| File | Purpose |
|------|---------|
| `__init__.py` | Integration setup, platform loading, service registration |
| `const.py` | All constants, defaults, configuration keys |
| `sensor.py` | Price proxy and Today/Tomorrow sensors |
| `coordinator.py` | Data coordination and polling |
| `calculation_engine.py` | Window calculation logic (NumPy) |
| `config_flow.py` | Setup wizard, sensor detection |
| `automation_handler.py` | Battery automation management |
| `number.py` | Number input entities |
| `select.py` | Select input entities |
| `services.py` | HA services |
| `switch.py` | Switch entities |
| `text.py` | Text input entities |
| `time.py` | Time input entities |
| `manifest.json` | Integration manifest |
| `strings.json` | UI strings |
| `translations/` | Localization files |

## Testing

write test first, TDD!
use pytest

Manual testing:

1. **Verify Tibber service availability**:
   - Developer Tools > Services
   - Search for `tibber.get_prices`

2. **Test Tibber action directly**:
   ```yaml
   service: tibber.get_prices
   data:
     start: "2026-01-11T00:00:00+01:00"
     end: "2026-01-11T23:59:59+01:00"
   ```

3. **Check CEW logs for**:
   - `"Tibber action available - using action-based fetching"`
   - `"Calling tibber.get_prices: start=..., end=..."`
   - `"Tibber get_prices returned X price entries"`

4. **Verify proxy sensor attributes**:
   - `sensor.cew_price_sensor_proxy`
   - Check `raw_today`, `raw_tomorrow`, `tomorrow_valid`, `tibber_action_mode`

## Global Energy-Aware Window Selection

### Problem Solved

Traditional algorithms select cheapest (charge) and most expensive (discharge) windows independently. This creates scenarios where:

- Discharge windows scheduled early morning (07:00-09:00)
- Charge windows scheduled at midday (10:00-14:00) - cheapest during "daytime"
- Battery drains overnight from consumption
- By morning, battery empty → forced to buy expensive grid power

### Solution: Global Optimization

The algorithm now optimizes **globally across the entire day**:

1. **Find discharge windows FIRST** - identify all expensive periods
2. **Calculate total energy needed** - sum energy for ALL discharge windows
3. **Select charge windows globally** - pick cheapest windows from ANY time that can provide energy before discharge
4. **Simulate energy flow** - verify battery never runs empty

### Algorithm Flow

```
1. Process prices (add VAT/tax)
   ↓
2. Find ALL discharge windows (expensive percentile)
   ↓
3. Calculate TOTAL energy needed for all discharge windows
   ↓
4. Calculate minimum charge windows needed (accounting for RTE)
   ↓
5. Select charge windows GLOBALLY:
   ├─ Sort all available windows by price (cheapest first)
   ├─ Exclude windows overlapping with discharge
   ├─ For each candidate: verify it's before at least one future discharge
   └─ Select until energy requirement met
   ↓
6. Simulate energy flow chronologically:
   ├─ Track battery state hour-by-hour
   ├─ If battery goes negative: add cheapest window before that point
   └─ Repeat until valid
   ↓
7. Find aggressive discharge windows
   ↓
8. Determine current state
```

### Key Methods

**Location**: `calculation_engine.py`

| Method | Purpose |
|--------|---------|
| `_calculate_energy_requirement()` | Calculate total Wh needed for all discharge windows |
| `_select_charge_windows_globally()` | Select cheapest windows from any time period |
| `_simulate_energy_flow()` | Verify battery never goes negative, add windows if needed |

### Example

**Prices**: Night 0.10€, Morning peak 0.45€, Day 0.25€, Evening peak 0.50€

**Old behavior** (local optimization):
```
Charge:    [10:00, 11:00, 12:00, 13:00] @ ~0.25 EUR (cheapest during day)
Discharge: [07:00, 08:00] + [18:00, 19:00, 20:00] @ ~0.45-0.50 EUR
⚠️ Battery empty at 07:00!
```

**New behavior** (global optimization):
```
Charge:    [00:00, 01:00, 02:00, 03:00, 04:00] @ ~0.10 EUR (cheapest overall = night)
Discharge: [07:00, 08:00] + [18:00, 19:00, 20:00] @ ~0.45-0.50 EUR
✅ Night charging covers BOTH morning AND evening peaks!
```

### Energy Calculation

```python
# Total discharge energy
total_discharge_wh = num_discharge_windows × window_duration_hours × discharge_power_watts
# Example: 8 windows × 0.25h × 2400W = 4800 Wh

# Energy needed for charging (accounting for efficiency losses)
energy_needed_wh = total_discharge_wh / battery_rte
# Example: 4800 Wh / 0.85 = 5647 Wh

# Minimum charge windows
min_charge_windows = ceil(energy_needed_wh / (window_duration_hours × charge_power_watts))
# Example: 5647 Wh / (0.25h × 2400W) = 9.4 → 10 windows
```

### Files

| File | Purpose |
|------|---------|
| `calculation_engine.py` | Core algorithm with `_calculate_energy_requirement()`, `_select_charge_windows_globally()`, `_simulate_energy_flow()` |

## Known Limitations

1. **Tibber tomorrow prices**: Available after ~13:00 CET
2. **No unit tests**: Project currently lacks test infrastructure
3. **Price unit requirement**: Only EUR/kWh supported (not cents)
4. **15-minute data required**: Even for hourly contracts, 15-min price data needed

## Startup Race Condition Handling

The Tibber integration may not be fully initialized when CEW starts during Home Assistant boot. This manifests as:
```
AttributeError: 'ConfigEntry' object has no attribute 'runtime_data'
```

**Solution**: CEW implements retry logic with exponential backoff:
- Max 5 retries with increasing delay (10s, 20s, 30s, 40s, 50s)
- Automatic retry when `runtime_data` error is detected
- Clear logging of retry attempts for troubleshooting

**Code locations**:
- `sensor.py:CEWPriceSensorProxy._schedule_tibber_retry()` - Retry scheduling
- `sensor.py:CEWPriceSensorProxy._call_tibber_get_prices()` - Error detection
- `sensor.py:CEWPriceSensorProxy._async_fetch_and_update_tibber_prices()` - Retry handling

## Rules

- always update the README.md and project-notes.md!
- read EXPLANATIONS.md for more details