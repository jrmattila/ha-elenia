import logging
from datetime import datetime, timezone
from typing import Literal

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.components.sensor import (
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.const import UnitOfEnergy
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, format_mac

from .const import DOMAIN, UPDATE_INTERVAL, CONF_GSRN, CONF_CUSTOMER_ID
from .elenia_data import Measurements

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    elenia_data = hass.data[DOMAIN][entry.entry_id]

    async def async_update_data():
        data: Measurements = await elenia_data.fetch_5min_readings()
        if data is None:
            raise UpdateFailed("Failed to fetch data")
        return data

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="Elenia",
        update_method=async_update_data,
        update_interval=UPDATE_INTERVAL,
    )

    await coordinator.async_config_entry_first_refresh()

    async_add_entities(
        [
            EleniaSensor(coordinator, entry, elenia_data, "a"),
            EleniaSensor(coordinator, entry, elenia_data, "a1"),
            EleniaSensor(coordinator, entry, elenia_data, "a2"),
            EleniaSensor(coordinator, entry, elenia_data, "a3"),
        ],
        False,
    )


class EleniaSensor(CoordinatorEntity):
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
        return (
            f"elenia_energy_{self.entry.data[CONF_GSRN]}_${self.measurement_attribute}"
        )

    @property
    def state(self):
        data: Measurements = self.coordinator.data
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
