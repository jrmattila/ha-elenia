import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS, UPDATE_INTERVAL
from .elenia_data import EleniaData

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = UPDATE_INTERVAL

async def async_setup(hass: HomeAssistant, config: dict):
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    try:
        elenia_data = EleniaData(hass, entry.data, _LOGGER)
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = elenia_data

        await elenia_data.ensure_authenticated()

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        return True
    except Exception as e:
        _LOGGER.error("Failed to set up Elenia integration: %s", str(e))
        return False


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
