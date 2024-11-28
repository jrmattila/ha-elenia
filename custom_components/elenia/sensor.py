from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import Literal

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, format_mac
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CUSTOMER_ID,
    CONF_GSRN,
    DOMAIN,
    UPDATE_INTERVAL,
    CONF_PRICE_SENSOR_FOR_EACH_HOUR,
    CONF_RELAY_SENSOR_FOR_EACH_HOUR,
)
from .elenia_data import EleniaData, Measurements
from .types import RelayData, RelayMarketDataList

_LOGGER = logging.getLogger(__name__)


@dataclass
class CoordinatorData:
    consumption_data: Measurements
    relay_schedule_data: RelayData
    relay1_market_data: RelayMarketDataList
    relay2_market_data: RelayMarketDataList


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    elenia_data: EleniaData = hass.data[DOMAIN][entry.entry_id]

    async def async_update_data():
        consumption_data: Measurements = await elenia_data.fetch_5min_readings()
        if consumption_data is None:
            raise UpdateFailed("Failed to fetch consumption data")
        relay_schedule_data = await elenia_data.fetch_relay_schedule()
        if relay_schedule_data is None:
            raise UpdateFailed("Failed to fetch relay data")
        relay1_market_data = await elenia_data.fetch_relay_market(1)
        if relay1_market_data is None:
            raise UpdateFailed("Failed to fetch relay1 market data")
        relay2_market_data = await elenia_data.fetch_relay_market(2)
        if relay2_market_data is None:
            raise UpdateFailed("Failed to fetch relay2 market data")

        return CoordinatorData(
            consumption_data,
            relay_schedule_data,
            relay1_market_data,
            relay2_market_data,
        )

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="Elenia",
        update_method=async_update_data,
        update_interval=UPDATE_INTERVAL,
    )

    await coordinator.async_config_entry_first_refresh()

    relay1_hour_sensors = []
    relay2_hour_sensors = []
    price_hour_sensors = []

    for hour in range(24):
        if entry.data[CONF_RELAY_SENSOR_FOR_EACH_HOUR] is True:
            relay1_hour_sensors.append(
                RelaySensor(coordinator, entry, elenia_data, 1, hour)
            )
            relay2_hour_sensors.append(
                RelaySensor(coordinator, entry, elenia_data, 2, hour)
            )
        if entry.data[CONF_PRICE_SENSOR_FOR_EACH_HOUR] is True:
            price_hour_sensors.append(
                PriceSensor(coordinator, entry, elenia_data, "total", hour)
            )

    async_add_entities(
        [
            ConsumptionSensor(coordinator, entry, elenia_data, "a"),
            ConsumptionSensor(coordinator, entry, elenia_data, "a1"),
            ConsumptionSensor(coordinator, entry, elenia_data, "a2"),
            ConsumptionSensor(coordinator, entry, elenia_data, "a3"),
            RelaySensor(coordinator, entry, elenia_data, 1),
            RelaySensor(coordinator, entry, elenia_data, 2),
            PriceSensor(coordinator, entry, elenia_data, "total"),
            PriceSensor(coordinator, entry, elenia_data, "prices"),
            PriceSensor(coordinator, entry, elenia_data, "distribution_prices"),
            *relay1_hour_sensors,
            *relay2_hour_sensors,
            *price_hour_sensors,
        ],
        False,
    )


class PriceSensor(CoordinatorEntity):
    def __init__(
        self,
        coordinator: DataUpdateCoordinator[CoordinatorData],
        entry,
        elenia_data,
        price_type: Literal["prices", "distribution_prices", "total"],
        hour: int | None = None,
    ) -> None:
        super().__init__(coordinator)
        self.hour = hour
        self.price_type = price_type
        self._name = self.resolve_name(price_type, hour)
        self.entry = entry
        self.elenia_data = elenia_data
        self.coordinator = coordinator
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_unit_of_measurement = "cent"

    # for future-proofing unique id, if offets are implemented
    @property
    def name(self):
        return self._name

    @property
    def unique_id(self):
        return f"elenia_{self.entry.data[CONF_GSRN]}_price_{self.price_type}_{'now' if self.hour is None else f'hour {self.hour}'}"

    @property
    def state(self):
        return (
            (self.resolve_price("prices") + self.resolve_price("distribution_prices"))
            if self.price_type == "total"
            else self.resolve_price(self.price_type)
        )

    def resolve_name(
        self,
        price_type: Literal["prices", "distribution_prices", "total"],
        hour: int | None,
    ):
        name_suffix = "now" if hour is None else f"hour {hour}"
        match price_type:
            case "prices":
                return f"Spot price {name_suffix}"
            case "distribution_prices":
                return f"Distribution price {name_suffix}"
            case "total":
                return f"Price now {name_suffix}"
            case _:
                raise Exception(f"Price type not supported, got {price_type}")

    def resolve_price(
        self, price_type: Literal["prices", "distribution_prices", "total"]
    ):
        relay_market_data = self.coordinator.data.relay2_market_data.data
        today = dt_util.now().strftime("%Y-%m-%d")

        today_prices = next(
            (
                t_prices
                for t_prices in relay_market_data
                if t_prices.get("day") == today
            ),
            None,
        )

        hour = self.hour if self.hour is not None else dt_util.now().hour
        # _LOGGER.debug(f"Showing price for hour {hour}")
        return today_prices[price_type][hour]


class RelaySensor(BinarySensorEntity, CoordinatorEntity):
    def __init__(
        self,
        coordinator: DataUpdateCoordinator[CoordinatorData],
        entry,
        elenia_data,
        relay_instance: Literal[1, 2],
        hour: int | None = None,
        day_offset: Literal[-2, -1, 0] = 0,
    ):
        super().__init__(coordinator)
        name_suffix = f"hour {hour}" if hour is not None else "now"
        self._name = f"Relay {relay_instance} {name_suffix}"
        self.entry = entry
        self.coordinator = coordinator
        self.elenia_data = elenia_data
        self.relay_instance = relay_instance
        self.relay_market_data = (
            self.coordinator.data.relay1_market_data.data
            if relay_instance == 1
            else self.coordinator.data.relay2_market_data.data
        )
        self.hour = hour
        # for future-proofing unique id, if offets are implemented
        self.day_offset = day_offset

    @property
    def name(self):
        return self._name

    @property
    def unique_id(self):
        return f"elenia_{self.entry.data[CONF_GSRN]}_relay_{self.relay_instance}_hour_{self.hour if self.hour is not None else 'current'}_{self.day_offset}"

    @property
    def is_on(self):
        return self.is_relay_enabled()

    def is_relay_enabled(self):
        day = dt_util.now().strftime("%Y-%m-%d")
        hour = self.hour or dt_util.now().hour

        _LOGGER.debug(
            f"Looking for relay info for day: {day}, hour: {hour} for relay {self.relay_instance}"
        )

        market_data_for_today = next(
            (rd for rd in self.relay_market_data if rd.get("day") == day), None
        )

        if not market_data_for_today:
            _LOGGER.debug(
                f"Couldn't find market data for today for relay {self.relay_instance}"
            )
            return None
        if not market_data_for_today.get("hours_on"):
            _LOGGER.debug("No hours_on-attribute on today's market data")
            return None

        is_toggled = hour in market_data_for_today.get("hours_on")
        _LOGGER.debug(f"Relay state found: {is_toggled}")

        return is_toggled

class ConsumptionSensor(CoordinatorEntity):
    def __init__(
        self,
        coordinator,
        entry,
        elenia_data,
        measurement_attribute: Literal["a", "a1", "a2", "a3"],
    ):
        super().__init__(coordinator)
        self.entry = entry
        self.elenia_data = elenia_data
        self.measurement_attribute = measurement_attribute
        self._name = self.get_name(measurement_attribute)
        self._unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._latest_measurement_time = None
        self._latest_measurement = None
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING

    def get_name(self, measurement_attribute: Literal["a", "a1", "a2", "a3"]):
        match measurement_attribute:
            case "a":
                return "Electric consumption total"
            case "a1":
                return "Electric consumption phase 1"
            case "a2":
                return "Electric consumption phase 2"
            case "a3":
                return "Electric consumption phase 3"

    @property
    def name(self):
        return self._name

    @property
    def unique_id(self):
        return f"elenia_{self.entry.data[CONF_GSRN]}_{self.measurement_attribute}"

    @property
    def state(self):
        data: Measurements = self.coordinator.data.consumption_data
        if data:
            try:
                latest_measurement = data[-1]
                latest_time_str = latest_measurement.get("dt")
                entry_time = (
                    datetime.strptime(latest_time_str, "%Y-%m-%dT%H:%M:%S").replace(
                        tzinfo=timezone.utc
                    )
                    if latest_time_str
                    else None
                )

                self._latest_measurement_time = entry_time
                self._latest_measurement = latest_measurement

                _LOGGER.debug("Latest data timestamp: %s", entry_time)
                raw_value = latest_measurement.get(self.measurement_attribute)
                if raw_value is None:
                    _LOGGER.error("Could not get latest measurement")
                    return None

                value = int(raw_value) / 1000
                if value is not None:
                    return value
                else:
                    _LOGGER.error("Could not parse latest measurement")
                    return None

            except Exception as e:
                _LOGGER.error("Error processing data: %s", str(e))
                return None
        return None

    @property
    def unit_of_measurement(self):
        return self._unit_of_measurement

    @property
    def extra_state_attributes(self):
        attrs = {
            "customer_id": self.entry.data[CONF_CUSTOMER_ID],
            "gsrn": self.entry.data[CONF_GSRN],
        }
        if self._latest_measurement:
            attrs["latest_measurement_time"] = self._latest_measurement
        if self._latest_measurement_time:
            attrs["latest_measurement_time"] = self._latest_measurement_time.isoformat()
        return attrs

    @property
    def device_info(self) -> DeviceInfo:
        customer_id = self.entry.data[CONF_CUSTOMER_ID]
        gsrn = self.entry.data[CONF_GSRN]
        meteringpoints = self.elenia_data.customer_data.get(customer_id, {}).get(
            "meteringpoints", []
        )
        meteringpoint = next(
            (mp for mp in meteringpoints if mp.get("gsrn") == gsrn), None
        )
        product_description = meteringpoint.get("productcode_description", "")
        default_manufacturer = f"Elenia, {product_description}"
        default_model = meteringpoint.get("device").get("name")

        return DeviceInfo(
            connections={(CONNECTION_NETWORK_MAC, format_mac(gsrn))},
            manufacturer=default_manufacturer,
            model=default_model,
            name="Elenia",
            identifiers={(DOMAIN, gsrn)},
            via_device=(DOMAIN, format_mac(gsrn)),
        )
