# Cheapest Energy Windows - Project Notes

## Overview

A Home Assistant custom component for battery energy management. It identifies optimal charging windows (cheap electricity) and discharging windows (expensive electricity) based on dynamic pricing from multiple sources.

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
  1. Today: 00:00 → midnight
  2. Tomorrow: midnight → 23:00
- **Normalization method**: `_normalize_tibber_action_response()`

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

## Data Flow

```
Price Sensor (Nord Pool/ENTSO-E/Tibber)
    │
    ▼
CEWPriceSensorProxy
    │ (normalizes to canonical format)
    ▼
CEWCoordinator
    │ (tracks changes, provides config)
    ▼
CEWTodaySensor / CEWTomorrowSensor
    │ (calls calculation engine)
    ▼
WindowCalculationEngine
    │ (NumPy-based window calculations)
    ▼
Battery Mode State (charge/discharge/idle/off)
```

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

## Testing Tibber Integration

### Manual Testing in Home Assistant

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

## Recent Changes (Task 003)

Implemented Tibber action-based price fetching as fallback:
- Calls `tibber.get_prices` Home Assistant action when sensor data unavailable
- Handles midnight boundary with two API calls
- Extracts data from nested `prices["null"]` structure
- Normalizes API response to canonical format
- Integrated with coordinator via `tibber_action_mode` flag

## Known Limitations

1. **Tibber tomorrow prices**: Available after ~13:00 CET
2. **No unit tests**: Project currently lacks test infrastructure
3. **Price unit requirement**: Only EUR/kWh supported (not cents)
4. **15-minute data required**: Even for hourly contracts, 15-min price data needed

## File Structure

```
custom_components/cheapest_energy_windows/
├── __init__.py         # Integration setup, entry point
├── calculation_engine.py  # Window calculation logic (NumPy)
├── config_flow.py      # Setup wizard, sensor detection
├── const.py            # Constants, defaults
├── coordinator.py      # Data coordinator
├── sensor.py           # Sensors including price proxy
├── automation_handler.py  # Battery control automation
├── number.py           # Number input entities
├── select.py           # Select input entities
├── services.py         # HA services
├── switch.py           # Switch entities
├── text.py             # Text input entities
├── time.py             # Time input entities
├── manifest.json       # Integration manifest
├── strings.json        # UI strings
└── translations/       # Localization files
```
