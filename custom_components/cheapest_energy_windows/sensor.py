"""Sensor platform for Cheapest Energy Windows.

This module provides sensor entities for the Cheapest Energy Windows integration:
- CEWTodaySensor: Today's energy charging/discharging windows
- CEWTomorrowSensor: Tomorrow's energy windows (when available)
- CEWPriceSensorProxy: Proxy sensor that normalizes various price sources
- CEWLastCalculationSensor: Tracks calculation updates for dashboard refresh

TIBBER INTEGRATION - IMPLEMENTATION NOTES
=========================================

The Tibber integration works differently from Nord Pool and ENTSO-E sensors.
While those sensors expose price data via entity attributes, Tibber may not
expose price data through standard sensor attributes. Instead, Tibber provides
price data through the Home Assistant action/service `tibber.get_prices`.

Detection Logic (_should_use_tibber_action):
    1. Check if tibber.get_prices service is registered in Home Assistant
    2. Check if configured price sensor has valid price data in attributes
    3. If sensor data is missing/empty and Tibber action is available, use action

Fetching Logic (_fetch_tibber_prices_via_action):
    Due to Tibber's day boundary handling, two separate API calls are required:
    - Call 1: Today's prices (00:00 today → midnight)
    - Call 2: Tomorrow's prices (midnight → 23:00 tomorrow)
    Tomorrow's prices may be empty before ~13:00 CET when Tibber publishes them.

API Response Format:
    The tibber.get_prices action returns data nested under a "null" string key:
    {
        "prices": {
            "null": [
                {"start_time": "2026-01-11T00:00:00.000+01:00", "price": 0.2865},
                {"start_time": "2026-01-11T00:15:00.000+01:00", "price": 0.274},
                ...
            ]
        }
    }

Normalization (_normalize_tibber_action_response):
    Tibber API response is converted to Nord Pool canonical format:
    - start_time → start (ISO 8601 local time string)
    - (calculated) → end (start + interval, typically 15 minutes)
    - price → value (decimal EUR/kWh)

TESTING PROCEDURE
=================

Manual Testing:
    1. Prerequisites:
       - Home Assistant with Tibber integration configured
       - CEW integration installed with price sensor configured
       - Access to Developer Tools > Services

    2. Verify Tibber Service Availability:
       - Go to Developer Tools > Services
       - Search for "tibber.get_prices"
       - If present, the action-based fallback can be used

    3. Test Tibber Action Directly:
       Service: tibber.get_prices
       Data:
         start: "2026-01-11T00:00:00+01:00"
         end: "2026-01-11T23:59:59+01:00"

    4. Verify CEW Detection:
       - Check Home Assistant logs for:
         "Tibber action available - using action-based fetching"
         "Calling tibber.get_prices: start=..., end=..."
         "Tibber get_prices returned X price entries"

    5. Verify Data Flow:
       - Check sensor.cew_price_sensor_proxy attributes for:
         - raw_today: List of price entries in Nord Pool format
         - raw_tomorrow: List of tomorrow's prices (after ~13:00 CET)
         - tomorrow_valid: Boolean indicating tomorrow data availability
         - tibber_action_mode: True when using action-based fetching

    6. Verify Window Calculation:
       - Check sensor.cew_today attributes for:
         - cheapest_times: Calculated charging windows
         - expensive_times: Calculated discharging windows
         - state: Should be charge/discharge/idle based on current time

Automated Verification:
    - All unit tests in test_sensor.py should pass
    - Integration tests verify Tibber to coordinator data flow
    - No regressions in Nord Pool or ENTSO-E functionality

Troubleshooting:
    - If Tibber action fails: Check Tibber integration setup in HA
    - If prices["null"] is empty: Verify Tibber subscription is active
    - If tomorrow prices missing before 13:00: This is expected behavior
    - If normalization fails: Check start_time format in API response
"""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any, Dict, List, Optional, Tuple
import uuid

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .calculation_engine import WindowCalculationEngine
from .const import (
    DOMAIN,
    LOGGER_NAME,
    PREFIX,
    VERSION,
    STATE_CHARGE,
    STATE_DISCHARGE,
    STATE_DISCHARGE_AGGRESSIVE,
    STATE_IDLE,
    STATE_OFF,
    STATE_AVAILABLE,
    STATE_UNAVAILABLE,
    ATTR_CHEAPEST_TIMES,
    ATTR_CHEAPEST_PRICES,
    ATTR_EXPENSIVE_TIMES,
    ATTR_EXPENSIVE_PRICES,
    ATTR_EXPENSIVE_TIMES_AGGRESSIVE,
    ATTR_EXPENSIVE_PRICES_AGGRESSIVE,
    ATTR_ACTUAL_CHARGE_TIMES,
    ATTR_ACTUAL_CHARGE_PRICES,
    ATTR_ACTUAL_DISCHARGE_TIMES,
    ATTR_ACTUAL_DISCHARGE_PRICES,
    ATTR_COMPLETED_CHARGE_WINDOWS,
    ATTR_COMPLETED_DISCHARGE_WINDOWS,
    ATTR_COMPLETED_CHARGE_COST,
    ATTR_COMPLETED_DISCHARGE_REVENUE,
    ATTR_COMPLETED_BASE_USAGE_COST,
    ATTR_COMPLETED_BASE_USAGE_BATTERY,
    ATTR_TOTAL_COST,
    ATTR_PLANNED_TOTAL_COST,
    ATTR_NUM_WINDOWS,
    ATTR_MIN_SPREAD_REQUIRED,
    ATTR_SPREAD_PERCENTAGE,
    ATTR_SPREAD_MET,
    ATTR_SPREAD_AVG,
    ATTR_ACTUAL_SPREAD_AVG,
    ATTR_DISCHARGE_SPREAD_MET,
    ATTR_AGGRESSIVE_DISCHARGE_SPREAD_MET,
    ATTR_AVG_CHEAP_PRICE,
    ATTR_AVG_EXPENSIVE_PRICE,
    ATTR_CURRENT_PRICE,
    ATTR_PRICE_OVERRIDE_ACTIVE,
    ATTR_TIME_OVERRIDE_ACTIVE,
    TIBBER_SERVICE_DOMAIN,
    TIBBER_SERVICE_GET_PRICES,
    TIBBER_TOMORROW_END_HOUR,
)
from .coordinator import CEWCoordinator

_LOGGER = logging.getLogger(LOGGER_NAME)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Cheapest Energy Windows sensors."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]

    sensors = [
        CEWTodaySensor(coordinator, config_entry),
        CEWTomorrowSensor(coordinator, config_entry),
        CEWPriceSensorProxy(hass, coordinator, config_entry),
        CEWLastCalculationSensor(coordinator, config_entry),
    ]

    async_add_entities(sensors)


class CEWBaseSensor(CoordinatorEntity, SensorEntity):
    """Base class for CEW sensors."""

    def __init__(
        self,
        coordinator: CEWCoordinator,
        config_entry: ConfigEntry,
        sensor_type: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.config_entry = config_entry
        self._sensor_type = sensor_type

        # Set unique ID and name
        self._attr_unique_id = f"{PREFIX}{sensor_type}"
        self._attr_name = f"CEW {sensor_type.replace('_', ' ').title()}"
        self._attr_has_entity_name = False

        # Initialize state
        self._attr_native_value = STATE_OFF

        # Track previous values to detect changes
        self._previous_state = None
        self._previous_attributes = None

        # Persist automation_enabled across sensor recreations (integration reloads)
        # This allows us to detect actual changes in automation state
        persistent_key = f"{DOMAIN}_{config_entry.entry_id}_sensor_{sensor_type}_state"
        if persistent_key not in coordinator.hass.data:
            coordinator.hass.data[persistent_key] = {
                "previous_automation_enabled": None,
                "previous_calc_config_hash": None,
            }
        self._persistent_sensor_state = coordinator.hass.data[persistent_key]
        self._previous_automation_enabled = self._persistent_sensor_state["previous_automation_enabled"]
        self._previous_calc_config_hash = self._persistent_sensor_state["previous_calc_config_hash"]

    @property
    def device_info(self) -> Dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self.config_entry.entry_id)},
            "name": "Cheapest Energy Windows",
            "manufacturer": "Community",
            "model": "Energy Optimizer",
            "sw_version": VERSION,
        }

    def _calc_config_hash(self, config: Dict[str, Any], is_tomorrow: bool = False) -> str:
        """Create a hash of config values that affect calculations.

        Only includes values that impact window calculations and current state.
        Excludes notification settings and other non-calculation config.
        """
        suffix = "_tomorrow" if is_tomorrow and config.get("tomorrow_settings_enabled", False) else ""

        # Config values that affect calculations
        calc_values = [
            config.get("automation_enabled", True),
            config.get(f"charging_windows{suffix}", 4),
            config.get(f"expensive_windows{suffix}", 4),
            config.get(f"cheap_percentile{suffix}", 25),
            config.get(f"expensive_percentile{suffix}", 25),
            config.get(f"min_spread{suffix}", 10),
            config.get(f"min_spread_discharge{suffix}", 20),
            config.get(f"aggressive_discharge_spread{suffix}", 40),
            config.get(f"min_price_difference{suffix}", 0.05),
            config.get("vat", 0.21),
            config.get("tax", 0.12286),
            config.get("additional_cost", 0.02398),
            config.get("battery_rte", 90),
            config.get("charge_power", 2400),
            config.get("discharge_power", 2400),
            config.get(f"price_override_enabled{suffix}", False),
            config.get(f"price_override_threshold{suffix}", 0.15),
            config.get("pricing_window_duration", "15_minutes"),
            # Calculation window settings affect what windows are selected
            config.get(f"calculation_window_enabled{suffix}", False),
            config.get(f"calculation_window_start{suffix}", "00:00:00"),
            config.get(f"calculation_window_end{suffix}", "23:59:59"),
        ]

        # Add time overrides (these affect current state)
        calc_values.extend([
            config.get(f"time_override_enabled{suffix}", False),
            config.get(f"time_override_start{suffix}", "00:00:00"),
            config.get(f"time_override_end{suffix}", "00:00:00"),
            config.get(f"time_override_mode{suffix}", "charge"),
        ])

        # Create hash from all values
        return str(hash(tuple(str(v) for v in calc_values)))


class CEWTodaySensor(CEWBaseSensor):
    """Sensor for today's energy windows."""

    def __init__(self, coordinator: CEWCoordinator, config_entry: ConfigEntry) -> None:
        """Initialize today sensor."""
        super().__init__(coordinator, config_entry, "today")
        self._calculation_engine = WindowCalculationEngine()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        _LOGGER.debug("-"*60)
        _LOGGER.debug(f"SENSOR UPDATE: {self._sensor_type}")
        _LOGGER.debug(f"Coordinator data exists: {self.coordinator.data is not None}")

        if not self.coordinator.data:
            # No coordinator data - maintain previous state if we have one
            # This prevents brief unavailable states during updates
            if self._previous_state is not None:
                _LOGGER.debug("No coordinator data, maintaining previous state")
                # Use previous values and skip write - sensor already has correct state
                return
            else:
                _LOGGER.debug("No coordinator data and no previous state, defaulting to OFF")
                new_state = STATE_OFF
                new_attributes = {}
                self._attr_native_value = new_state
                self._attr_extra_state_attributes = new_attributes
                self._previous_state = new_state
                self._previous_attributes = new_attributes.copy() if new_attributes else None
                self.async_write_ha_state()
                return

        # Layer 3: Check what changed
        price_data_changed = self.coordinator.data.get("price_data_changed", True)
        config_changed = self.coordinator.data.get("config_changed", False)
        is_first_load = self.coordinator.data.get("is_first_load", False)
        scheduled_update = self.coordinator.data.get("scheduled_update", False)

        config = self.coordinator.data.get("config", {})
        current_automation_enabled = config.get("automation_enabled", True)

        # Check if calculation-affecting config changed
        current_calc_config_hash = self._calc_config_hash(config, is_tomorrow=False)
        calc_config_changed = (
            self._previous_calc_config_hash is None or
            self._previous_calc_config_hash != current_calc_config_hash
        )

        _LOGGER.debug(f"Price data changed: {price_data_changed}")
        _LOGGER.debug(f"Config changed: {config_changed}")
        _LOGGER.debug(f"Is first load: {is_first_load}")
        _LOGGER.debug(f"Scheduled update: {scheduled_update}")
        _LOGGER.debug(f"Automation enabled: {current_automation_enabled} (was: {self._previous_automation_enabled})")
        _LOGGER.debug(f"Calc config hash: {current_calc_config_hash} (was: {self._previous_calc_config_hash})")
        _LOGGER.debug(f"Calc config changed: {calc_config_changed}")

        # Check if automation_enabled changed - this requires recalculation
        # Only detect change if we have a previous value (not on very first load)
        automation_enabled_changed = (
            self._previous_automation_enabled is not None and
            self._previous_automation_enabled != current_automation_enabled
        )

        # Only skip recalculation for non-calculation config changes
        # Always recalculate for:
        # - First load
        # - Price data changed
        # - Calculation config changed
        # - Scheduled updates (needed for time-based state changes)
        if config_changed and not price_data_changed and not is_first_load and not calc_config_changed and not scheduled_update:
            # Non-calculation config change (notifications, etc.) - maintain current state
            _LOGGER.debug("Non-calculation config change, skipping recalculation to prevent spurious state changes")
            return

        if calc_config_changed:
            _LOGGER.info(f"Calculation config changed, forcing recalculation")

        if scheduled_update:
            _LOGGER.debug("Scheduled update - recalculating for time-based state changes")

        # On first load, we need to calculate to set initial state even though it's a config change
        if is_first_load:
            _LOGGER.debug("First load - calculating initial state")


        # Price data changed OR first run - proceed with recalculation
        raw_today = self.coordinator.data.get("raw_today", [])

        _LOGGER.debug(f"Raw today length: {len(raw_today)}")
        _LOGGER.debug(f"Config keys: {len(list(config.keys()))} items")
        _LOGGER.debug(f"Automation enabled: {config.get('automation_enabled')}")

        # Calculate windows and state
        if raw_today:
            _LOGGER.debug("Calculating windows...")

            result = self._calculation_engine.calculate_windows(
                raw_today, config, is_tomorrow=False
            )

            calculated_state = result.get("state", STATE_OFF)
            _LOGGER.debug(f"Calculated state: {calculated_state}")
            _LOGGER.debug(f"Charge windows: {len(result.get('cheapest_times', []))}")
            _LOGGER.debug(f"Discharge windows: {len(result.get('expensive_times', []))}")

            new_state = calculated_state
            new_attributes = self._build_attributes(result)
        else:
            # No data available
            automation_enabled = config.get("automation_enabled", True)
            state = STATE_OFF if not automation_enabled else STATE_IDLE
            _LOGGER.debug(f"No raw_today data, setting state to: {state}")

            new_state = state
            new_attributes = self._build_attributes({})

        # Only update if state or attributes have changed
        state_changed = new_state != self._previous_state
        attributes_changed = new_attributes != self._previous_attributes

        if state_changed or attributes_changed:
            if state_changed:
                _LOGGER.info(f"State changed: {self._previous_state} → {new_state}")
            else:
                _LOGGER.debug("Attributes changed, updating sensor")

            self._attr_native_value = new_state
            self._attr_extra_state_attributes = new_attributes
            self._previous_state = new_state
            self._previous_attributes = new_attributes.copy() if new_attributes else None
            self._previous_automation_enabled = current_automation_enabled
            self._previous_calc_config_hash = current_calc_config_hash
            self._persistent_sensor_state["previous_automation_enabled"] = current_automation_enabled
            self._persistent_sensor_state["previous_calc_config_hash"] = current_calc_config_hash

            _LOGGER.debug(f"Final state: {self._attr_native_value}")
            _LOGGER.debug("-"*60)
            self.async_write_ha_state()
        else:
            _LOGGER.debug("No changes detected, maintaining current state")
            # Still update tracking even if state didn't change
            self._previous_automation_enabled = current_automation_enabled
            self._previous_calc_config_hash = current_calc_config_hash
            self._persistent_sensor_state["previous_automation_enabled"] = current_automation_enabled
            self._persistent_sensor_state["previous_calc_config_hash"] = current_calc_config_hash

    def _build_attributes(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Build sensor attributes from calculation result."""
        # Get last config update time from coordinator data
        last_config_update = self.coordinator.data.get("last_config_update") if self.coordinator.data else None

        return {
            ATTR_CHEAPEST_TIMES: result.get("cheapest_times", []),
            ATTR_CHEAPEST_PRICES: result.get("cheapest_prices", []),
            ATTR_EXPENSIVE_TIMES: result.get("expensive_times", []),
            ATTR_EXPENSIVE_PRICES: result.get("expensive_prices", []),
            ATTR_EXPENSIVE_TIMES_AGGRESSIVE: result.get("expensive_times_aggressive", []),
            ATTR_EXPENSIVE_PRICES_AGGRESSIVE: result.get("expensive_prices_aggressive", []),
            ATTR_ACTUAL_CHARGE_TIMES: result.get("actual_charge_times", []),
            ATTR_ACTUAL_CHARGE_PRICES: result.get("actual_charge_prices", []),
            ATTR_ACTUAL_DISCHARGE_TIMES: result.get("actual_discharge_times", []),
            ATTR_ACTUAL_DISCHARGE_PRICES: result.get("actual_discharge_prices", []),
            ATTR_COMPLETED_CHARGE_WINDOWS: result.get("completed_charge_windows", 0),
            ATTR_COMPLETED_DISCHARGE_WINDOWS: result.get("completed_discharge_windows", 0),
            ATTR_COMPLETED_CHARGE_COST: result.get("completed_charge_cost", 0.0),
            ATTR_COMPLETED_DISCHARGE_REVENUE: result.get("completed_discharge_revenue", 0.0),
            ATTR_COMPLETED_BASE_USAGE_COST: result.get("completed_base_usage_cost", 0.0),
            ATTR_COMPLETED_BASE_USAGE_BATTERY: result.get("completed_base_usage_battery", 0.0),
            ATTR_TOTAL_COST: result.get("total_cost", 0.0),
            ATTR_PLANNED_TOTAL_COST: result.get("planned_total_cost", 0.0),
            ATTR_NUM_WINDOWS: result.get("num_windows", 0),
            ATTR_MIN_SPREAD_REQUIRED: result.get("min_spread_required", 0.0),
            ATTR_SPREAD_PERCENTAGE: result.get("spread_percentage", 0.0),
            ATTR_SPREAD_MET: result.get("spread_met", False),
            ATTR_SPREAD_AVG: result.get("spread_avg", 0.0),
            ATTR_ACTUAL_SPREAD_AVG: result.get("actual_spread_avg", 0.0),
            ATTR_DISCHARGE_SPREAD_MET: result.get("discharge_spread_met", False),
            ATTR_AGGRESSIVE_DISCHARGE_SPREAD_MET: result.get("aggressive_discharge_spread_met", False),
            ATTR_AVG_CHEAP_PRICE: result.get("avg_cheap_price", 0.0),
            ATTR_AVG_EXPENSIVE_PRICE: result.get("avg_expensive_price", 0.0),
            ATTR_CURRENT_PRICE: result.get("current_price", 0.0),
            ATTR_PRICE_OVERRIDE_ACTIVE: result.get("price_override_active", False),
            ATTR_TIME_OVERRIDE_ACTIVE: result.get("time_override_active", False),
            "last_config_update": last_config_update.isoformat() if last_config_update else None,
        }


class CEWTomorrowSensor(CEWBaseSensor):
    """Sensor for tomorrow's energy windows."""

    def __init__(self, coordinator: CEWCoordinator, config_entry: ConfigEntry) -> None:
        """Initialize tomorrow sensor."""
        super().__init__(coordinator, config_entry, "tomorrow")
        self._calculation_engine = WindowCalculationEngine()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if not self.coordinator.data:
            # No coordinator data - maintain previous state if we have one
            if self._previous_state is not None:
                _LOGGER.debug("No coordinator data, maintaining previous tomorrow state")
                return
            else:
                new_state = STATE_OFF
                new_attributes = {}
                self._attr_native_value = new_state
                self._attr_extra_state_attributes = new_attributes
                self._previous_state = new_state
                self._previous_attributes = new_attributes.copy() if new_attributes else None
                self.async_write_ha_state()
                return

        # Layer 3: Check what changed
        price_data_changed = self.coordinator.data.get("price_data_changed", True)
        config_changed = self.coordinator.data.get("config_changed", False)
        is_first_load = self.coordinator.data.get("is_first_load", False)
        scheduled_update = self.coordinator.data.get("scheduled_update", False)

        config = self.coordinator.data.get("config", {})
        current_automation_enabled = config.get("automation_enabled", True)

        # Check if calculation-affecting config changed
        current_calc_config_hash = self._calc_config_hash(config, is_tomorrow=True)
        calc_config_changed = (
            self._previous_calc_config_hash is None or
            self._previous_calc_config_hash != current_calc_config_hash
        )

        # Only skip recalculation for non-calculation config changes
        # Always recalculate for scheduled updates (needed for time-based state changes)
        if config_changed and not price_data_changed and not is_first_load and not calc_config_changed and not scheduled_update:
            _LOGGER.debug("Tomorrow: Non-calculation config change, skipping recalculation")
            return

        if calc_config_changed:
            _LOGGER.info(f"Tomorrow: Calculation config changed, forcing recalculation")

        if scheduled_update:
            _LOGGER.debug("Tomorrow: Scheduled update - recalculating for time-based state changes")

        # On first load, calculate to set initial state
        if is_first_load:
            _LOGGER.debug("Tomorrow: First load - calculating initial state")

        # Price data changed OR first run - proceed with recalculation
        tomorrow_valid = self.coordinator.data.get("tomorrow_valid", False)
        raw_tomorrow = self.coordinator.data.get("raw_tomorrow", [])

        if tomorrow_valid and raw_tomorrow:
            # Calculate tomorrow's windows
            result = self._calculation_engine.calculate_windows(
                raw_tomorrow, config, is_tomorrow=True
            )

            # Get calculated state from result (like today sensor does)
            new_state = result.get("state", STATE_OFF)
            new_attributes = self._build_attributes(result)
        else:
            # No tomorrow data yet (Nordpool publishes after 13:00 CET)
            new_state = STATE_OFF
            new_attributes = {}

        # Only update if state or attributes have changed
        state_changed = new_state != self._previous_state
        attributes_changed = new_attributes != self._previous_attributes

        if state_changed or attributes_changed:
            if state_changed:
                _LOGGER.info(f"Tomorrow state changed: {self._previous_state} → {new_state}")
            else:
                _LOGGER.debug("Tomorrow attributes changed, updating sensor")

            self._attr_native_value = new_state
            self._attr_extra_state_attributes = new_attributes
            self._previous_state = new_state
            self._previous_attributes = new_attributes.copy() if new_attributes else None
            self._previous_automation_enabled = current_automation_enabled
            self._previous_calc_config_hash = current_calc_config_hash
            self._persistent_sensor_state["previous_automation_enabled"] = current_automation_enabled
            self._persistent_sensor_state["previous_calc_config_hash"] = current_calc_config_hash
            self.async_write_ha_state()
        else:
            _LOGGER.debug("No changes in tomorrow sensor, maintaining current state")
            # Still update tracking even if state didn't change
            self._previous_automation_enabled = current_automation_enabled
            self._previous_calc_config_hash = current_calc_config_hash
            self._persistent_sensor_state["previous_automation_enabled"] = current_automation_enabled
            self._persistent_sensor_state["previous_calc_config_hash"] = current_calc_config_hash

    def _build_attributes(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Build sensor attributes for tomorrow."""
        # Get last config update time from coordinator data
        last_config_update = self.coordinator.data.get("last_config_update") if self.coordinator.data else None

        # Tomorrow sensor has fewer attributes (no completed windows, etc.)
        return {
            ATTR_CHEAPEST_TIMES: result.get("cheapest_times", []),
            ATTR_CHEAPEST_PRICES: result.get("cheapest_prices", []),
            ATTR_EXPENSIVE_TIMES: result.get("expensive_times", []),
            ATTR_EXPENSIVE_PRICES: result.get("expensive_prices", []),
            ATTR_EXPENSIVE_TIMES_AGGRESSIVE: result.get("expensive_times_aggressive", []),
            ATTR_EXPENSIVE_PRICES_AGGRESSIVE: result.get("expensive_prices_aggressive", []),
            ATTR_ACTUAL_CHARGE_TIMES: result.get("actual_charge_times", []),
            ATTR_ACTUAL_CHARGE_PRICES: result.get("actual_charge_prices", []),
            ATTR_ACTUAL_DISCHARGE_TIMES: result.get("actual_discharge_times", []),
            ATTR_ACTUAL_DISCHARGE_PRICES: result.get("actual_discharge_prices", []),
            ATTR_NUM_WINDOWS: result.get("num_windows", 0),
            ATTR_MIN_SPREAD_REQUIRED: result.get("min_spread_required", 0.0),
            ATTR_SPREAD_PERCENTAGE: result.get("spread_percentage", 0.0),
            ATTR_SPREAD_MET: result.get("spread_met", False),
            ATTR_AVG_CHEAP_PRICE: result.get("avg_cheap_price", 0.0),
            ATTR_AVG_EXPENSIVE_PRICE: result.get("avg_expensive_price", 0.0),
            ATTR_PLANNED_TOTAL_COST: result.get("planned_total_cost", 0.0),
            "last_config_update": last_config_update.isoformat() if last_config_update else None,
        }


class CEWPriceSensorProxy(SensorEntity):
    """Proxy sensor that mirrors the configured price sensor.

    This allows the dashboard to use a consistent sensor entity_id
    regardless of which price sensor the user has configured.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: CEWCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the proxy sensor."""
        self.hass = hass
        self.coordinator = coordinator
        self.config_entry = config_entry

        self._attr_unique_id = f"{PREFIX}price_sensor_proxy"
        self._attr_name = "CEW Price Sensor Proxy"
        self._attr_has_entity_name = False
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

        _LOGGER.debug("Price sensor proxy initialized")

    @property
    def device_info(self):
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self.config_entry.entry_id)},
            "name": "Cheapest Energy Windows",
            "manufacturer": "Community",
            "model": "Energy Optimizer",
            "sw_version": VERSION,
        }

    @property
    def should_poll(self) -> bool:
        """No polling needed - updates come from coordinator."""
        return False

    def _detect_sensor_format(self, attributes):
        """Detect sensor format type."""
        if "raw_today" in attributes and "raw_tomorrow" in attributes:
            return "nordpool"
        elif "prices_today" in attributes or "prices_tomorrow" in attributes:
            return "entsoe"
        elif "today" in attributes:
            # Tibber format: 'today' contains list of dicts with 'startsAt' key
            today_data = attributes.get("today")
            if isinstance(today_data, list) and len(today_data) > 0:
                if isinstance(today_data[0], dict) and "startsAt" in today_data[0]:
                    return "tibber"
        return None

    def _normalize_tibber_to_nordpool(self, attributes):
        """Convert Tibber format to Nord Pool format.

        Tibber data format:
        {
            "today": [{"startsAt": "2023-12-09T03:00:00.000+02:00", "total": 0.46914, ...}],
            "tomorrow": [...]
        }

        Nord Pool canonical format:
        {
            "raw_today": [{"start": "...", "end": "...", "value": 0.46914}],
            "raw_tomorrow": [...]
        }
        """
        from datetime import timedelta
        normalized = {}

        def _detect_interval(price_list):
            """Detect interval duration from consecutive entries.

            Returns interval in minutes. Defaults to 15 minutes if unable to detect.
            """
            if len(price_list) < 2:
                return 15  # Default to 15 minutes for single entry

            # Get first two entries to detect interval
            first_time = dt_util.parse_datetime(price_list[0].get("startsAt", ""))
            second_time = dt_util.parse_datetime(price_list[1].get("startsAt", ""))

            if first_time and second_time:
                delta = (second_time - first_time).total_seconds() / 60
                # Support 15-minute or hourly intervals
                if delta in [15, 60]:
                    return int(delta)

            return 15  # Default to 15 minutes

        def _convert_price_list(price_list):
            """Convert a list of Tibber prices to Nord Pool format."""
            if not price_list:
                return []

            result = []
            interval_minutes = _detect_interval(price_list)

            for item in price_list:
                starts_at = item.get("startsAt", "")
                parsed = dt_util.parse_datetime(starts_at)
                if parsed:
                    # Convert to local timezone
                    local_time = dt_util.as_local(parsed)
                    end_time = local_time + timedelta(minutes=interval_minutes)
                    result.append({
                        "start": local_time.isoformat(),
                        "end": end_time.isoformat(),
                        "value": item.get("total", 0)
                    })

            return result

        # Convert today to raw_today
        today_data = attributes.get("today")
        if today_data and isinstance(today_data, list):
            normalized["raw_today"] = _convert_price_list(today_data)
        else:
            normalized["raw_today"] = []

        # Convert tomorrow to raw_tomorrow
        tomorrow_data = attributes.get("tomorrow")
        if tomorrow_data and isinstance(tomorrow_data, list) and len(tomorrow_data) > 0:
            normalized["raw_tomorrow"] = _convert_price_list(tomorrow_data)
            normalized["tomorrow_valid"] = True
        else:
            normalized["raw_tomorrow"] = []
            normalized["tomorrow_valid"] = False

        # Pass through other attributes we might need
        for key, value in attributes.items():
            if key not in ["today", "tomorrow"]:
                normalized[key] = value

        return normalized

    def _normalize_entsoe_to_nordpool(self, attributes):
        """Convert ENTSO-E format to Nord Pool format."""
        from datetime import timedelta
        normalized = {}

        # Convert prices_today to raw_today
        if "prices_today" in attributes and attributes["prices_today"]:
            raw_today = []
            for item in attributes["prices_today"]:
                time_str = item.get("time", "")
                parsed = dt_util.parse_datetime(time_str)
                if parsed:
                    # Convert UTC to local timezone
                    local_time = dt_util.as_local(parsed)
                    end_time = local_time + timedelta(minutes=15)
                    raw_today.append({
                        "start": local_time.isoformat(),
                        "end": end_time.isoformat(),
                        "value": item.get("price", 0)
                    })
            normalized["raw_today"] = raw_today
        else:
            normalized["raw_today"] = []

        # Convert prices_tomorrow to raw_tomorrow
        if "prices_tomorrow" in attributes and attributes["prices_tomorrow"]:
            raw_tomorrow = []
            for item in attributes["prices_tomorrow"]:
                time_str = item.get("time", "")
                parsed = dt_util.parse_datetime(time_str)
                if parsed:
                    # Convert UTC to local timezone
                    local_time = dt_util.as_local(parsed)
                    end_time = local_time + timedelta(minutes=15)
                    raw_tomorrow.append({
                        "start": local_time.isoformat(),
                        "end": end_time.isoformat(),
                        "value": item.get("price", 0)
                    })
            normalized["raw_tomorrow"] = raw_tomorrow
            normalized["tomorrow_valid"] = True
        else:
            normalized["raw_tomorrow"] = []
            normalized["tomorrow_valid"] = False

        # Pass through other attributes we might need
        for key, value in attributes.items():
            if key not in ["prices_today", "prices_tomorrow", "prices", "raw_prices"]:
                normalized[key] = value

        return normalized

    # =========================================================================
    # TIBBER ACTION-BASED PRICE FETCHING
    # =========================================================================
    # The following methods implement Tibber price fetching via the Home Assistant
    # tibber.get_prices action/service. This is used as a fallback when:
    #   1. The configured price sensor doesn't expose price data via attributes
    #   2. The Tibber integration is installed and tibber.get_prices is available
    #
    # Key methods:
    #   - _call_tibber_get_prices(): Low-level API call wrapper
    #   - _fetch_tibber_prices_via_action(): Orchestrates two API calls for day boundary
    #   - _normalize_tibber_action_response(): Converts API response to Nord Pool format
    #   - _should_use_tibber_action(): Detection logic for when to use action fallback
    #   - _async_fetch_and_update_tibber_prices(): Async update entry point
    # =========================================================================

    async def _call_tibber_get_prices(
        self, start: datetime, end: datetime
    ) -> List[Dict[str, Any]]:
        """Call the Tibber get_prices action with time range parameters.

        This method calls the Home Assistant tibber.get_prices action to fetch
        price data from the Tibber API. The response contains prices nested under
        a "null" key which this method extracts.

        Args:
            start: Start datetime for the price range (timezone-aware)
            end: End datetime for the price range (timezone-aware)

        Returns:
            List of price dictionaries with 'start_time' and 'price' fields,
            or empty list on failure.
        """
        try:
            # Format timestamps as ISO 8601 strings
            start_str = start.isoformat()
            end_str = end.isoformat()

            _LOGGER.debug(
                "Calling tibber.get_prices: start=%s, end=%s",
                start_str,
                end_str,
            )

            # Call the Tibber service action
            response = await self.hass.services.async_call(
                TIBBER_SERVICE_DOMAIN,
                TIBBER_SERVICE_GET_PRICES,
                {
                    "start": start_str,
                    "end": end_str,
                },
                blocking=True,
                return_response=True,
            )

            _LOGGER.debug("Tibber get_prices response type: %s", type(response))

            if not response:
                _LOGGER.warning("Tibber get_prices returned empty response")
                return []

            # Extract prices from the nested structure
            # Tibber returns: {"prices": {"null": [{"start_time": "...", "price": 0.123}, ...]}}
            prices_container = response.get("prices", {})

            if not prices_container:
                _LOGGER.warning("Tibber response missing 'prices' key")
                return []

            # The prices are nested under a "null" string key
            price_list = prices_container.get("null", [])

            if not price_list:
                _LOGGER.debug(
                    "Tibber prices['null'] is empty. Available keys: %s",
                    list(prices_container.keys()),
                )
                return []

            _LOGGER.debug(
                "Tibber get_prices returned %d price entries",
                len(price_list),
            )

            return price_list

        except Exception as err:
            _LOGGER.error(
                "Failed to call tibber.get_prices: %s",
                err,
                exc_info=True,
            )
            return []

    async def _fetch_tibber_prices_via_action(
        self,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Fetch Tibber prices using two API calls for day boundary handling.

        Tibber requires separate API calls for today and tomorrow data due to
        its day boundary handling. This method:
        1. Calls API for today: from start of today (00:00) to midnight
        2. Calls API for tomorrow: from midnight to end of tomorrow (23:00)

        Returns:
            Tuple of (today_prices, tomorrow_prices) where each is a list of
            price dictionaries with 'start_time' and 'price' fields.
            Returns empty lists on failure or if data is not yet available.
        """
        now = dt_util.now()

        # Calculate time range boundaries
        # Today: 00:00 today to 00:00 tomorrow (midnight)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        midnight = today_start + timedelta(days=1)

        # Tomorrow: 00:00 tomorrow to 23:00 tomorrow
        tomorrow_end = midnight.replace(hour=TIBBER_TOMORROW_END_HOUR, minute=0)

        _LOGGER.debug(
            "Fetching Tibber prices - today: %s to %s, tomorrow: %s to %s",
            today_start.isoformat(),
            midnight.isoformat(),
            midnight.isoformat(),
            tomorrow_end.isoformat(),
        )

        # Call 1: Today's prices (00:00 today -> midnight)
        today_prices = await self._call_tibber_get_prices(today_start, midnight)
        _LOGGER.debug(
            "Tibber today prices: %d entries",
            len(today_prices),
        )

        # Call 2: Tomorrow's prices (midnight -> end of tomorrow)
        # This may return empty if tomorrow's prices are not yet available
        # (Tibber typically publishes tomorrow's prices after ~13:00 CET)
        tomorrow_prices = await self._call_tibber_get_prices(midnight, tomorrow_end)
        _LOGGER.debug(
            "Tibber tomorrow prices: %d entries",
            len(tomorrow_prices),
        )

        if not today_prices:
            _LOGGER.warning(
                "No today prices received from Tibber API action"
            )

        if not tomorrow_prices:
            _LOGGER.debug(
                "No tomorrow prices from Tibber - may not be available yet "
                "(typically published after 13:00 CET)"
            )

        return today_prices, tomorrow_prices

    def _normalize_tibber_action_response(
        self,
        today_prices: List[Dict[str, Any]],
        tomorrow_prices: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Convert Tibber API action response to Nord Pool canonical format.

        This normalizes the response from tibber.get_prices action which returns
        price data in a different format than Tibber sensor attributes.

        Tibber API action format (extracted from prices["null"]):
        [
            {"start_time": "2026-01-11T00:00:00.000+01:00", "price": 0.2865},
            {"start_time": "2026-01-11T00:15:00.000+01:00", "price": 0.274},
            ...
        ]

        Nord Pool canonical format:
        {
            "raw_today": [{"start": "...", "end": "...", "value": 0.2865}],
            "raw_tomorrow": [...],
            "tomorrow_valid": True/False
        }

        Args:
            today_prices: List of price dicts from today's API call
            tomorrow_prices: List of price dicts from tomorrow's API call

        Returns:
            Dictionary with raw_today, raw_tomorrow, and tomorrow_valid keys
            in Nord Pool canonical format.
        """
        from datetime import timedelta

        def _detect_interval(price_list: List[Dict[str, Any]]) -> int:
            """Detect interval duration from consecutive entries.

            Returns interval in minutes. Defaults to 15 minutes if unable to detect.
            Tibber API typically uses 15-minute intervals.
            """
            if len(price_list) < 2:
                return 15  # Default to 15 minutes for single entry

            # Get first two entries to detect interval
            first_time = dt_util.parse_datetime(price_list[0].get("start_time", ""))
            second_time = dt_util.parse_datetime(price_list[1].get("start_time", ""))

            if first_time and second_time:
                delta = (second_time - first_time).total_seconds() / 60
                # Support 15-minute or hourly intervals
                if delta in [15, 60]:
                    return int(delta)

            return 15  # Default to 15 minutes (Tibber standard)

        def _convert_price_list(price_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            """Convert a list of Tibber API action prices to Nord Pool format.

            Handles the mapping:
              - start_time → start (ISO 8601 local time)
              - (calculated) → end (start + interval)
              - price → value
            """
            if not price_list:
                return []

            result = []
            interval_minutes = _detect_interval(price_list)

            for item in price_list:
                start_time = item.get("start_time", "")

                # Skip entries with missing or invalid data
                if not start_time:
                    _LOGGER.debug(
                        "Skipping Tibber price entry with missing start_time: %s",
                        item,
                    )
                    continue

                parsed = dt_util.parse_datetime(start_time)
                if not parsed:
                    _LOGGER.debug(
                        "Failed to parse Tibber start_time: %s",
                        start_time,
                    )
                    continue

                # Convert to local timezone
                local_time = dt_util.as_local(parsed)
                end_time = local_time + timedelta(minutes=interval_minutes)

                # Get price value, skip if missing
                price = item.get("price")
                if price is None:
                    _LOGGER.debug(
                        "Skipping Tibber price entry with missing price: %s",
                        item,
                    )
                    continue

                result.append({
                    "start": local_time.isoformat(),
                    "end": end_time.isoformat(),
                    "value": price,
                })

            return result

        # Build normalized output
        normalized: Dict[str, Any] = {}

        # Flag to indicate this data came from Tibber action-based fetching
        # This allows the coordinator to track the data source mode
        normalized["tibber_action_mode"] = True

        # Convert today's prices to raw_today
        normalized["raw_today"] = _convert_price_list(today_prices)
        _LOGGER.debug(
            "Normalized Tibber today prices: %d entries",
            len(normalized["raw_today"]),
        )

        # Convert tomorrow's prices to raw_tomorrow
        if tomorrow_prices:
            normalized["raw_tomorrow"] = _convert_price_list(tomorrow_prices)
            normalized["tomorrow_valid"] = len(normalized["raw_tomorrow"]) > 0
        else:
            normalized["raw_tomorrow"] = []
            normalized["tomorrow_valid"] = False

        _LOGGER.debug(
            "Normalized Tibber tomorrow prices: %d entries, valid: %s",
            len(normalized["raw_tomorrow"]),
            normalized["tomorrow_valid"],
        )

        return normalized

    def _should_use_tibber_action(self) -> bool:
        """Determine if we should use Tibber action-based fetching vs sensor-based.

        This method checks:
        1. If the tibber.get_prices service is available in Home Assistant
        2. If the configured price sensor is missing or has no usable price data

        Returns:
            True if we should use tibber.get_prices action to fetch prices,
            False if we should rely on sensor-based data.
        """
        # Check 1: Is the Tibber service available?
        if not self.hass.services.has_service(TIBBER_SERVICE_DOMAIN, TIBBER_SERVICE_GET_PRICES):
            _LOGGER.debug(
                "Tibber action not available: %s.%s service not registered",
                TIBBER_SERVICE_DOMAIN,
                TIBBER_SERVICE_GET_PRICES,
            )
            return False

        # Check 2: Get the configured price sensor and its data
        price_sensor_entity = self.hass.states.get(f"text.{PREFIX}price_sensor_entity")
        if not price_sensor_entity:
            # No price sensor configured, but Tibber action is available - use it
            _LOGGER.debug(
                "No price sensor entity configured, Tibber action available - using action-based fetching"
            )
            return True

        price_sensor_id = price_sensor_entity.state
        if not price_sensor_id or price_sensor_id == "":
            # Price sensor not configured, but Tibber action is available - use it
            _LOGGER.debug(
                "Price sensor entity not set, Tibber action available - using action-based fetching"
            )
            return True

        # Get the actual price sensor state
        price_sensor = self.hass.states.get(price_sensor_id)
        if not price_sensor:
            # Configured sensor not found, but Tibber action is available - use it
            _LOGGER.debug(
                "Configured price sensor %s not found, using Tibber action fallback",
                price_sensor_id,
            )
            return True

        # Check 3: Does the sensor have usable price data?
        attributes = price_sensor.attributes
        sensor_format = self._detect_sensor_format(attributes)

        if sensor_format is None:
            # Unknown format - check if it's a Tibber sensor with empty data
            # Tibber sensors sometimes don't expose price data via attributes
            # In this case, we should use the action-based approach
            _LOGGER.debug(
                "Price sensor %s has unknown format, checking for Tibber action fallback",
                price_sensor_id,
            )

            # If Tibber service is available and sensor format is unknown,
            # the sensor might be a Tibber sensor that doesn't expose attributes
            return True

        # Check if the detected format has actual data
        if sensor_format == "nordpool":
            raw_today = attributes.get("raw_today", [])
            if not raw_today:
                _LOGGER.debug(
                    "Nord Pool sensor %s has empty raw_today, using Tibber action fallback",
                    price_sensor_id,
                )
                return True

        elif sensor_format == "entsoe":
            prices_today = attributes.get("prices_today", [])
            if not prices_today:
                _LOGGER.debug(
                    "ENTSO-E sensor %s has empty prices_today, using Tibber action fallback",
                    price_sensor_id,
                )
                return True

        elif sensor_format == "tibber":
            today_data = attributes.get("today", [])
            if not today_data:
                _LOGGER.debug(
                    "Tibber sensor %s has empty today data, using Tibber action fallback",
                    price_sensor_id,
                )
                return True

        # Sensor has valid data, no need to use action-based fetching
        _LOGGER.debug(
            "Price sensor %s has valid %s format data, using sensor-based approach",
            price_sensor_id,
            sensor_format,
        )
        return False

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator.

        This method handles price data from multiple sources:
        1. Sensor-based: Nord Pool, ENTSO-E, or Tibber sensors with attribute data
        2. Action-based: Tibber API action (tibber.get_prices) for cases where
           sensor attributes don't contain price data

        The method first tries sensor-based data, then falls back to Tibber action
        if the tibber.get_prices service is available and sensor data is missing.
        """
        if not self.coordinator.data:
            return

        # Get the configured price sensor entity_id
        price_sensor_entity = self.hass.states.get(f"text.{PREFIX}price_sensor_entity")
        if not price_sensor_entity:
            _LOGGER.warning("Price sensor entity text input not found")
            # Check if we can use Tibber action as fallback
            if self._should_use_tibber_action():
                _LOGGER.info("No price sensor configured, attempting Tibber action-based fetching")
                self.hass.async_create_task(self._async_fetch_and_update_tibber_prices())
            return

        price_sensor_id = price_sensor_entity.state
        if not price_sensor_id or price_sensor_id == "":
            _LOGGER.warning("Price sensor entity not configured")
            # Check if we can use Tibber action as fallback
            if self._should_use_tibber_action():
                _LOGGER.info("Price sensor not set, attempting Tibber action-based fetching")
                self.hass.async_create_task(self._async_fetch_and_update_tibber_prices())
            return

        # Special case: Tibber action-based fetching (configured explicitly)
        if price_sensor_id == "tibber_action":
            _LOGGER.debug("Tibber action mode configured, using action-based fetching")
            self.hass.async_create_task(self._async_fetch_and_update_tibber_prices())
            return

        # Get the actual price sensor state
        price_sensor = self.hass.states.get(price_sensor_id)
        if not price_sensor:
            _LOGGER.warning(f"Configured price sensor {price_sensor_id} not found")
            # Check if we can use Tibber action as fallback
            if self._should_use_tibber_action():
                _LOGGER.info(
                    "Price sensor %s not found, attempting Tibber action-based fetching",
                    price_sensor_id,
                )
                self.hass.async_create_task(self._async_fetch_and_update_tibber_prices())
            else:
                self._attr_native_value = STATE_UNAVAILABLE
                self.async_write_ha_state()
            return

        # Mirror the state from the price sensor
        self._attr_native_value = price_sensor.state

        # Detect format and normalize if needed
        sensor_format = self._detect_sensor_format(price_sensor.attributes)

        if sensor_format == "entsoe":
            _LOGGER.debug(f"Detected ENTSO-E format from {price_sensor_id}, normalizing to Nord Pool format")
            self._attr_extra_state_attributes = self._normalize_entsoe_to_nordpool(price_sensor.attributes)
            _LOGGER.debug(f"Proxy sensor updated from {price_sensor_id}, state: {self._attr_native_value}")
            self.async_write_ha_state()

        elif sensor_format == "tibber":
            _LOGGER.debug(f"Detected Tibber format from {price_sensor_id}, normalizing to Nord Pool format")
            self._attr_extra_state_attributes = self._normalize_tibber_to_nordpool(price_sensor.attributes)
            _LOGGER.debug(f"Proxy sensor updated from {price_sensor_id}, state: {self._attr_native_value}")
            self.async_write_ha_state()

        elif sensor_format == "nordpool":
            _LOGGER.debug(f"Detected Nord Pool format from {price_sensor_id}, passing through")
            self._attr_extra_state_attributes = dict(price_sensor.attributes)
            _LOGGER.debug(f"Proxy sensor updated from {price_sensor_id}, state: {self._attr_native_value}")
            self.async_write_ha_state()

        else:
            # Unknown format - check if we should use Tibber action fallback
            _LOGGER.debug(
                "Unknown price sensor format from %s, checking Tibber action fallback",
                price_sensor_id,
            )
            if self._should_use_tibber_action():
                _LOGGER.info(
                    "Sensor %s has unknown format, using Tibber action-based fetching",
                    price_sensor_id,
                )
                self.hass.async_create_task(self._async_fetch_and_update_tibber_prices())
            else:
                # No Tibber fallback available, pass through as-is
                _LOGGER.warning(
                    "Unknown price sensor format from %s and no Tibber action available, passing through as-is",
                    price_sensor_id,
                )
                self._attr_extra_state_attributes = dict(price_sensor.attributes)
                _LOGGER.debug(f"Proxy sensor updated from {price_sensor_id}, state: {self._attr_native_value}")
                self.async_write_ha_state()

    async def _async_fetch_and_update_tibber_prices(self) -> None:
        """Async method to fetch Tibber prices via action and update sensor state.

        This method is called when sensor-based price data is not available but
        the tibber.get_prices action is available. It fetches prices using the
        Tibber API action, normalizes them to Nord Pool format, and updates
        the sensor attributes.
        """
        try:
            _LOGGER.debug("Starting Tibber action-based price fetching")

            # Fetch prices using the Tibber action (two API calls for day boundary)
            today_prices, tomorrow_prices = await self._fetch_tibber_prices_via_action()

            if not today_prices:
                _LOGGER.warning(
                    "Tibber action returned no today prices, cannot update proxy sensor"
                )
                self._attr_native_value = STATE_UNAVAILABLE
                self._attr_extra_state_attributes = {}
                self.async_write_ha_state()
                return

            # Normalize to Nord Pool canonical format
            normalized = self._normalize_tibber_action_response(today_prices, tomorrow_prices)

            # Update sensor attributes with normalized data
            self._attr_extra_state_attributes = normalized

            # Set state to available (use current price if we can determine it)
            # For now, set to a placeholder state indicating data is available
            if normalized.get("raw_today"):
                self._attr_native_value = STATE_AVAILABLE
            else:
                self._attr_native_value = STATE_UNAVAILABLE

            _LOGGER.info(
                "Tibber action-based price fetch complete: %d today entries, %d tomorrow entries",
                len(normalized.get("raw_today", [])),
                len(normalized.get("raw_tomorrow", [])),
            )

            self.async_write_ha_state()

        except Exception as err:
            _LOGGER.error(
                "Failed to fetch and update Tibber prices via action: %s",
                err,
                exc_info=True,
            )
            self._attr_native_value = STATE_UNAVAILABLE
            self._attr_extra_state_attributes = {}
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        # Subscribe to coordinator updates
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

        # Do initial update
        self._handle_coordinator_update()


class CEWLastCalculationSensor(CoordinatorEntity, SensorEntity):
    """Sensor that tracks calculation updates with unique state values.

    This sensor generates a unique random value on every coordinator update
    to trigger chart refreshes via a hidden series in the dashboard.
    Using random values ensures state changes are always detected,
    even with rapid consecutive updates.
    """

    def __init__(
        self,
        coordinator: CEWCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.config_entry = config_entry
        self._attr_unique_id = f"{PREFIX}last_calculation"
        self._attr_name = "CEW Last Calculation"
        self._attr_has_entity_name = False
        self._attr_icon = "mdi:refresh"

        # Initialize with random value
        self._attr_native_value = str(uuid.uuid4())[:8]

    @property
    def device_info(self):
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self.config_entry.entry_id)},
            "name": "Cheapest Energy Windows",
            "manufacturer": "Community",
            "model": "Energy Optimizer",
            "sw_version": VERSION,
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if not self.coordinator.data:
            return

        # Only update when calculations actually change
        # Coordinator polls every 10s for state transitions, but this sensor
        # only updates when price data changes or config changes to avoid
        # unnecessary chart refreshes
        price_data_changed = self.coordinator.data.get("price_data_changed", False)
        config_changed = self.coordinator.data.get("config_changed", False)

        if price_data_changed or config_changed:
            # Actual calculation occurred - generate new unique value
            self._attr_native_value = str(uuid.uuid4())[:8]
            self.async_write_ha_state()
            _LOGGER.debug(f"Last calculation updated: {self._attr_native_value} (price_changed={price_data_changed}, config_changed={config_changed})")

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        # Subscribe to coordinator updates
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

        # Do initial update
        self._handle_coordinator_update()