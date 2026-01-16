"""Data coordinator for Cheapest Energy Windows NG."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from typing import Any, Dict, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    LOGGER_NAME,
    UPDATE_INTERVAL,
    CONF_PRICE_SENSOR,
    DEFAULT_PRICE_SENSOR,
    DEFAULT_BASE_USAGE,
    DEFAULT_BASE_USAGE_CHARGE_STRATEGY,
    DEFAULT_BASE_USAGE_IDLE_STRATEGY,
    DEFAULT_BASE_USAGE_DISCHARGE_STRATEGY,
    DEFAULT_BASE_USAGE_AGGRESSIVE_STRATEGY,
    PREFIX,
    DEFAULT_SOLAR_FORECAST_SENSOR,
    DEFAULT_SOLAR_OPTIMIZATION_ENABLED,
    DEFAULT_SOLAR_FORECAST_SENSORS_TODAY,
    DEFAULT_SOLAR_FORECAST_SENSORS_TOMORROW,
)

_LOGGER = logging.getLogger(LOGGER_NAME)


class CEWCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    """Class to manage fetching Cheapest Energy Windows NG data."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )

        self.config_entry = config_entry
        self.price_sensor = config_entry.data.get(CONF_PRICE_SENSOR, DEFAULT_PRICE_SENSOR)

        # Track previous price data to detect changes (Layer 2)
        # Store in hass.data to persist across integration reloads
        persistent_key = f"{DOMAIN}_{config_entry.entry_id}_price_state"
        if persistent_key not in hass.data:
            hass.data[persistent_key] = {
                "previous_raw_today": None,
                "previous_raw_tomorrow": None,
                "last_price_update": None,
                "last_config_update": None,
                "previous_config_hash": None,
            }
        self._persistent_state = hass.data[persistent_key]

        # Instance variables (for convenience, but backed by persistent storage)
        self._previous_raw_today: Optional[list] = self._persistent_state["previous_raw_today"]
        self._previous_raw_tomorrow: Optional[list] = self._persistent_state["previous_raw_tomorrow"]
        self._last_price_update: Optional[datetime] = self._persistent_state["last_price_update"]
        self._last_config_update: Optional[datetime] = self._persistent_state["last_config_update"]
        self._previous_config_hash: Optional[str] = self._persistent_state["previous_config_hash"]

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from price sensor."""
        _LOGGER.debug("="*60)
        _LOGGER.debug("COORDINATOR UPDATE START")
        _LOGGER.debug("="*60)

        try:
            # Always use the proxy sensor which normalizes different price sensor formats
            # The proxy sensor handles both Nord Pool and ENTSO-E formats
            price_sensor = "sensor.cew_price_sensor_proxy"
            _LOGGER.debug(f"Using proxy price sensor: {price_sensor}")

            # Get the price sensor state
            price_state = self.hass.states.get(price_sensor)
            _LOGGER.debug(f"Price sensor state exists: {price_state is not None}")

            if not price_state:
                _LOGGER.warning(f"Price sensor {price_sensor} not found, returning empty data")
                _LOGGER.debug(f"Available sensors: {[e for e in self.hass.states.async_entity_ids() if 'nordpool' in e or 'price' in e]}")
                return await self._empty_data(f"Price sensor {price_sensor} not found")

            _LOGGER.debug(f"Price sensor state: {price_state.state}")
            _LOGGER.debug(f"Price sensor attributes keys: {list(price_state.attributes.keys())}")

            # Extract price data
            raw_today = price_state.attributes.get("raw_today", [])
            raw_tomorrow = price_state.attributes.get("raw_tomorrow", [])
            tomorrow_valid = price_state.attributes.get("tomorrow_valid", False)

            # Check if proxy sensor is using Tibber action-based fetching
            # First check if tibber_action_mode is set in proxy sensor attributes
            tibber_action_mode = price_state.attributes.get("tibber_action_mode", False)

            # Also check the price sensor entity configuration directly
            # This is more reliable than relying on proxy sensor attributes
            price_sensor_entity_id = f"text.{PREFIX}price_sensor_entity"
            price_sensor_entity = self.hass.states.get(price_sensor_entity_id)
            if price_sensor_entity and price_sensor_entity.state == "tibber_action":
                tibber_action_mode = True
                _LOGGER.debug("Tibber action mode detected from price sensor entity configuration")

            _LOGGER.debug(f"Raw today count: {len(raw_today)}")
            _LOGGER.debug(f"Raw tomorrow count: {len(raw_tomorrow)}")
            _LOGGER.debug(f"Tomorrow valid: {tomorrow_valid}")
            _LOGGER.debug(f"Tibber action mode: {tibber_action_mode}")

            # In Tibber action mode, empty raw_today is expected while fetching is in progress
            # Only log warning if we're NOT in Tibber action mode
            if not raw_today:
                if tibber_action_mode:
                    _LOGGER.debug("No price data available for today (Tibber action mode, data may still be fetching)")
                else:
                    _LOGGER.warning("No price data available for today")
                _LOGGER.debug(f"raw_today value: {raw_today}")
                return await self._empty_data("No price data available")

            # Get configuration from config entry options (Layer 1: no race conditions)
            config = await self._get_configuration()
            _LOGGER.debug(f"Config keys loaded: {list(config.keys())}")
            _LOGGER.debug(f"Automation enabled: {config.get('automation_enabled', 'NOT SET')}")
            _LOGGER.debug(f"Charging windows: {config.get('charging_windows', 'NOT SET')}")

            # Layer 2: Detect what changed
            now = dt_util.now()
            price_data_changed = False
            config_changed = False
            is_first_load = False
            scheduled_update = False  # New: track scheduled updates where nothing changed

            # Check if price data changed
            # Compare lengths and a hash of the data for more reliable comparison
            def _price_data_hash(data):
                """Create a simple hash of price data for comparison."""
                if not data:
                    return ""
                # Create hash from length and first/last items
                try:
                    return f"{len(data)}_{data[0].get('value', 0)}_{data[-1].get('value', 0)}"
                except (IndexError, AttributeError, TypeError):
                    return str(len(data))

            def _config_hash(cfg):
                """Create a simple hash of config for comparison."""
                # Convert config dict to a sorted tuple of items for consistent hashing
                try:
                    return str(hash(tuple(sorted((k, str(v)) for k, v in cfg.items()))))
                except (TypeError, AttributeError):
                    return str(cfg)

            current_today_hash = _price_data_hash(raw_today)
            current_tomorrow_hash = _price_data_hash(raw_tomorrow)
            previous_today_hash = _price_data_hash(self._previous_raw_today)
            previous_tomorrow_hash = _price_data_hash(self._previous_raw_tomorrow)

            current_config_hash = _config_hash(config)
            previous_config_hash = self._previous_config_hash

            _LOGGER.debug(f"Today hash: {current_today_hash} vs {previous_today_hash}")
            _LOGGER.debug(f"Tomorrow hash: {current_tomorrow_hash} vs {previous_tomorrow_hash}")
            _LOGGER.debug(f"Config hash: {current_config_hash} vs {previous_config_hash}")

            # Check if this is the first load (no previous data)
            if not previous_today_hash and not previous_tomorrow_hash:
                # First load after restart/reload - treat as initialization, not a real update
                is_first_load = True
                config_changed = True  # Treat as config change to avoid state transitions
                self._last_config_update = now
                self._persistent_state["last_config_update"] = now
                _LOGGER.info("FIRST LOAD - Initializing without triggering state changes")
            elif current_today_hash != previous_today_hash or current_tomorrow_hash != previous_tomorrow_hash:
                price_data_changed = True
                self._last_price_update = now
                self._persistent_state["last_price_update"] = now
                _LOGGER.info("PRICE DATA CHANGED - This is a real update")
            elif previous_config_hash and current_config_hash != previous_config_hash:
                config_changed = True
                self._last_config_update = now
                self._persistent_state["last_config_update"] = now
                _LOGGER.info("CONFIG CHANGED - User updated settings")
            else:
                # Nothing changed - this is a scheduled update for time-based state changes
                scheduled_update = True
                _LOGGER.debug("SCHEDULED UPDATE - No price or config changes")

            # Store current price data and config hash for next comparison
            self._previous_raw_today = raw_today.copy() if raw_today else []
            self._previous_raw_tomorrow = raw_tomorrow.copy() if raw_tomorrow else []
            self._previous_config_hash = current_config_hash
            self._persistent_state["previous_raw_today"] = self._previous_raw_today
            self._persistent_state["previous_raw_tomorrow"] = self._previous_raw_tomorrow
            self._persistent_state["previous_config_hash"] = current_config_hash

            # Get solar forecast data if solar optimization is enabled
            solar_optimization_enabled = config.get("solar_optimization_enabled", False)
            if solar_optimization_enabled:
                solar_data = await self._get_solar_forecast_data()
                _LOGGER.debug(f"Solar optimization enabled, sensor available: {solar_data.get('sensor_available', False)}")
            else:
                solar_data = self._empty_solar_data()
                _LOGGER.debug("Solar optimization disabled, using empty solar data")

            # Process the data with metadata
            data = {
                "price_sensor": price_sensor,
                "raw_today": raw_today,
                "raw_tomorrow": raw_tomorrow,
                "tomorrow_valid": tomorrow_valid,
                "config": config,
                "last_update": now,
                # Layer 2: Change tracking metadata
                "price_data_changed": price_data_changed,
                "config_changed": config_changed,
                "is_first_load": is_first_load,
                "scheduled_update": scheduled_update,
                "last_price_update": self._last_price_update,
                "last_config_update": self._last_config_update,
                # Tibber action mode flag - indicates if prices are from tibber.get_prices action
                "tibber_action_mode": tibber_action_mode,
                # Solar forecast data
                "solar_forecast": solar_data.get("solar_forecast", []),
                "solar_forecast_today": solar_data.get("solar_forecast_today", []),
                "solar_forecast_tomorrow": solar_data.get("solar_forecast_tomorrow", []),
                "solar_total_today_wh": solar_data.get("total_today_wh", 0),
                "solar_total_tomorrow_wh": solar_data.get("total_tomorrow_wh", 0),
                "solar_sensor_available": solar_data.get("sensor_available", False),
                "solar_optimization_enabled": solar_optimization_enabled,
            }

            _LOGGER.debug(f"Data structure keys: {list(data.keys())}")
            _LOGGER.debug(f"Price data changed: {price_data_changed}")
            _LOGGER.debug(f"Config changed: {config_changed}")
            _LOGGER.debug("COORDINATOR UPDATE SUCCESS")
            _LOGGER.debug("="*60)
            return data

        except Exception as e:
            _LOGGER.error(f"COORDINATOR UPDATE FAILED: {e}", exc_info=True)
            _LOGGER.debug("="*60)
            raise UpdateFailed(f"Error fetching data: {e}") from e


    async def _get_configuration(self) -> Dict[str, Any]:
        """Get current configuration from config entry options.

        Reading from config_entry.options instead of entity states eliminates
        race conditions where entity states might be temporarily unavailable
        during updates.
        """
        from .const import (
            DEFAULT_CHARGING_WINDOWS,
            DEFAULT_EXPENSIVE_WINDOWS,
            DEFAULT_CHEAP_PERCENTILE,
            DEFAULT_EXPENSIVE_PERCENTILE,
            DEFAULT_MIN_SPREAD,
            DEFAULT_MIN_SPREAD_DISCHARGE,
            DEFAULT_AGGRESSIVE_DISCHARGE_SPREAD,
            DEFAULT_MIN_PRICE_DIFFERENCE,
            DEFAULT_ADDITIONAL_COST,
            DEFAULT_TAX,
            DEFAULT_VAT_RATE,
            DEFAULT_BATTERY_RTE,
            DEFAULT_CHARGE_POWER,
            DEFAULT_DISCHARGE_POWER,
            DEFAULT_PRICE_OVERRIDE_THRESHOLD,
            DEFAULT_QUIET_START,
            DEFAULT_QUIET_END,
            DEFAULT_TIME_OVERRIDE_START,
            DEFAULT_TIME_OVERRIDE_END,
            DEFAULT_CALCULATION_WINDOW_START,
            DEFAULT_CALCULATION_WINDOW_END,
            DEFAULT_BATTERY_MIN_SOC_DISCHARGE,
            DEFAULT_BATTERY_MIN_SOC_AGGRESSIVE_DISCHARGE,
        )

        options = self.config_entry.options

        _LOGGER.debug(f"Building config from options. calculation_window_enabled raw value: {options.get('calculation_window_enabled', 'NOT SET')}")

        # Number values with defaults
        config = {
            # Today's configuration
            "charging_windows": float(options.get("charging_windows", DEFAULT_CHARGING_WINDOWS)),
            "expensive_windows": float(options.get("expensive_windows", DEFAULT_EXPENSIVE_WINDOWS)),
            "cheap_percentile": float(options.get("cheap_percentile", DEFAULT_CHEAP_PERCENTILE)),
            "expensive_percentile": float(options.get("expensive_percentile", DEFAULT_EXPENSIVE_PERCENTILE)),
            "min_spread": float(options.get("min_spread", DEFAULT_MIN_SPREAD)),
            "min_spread_discharge": float(options.get("min_spread_discharge", DEFAULT_MIN_SPREAD_DISCHARGE)),
            "aggressive_discharge_spread": float(options.get("aggressive_discharge_spread", DEFAULT_AGGRESSIVE_DISCHARGE_SPREAD)),
            "min_price_difference": float(options.get("min_price_difference", DEFAULT_MIN_PRICE_DIFFERENCE)),
            "additional_cost": float(options.get("additional_cost", DEFAULT_ADDITIONAL_COST)),
            "tax": float(options.get("tax", DEFAULT_TAX)),
            "vat": float(options.get("vat", DEFAULT_VAT_RATE)),
            "battery_rte": float(options.get("battery_rte", DEFAULT_BATTERY_RTE)),
            "charge_power": float(options.get("charge_power", DEFAULT_CHARGE_POWER)),
            "discharge_power": float(options.get("discharge_power", DEFAULT_DISCHARGE_POWER)),
            "base_usage": float(options.get("base_usage", DEFAULT_BASE_USAGE)),
            "base_usage_charge_strategy": options.get("base_usage_charge_strategy", DEFAULT_BASE_USAGE_CHARGE_STRATEGY),
            "base_usage_idle_strategy": options.get("base_usage_idle_strategy", DEFAULT_BASE_USAGE_IDLE_STRATEGY),
            "base_usage_discharge_strategy": options.get("base_usage_discharge_strategy", DEFAULT_BASE_USAGE_DISCHARGE_STRATEGY),
            "base_usage_aggressive_strategy": options.get("base_usage_aggressive_strategy", DEFAULT_BASE_USAGE_AGGRESSIVE_STRATEGY),
            "price_override_threshold": float(options.get("price_override_threshold", DEFAULT_PRICE_OVERRIDE_THRESHOLD)),
            "battery_min_soc_discharge": float(options.get("battery_min_soc_discharge", DEFAULT_BATTERY_MIN_SOC_DISCHARGE)),
            "battery_min_soc_aggressive_discharge": float(options.get("battery_min_soc_aggressive_discharge", DEFAULT_BATTERY_MIN_SOC_AGGRESSIVE_DISCHARGE)),

            # Tomorrow's configuration
            "charging_windows_tomorrow": float(options.get("charging_windows_tomorrow", DEFAULT_CHARGING_WINDOWS)),
            "expensive_windows_tomorrow": float(options.get("expensive_windows_tomorrow", DEFAULT_EXPENSIVE_WINDOWS)),
            "cheap_percentile_tomorrow": float(options.get("cheap_percentile_tomorrow", DEFAULT_CHEAP_PERCENTILE)),
            "expensive_percentile_tomorrow": float(options.get("expensive_percentile_tomorrow", DEFAULT_EXPENSIVE_PERCENTILE)),
            "min_spread_tomorrow": float(options.get("min_spread_tomorrow", DEFAULT_MIN_SPREAD)),
            "min_spread_discharge_tomorrow": float(options.get("min_spread_discharge_tomorrow", DEFAULT_MIN_SPREAD_DISCHARGE)),
            "aggressive_discharge_spread_tomorrow": float(options.get("aggressive_discharge_spread_tomorrow", DEFAULT_AGGRESSIVE_DISCHARGE_SPREAD)),
            "min_price_difference_tomorrow": float(options.get("min_price_difference_tomorrow", DEFAULT_MIN_PRICE_DIFFERENCE)),
            "price_override_threshold_tomorrow": float(options.get("price_override_threshold_tomorrow", DEFAULT_PRICE_OVERRIDE_THRESHOLD)),

            # Boolean values (switches)
            "automation_enabled": bool(options.get("automation_enabled", True)),
            "tomorrow_settings_enabled": bool(options.get("tomorrow_settings_enabled", False)),
            "midnight_rotation_notifications": bool(options.get("midnight_rotation_notifications", False)),
            "notifications_enabled": bool(options.get("notifications_enabled", True)),
            "quiet_hours_enabled": bool(options.get("quiet_hours_enabled", False)),
            "price_override_enabled": bool(options.get("price_override_enabled", False)),
            "price_override_enabled_tomorrow": bool(options.get("price_override_enabled_tomorrow", False)),
            "time_override_enabled": bool(options.get("time_override_enabled", False)),
            "time_override_enabled_tomorrow": bool(options.get("time_override_enabled_tomorrow", False)),
            "calculation_window_enabled": bool(options.get("calculation_window_enabled", False)),
            "calculation_window_enabled_tomorrow": bool(options.get("calculation_window_enabled_tomorrow", False)),
            "notify_automation_disabled": bool(options.get("notify_automation_disabled", False)),
            "notify_charging": bool(options.get("notify_charging", True)),
            "notify_discharge": bool(options.get("notify_discharge", True)),
            "notify_discharge_aggressive": bool(options.get("notify_discharge_aggressive", True)),
            "notify_idle": bool(options.get("notify_idle", False)),

            # String values (selects)
            "pricing_window_duration": options.get("pricing_window_duration", "15_minutes"),
            "time_override_mode": options.get("time_override_mode", "charge"),
            "time_override_mode_tomorrow": options.get("time_override_mode_tomorrow", "charge"),

            # Solar optimization configuration
            "solar_optimization_enabled": bool(options.get("solar_optimization_enabled", DEFAULT_SOLAR_OPTIMIZATION_ENABLED)),
            "solar_forecast_sensor": options.get("solar_forecast_sensor", DEFAULT_SOLAR_FORECAST_SENSOR),
            "solar_forecast_sensors_today": list(options.get("solar_forecast_sensors_today", DEFAULT_SOLAR_FORECAST_SENSORS_TODAY)),
            "solar_forecast_sensors_tomorrow": list(options.get("solar_forecast_sensors_tomorrow", DEFAULT_SOLAR_FORECAST_SENSORS_TOMORROW)),
            "battery_usable_capacity": float(options.get("battery_usable_capacity", 10.0)),
            "skip_charge_solar_threshold": float(options.get("skip_charge_solar_threshold", 80)),
            "consumption_estimate": float(options.get("consumption_estimate", 500)),

            # Time values
            "time_override_start": options.get("time_override_start", DEFAULT_TIME_OVERRIDE_START),
            "time_override_end": options.get("time_override_end", DEFAULT_TIME_OVERRIDE_END),
            "time_override_start_tomorrow": options.get("time_override_start_tomorrow", DEFAULT_TIME_OVERRIDE_START),
            "time_override_end_tomorrow": options.get("time_override_end_tomorrow", DEFAULT_TIME_OVERRIDE_END),
            "calculation_window_start": options.get("calculation_window_start", DEFAULT_CALCULATION_WINDOW_START),
            "calculation_window_end": options.get("calculation_window_end", DEFAULT_CALCULATION_WINDOW_END),
            "calculation_window_start_tomorrow": options.get("calculation_window_start_tomorrow", DEFAULT_CALCULATION_WINDOW_START),
            "calculation_window_end_tomorrow": options.get("calculation_window_end_tomorrow", DEFAULT_CALCULATION_WINDOW_END),
            "quiet_hours_start": options.get("quiet_hours_start", DEFAULT_QUIET_START),
            "quiet_hours_end": options.get("quiet_hours_end", DEFAULT_QUIET_END),
        }

        return config

    async def async_request_refresh(self) -> None:
        """Request an immediate coordinator refresh."""
        _LOGGER.debug("Refresh requested, executing immediately")
        # Call the parent's async_refresh() to fetch new data and update sensors
        await super(CEWCoordinator, self).async_refresh()

    def get_config_value(self, key: str, default: Any = None) -> Any:
        """Get a configuration value from the coordinator data."""
        if self.data and "config" in self.data:
            return self.data["config"].get(key, default)
        return default

    async def _empty_data(self, reason: str) -> Dict[str, Any]:
        """Return empty data structure when price sensor is not available."""
        # Still get config so settings are available
        config = await self._get_configuration()

        return {
            "price_sensor": None,
            "raw_today": [],
            "raw_tomorrow": [],
            "tomorrow_valid": False,
            "config": config,
            "last_update": dt_util.now(),
            "error": reason,
            # Tibber action mode - False when empty/error data
            "tibber_action_mode": False,
            # Solar forecast data - empty when price sensor not available
            "solar_forecast": [],
            "solar_forecast_today": [],
            "solar_forecast_tomorrow": [],
            "solar_total_today_wh": 0,
            "solar_total_tomorrow_wh": 0,
            "solar_sensor_available": False,
            "solar_optimization_enabled": config.get("solar_optimization_enabled", False),
        }

    async def _get_solar_forecast_data(self) -> Dict[str, Any]:
        """Get solar forecast data from multiple Forecast.Solar sensors.

        Retrieves data from the configured Forecast.Solar sensors and aggregates
        them by summing Wh values for matching timestamps.

        Supports both new multi-sensor configuration (solar_forecast_sensors_today,
        solar_forecast_sensors_tomorrow) and legacy single sensor configuration
        (solar_forecast_sensor) for backward compatibility.

        Returns:
            Dict containing:
                - solar_forecast: List of dicts with timestamp, watts, wh (combined)
                - solar_forecast_today: Filtered list for today only
                - solar_forecast_tomorrow: Filtered list for tomorrow only
                - total_today_wh: Total Wh forecast for today
                - total_tomorrow_wh: Total Wh forecast for tomorrow
                - sensor_available: Boolean indicating if any sensor data is available
        """
        options = self.config_entry.options
        solar_enabled = options.get("solar_optimization_enabled", DEFAULT_SOLAR_OPTIMIZATION_ENABLED)

        # Return empty data if solar optimization is disabled
        if not solar_enabled:
            _LOGGER.debug("Solar optimization disabled")
            return self._empty_solar_data()

        # Get sensor lists from new multi-sensor config
        sensors_today = list(options.get("solar_forecast_sensors_today", DEFAULT_SOLAR_FORECAST_SENSORS_TODAY))
        sensors_tomorrow = list(options.get("solar_forecast_sensors_tomorrow", DEFAULT_SOLAR_FORECAST_SENSORS_TOMORROW))

        # Backward compatibility: if new config is empty, check for legacy single sensor
        legacy_sensor = options.get("solar_forecast_sensor", DEFAULT_SOLAR_FORECAST_SENSOR)
        if not sensors_today and not sensors_tomorrow and legacy_sensor:
            _LOGGER.debug(f"Using legacy single sensor config: {legacy_sensor}")
            # Legacy sensor typically provides both today and tomorrow data
            sensors_today = [legacy_sensor]
            sensors_tomorrow = [legacy_sensor]

        # Return empty data if no sensors configured
        if not sensors_today and not sensors_tomorrow:
            _LOGGER.debug("No solar forecast sensors configured")
            return self._empty_solar_data()

        now = dt_util.now()
        today = now.date()
        tomorrow = today + timedelta(days=1)

        # Aggregate data from today sensors
        aggregated_today = await self._aggregate_solar_sensors(sensors_today, today)
        _LOGGER.debug(f"Aggregated today data from {len(sensors_today)} sensors: {len(aggregated_today)} entries")

        # Aggregate data from tomorrow sensors
        aggregated_tomorrow = await self._aggregate_solar_sensors(sensors_tomorrow, tomorrow)
        _LOGGER.debug(f"Aggregated tomorrow data from {len(sensors_tomorrow)} sensors: {len(aggregated_tomorrow)} entries")

        # Combine all forecast data
        solar_forecast = aggregated_today + aggregated_tomorrow
        solar_forecast.sort(key=lambda x: x["timestamp"])

        # Filter by day for clarity
        solar_forecast_today = [
            entry for entry in solar_forecast
            if entry["timestamp"].date() == today
        ]
        solar_forecast_tomorrow = [
            entry for entry in solar_forecast
            if entry["timestamp"].date() == tomorrow
        ]

        # Calculate daily totals
        total_today_wh = sum(entry["wh"] for entry in solar_forecast_today)
        total_tomorrow_wh = sum(entry["wh"] for entry in solar_forecast_tomorrow)

        sensor_available = len(solar_forecast_today) > 0 or len(solar_forecast_tomorrow) > 0

        _LOGGER.debug(f"Solar forecast entries: {len(solar_forecast)}")
        _LOGGER.debug(f"Solar forecast today entries: {len(solar_forecast_today)}")
        _LOGGER.debug(f"Solar forecast tomorrow entries: {len(solar_forecast_tomorrow)}")
        _LOGGER.debug(f"Total today Wh: {total_today_wh}, Total tomorrow Wh: {total_tomorrow_wh}")

        return {
            "solar_forecast": solar_forecast,
            "solar_forecast_today": solar_forecast_today,
            "solar_forecast_tomorrow": solar_forecast_tomorrow,
            "total_today_wh": total_today_wh,
            "total_tomorrow_wh": total_tomorrow_wh,
            "sensor_available": sensor_available,
        }

    async def _aggregate_solar_sensors(
        self, sensor_ids: list[str], target_date
    ) -> list[Dict[str, Any]]:
        """Aggregate solar forecast data from multiple sensors for a specific date.

        Args:
            sensor_ids: List of sensor entity IDs to aggregate
            target_date: The date to filter forecast data for

        Returns:
            List of dicts with timestamp, watts, wh - aggregated across all sensors
        """
        if not sensor_ids:
            return []

        # Dict to aggregate values by timestamp: timestamp_iso -> {watts: float, wh: float}
        aggregated: Dict[str, Dict[str, float]] = {}

        for sensor_id in sensor_ids:
            if not sensor_id:
                continue

            sensor_data = await self._get_single_sensor_forecast(sensor_id, target_date)

            for entry in sensor_data:
                # Use ISO format string as key for aggregation
                ts_key = entry["timestamp"].isoformat()

                if ts_key not in aggregated:
                    aggregated[ts_key] = {
                        "timestamp": entry["timestamp"],
                        "watts": 0.0,
                        "wh": 0.0,
                    }

                # Sum values from this sensor
                aggregated[ts_key]["watts"] += entry["watts"]
                aggregated[ts_key]["wh"] += entry["wh"]

        # Convert back to list format
        result = [
            {
                "timestamp": data["timestamp"],
                "watts": data["watts"],
                "wh": data["wh"],
            }
            for data in aggregated.values()
        ]

        # Sort by timestamp
        result.sort(key=lambda x: x["timestamp"])

        return result

    async def _get_single_sensor_forecast(
        self, sensor_id: str, target_date
    ) -> list[Dict[str, Any]]:
        """Get solar forecast data from a single Forecast.Solar sensor.

        Args:
            sensor_id: The sensor entity ID
            target_date: The date to filter forecast data for

        Returns:
            List of dicts with timestamp, watts, wh for the target date
        """
        # Get the solar forecast sensor state
        solar_state = self.hass.states.get(sensor_id)

        if not solar_state:
            _LOGGER.warning(f"Solar forecast sensor {sensor_id} not found")
            return []

        if solar_state.state in ("unavailable", "unknown"):
            _LOGGER.debug(f"Solar forecast sensor {sensor_id} is {solar_state.state}")
            return []

        _LOGGER.debug(f"Solar forecast sensor {sensor_id} state: {solar_state.state}")

        # Extract forecast data from sensor attributes
        # Forecast.Solar provides data in several formats:
        # - watts: dict of timestamp -> instantaneous watts
        # - wh_period: dict of timestamp -> Wh for each period
        watts_data = solar_state.attributes.get("watts", {})
        wh_period_data = solar_state.attributes.get("wh_period", {})

        # Parse and filter forecast data for target date
        result = []

        # Use wh_period data (preferred) or watts data
        data_source = wh_period_data if wh_period_data else watts_data

        for timestamp_str, value in data_source.items():
            try:
                # Parse timestamp - Forecast.Solar uses local timezone
                if isinstance(timestamp_str, str):
                    # Try ISO format first
                    try:
                        timestamp = datetime.fromisoformat(timestamp_str)
                    except ValueError:
                        # Try parsing as datetime string
                        timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")

                    # Ensure timezone awareness
                    if timestamp.tzinfo is None:
                        timestamp = dt_util.as_local(timestamp)
                else:
                    timestamp = timestamp_str

                # Filter for target date only
                if timestamp.date() != target_date:
                    continue

                # Get watts and wh values
                wh_value = wh_period_data.get(timestamp_str, 0) if wh_period_data else 0
                watts_value = watts_data.get(timestamp_str, 0) if watts_data else value

                # Handle potential non-numeric values
                try:
                    wh_value = float(wh_value) if wh_value else 0
                    watts_value = float(watts_value) if watts_value else 0
                except (ValueError, TypeError):
                    wh_value = 0
                    watts_value = 0

                result.append({
                    "timestamp": timestamp,
                    "watts": watts_value,
                    "wh": wh_value,
                })

            except (ValueError, TypeError) as e:
                _LOGGER.debug(f"Error parsing solar forecast timestamp {timestamp_str}: {e}")
                continue

        return result

    def _empty_solar_data(self) -> Dict[str, Any]:
        """Return empty solar forecast data structure."""
        return {
            "solar_forecast": [],
            "solar_forecast_today": [],
            "solar_forecast_tomorrow": [],
            "total_today_wh": 0,
            "total_tomorrow_wh": 0,
            "sensor_available": False,
        }