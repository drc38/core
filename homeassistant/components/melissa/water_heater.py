"""Support for Melissa Climate A/C."""
from __future__ import annotations

import asyncio
import logging

from homeassistant.components.water_heater import (
    STATE_ECO,
    STATE_ELECTRIC,
    WaterHeaterEntity,
)
from homeassistant.const import STATE_OFF, STATE_UNKNOWN, TEMP_CELSIUS
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.temperature import display_temp as show_temp
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from . import DATA_MELISSA

_LOGGER = logging.getLogger(__name__)

SUPPORT_FLAGS = 0
ATTR_HOT = "hot"
ATTR_COLD = "cold"
ATTR_HOME = "home"
ATTR_ENERGY = "energy"
ATTR_VOLTAGE = "voltage"
ATTR_CURRENT = "current"
ATTR_RELAY = "relay_state"
ATTR_LOAD = "load"
ATTR_SETPOINT = "energy_fix_setpoint"


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Iterate through and add all Melissa devices."""
    api = hass.data[DATA_MELISSA]
    devices = (await api.async_fetch_devices()).values()

    all_devices = []

    for device in devices:
        if device["type"] == "bobbie":
            all_devices.append(BobbieWaterHeater(api, device["serial_number"], device))

    async_add_entities(all_devices)


class BobbieWaterHeater(WaterHeaterEntity):
    """Representation of a Bobbie Water Heater device."""

    def __init__(self, api, serial_number, init_data):
        """Initialize the water heater device."""
        self._name = init_data["name"]
        self._api = api
        self._serial_number = serial_number
        self._data = init_data
        self._state = None
        self._cur_settings = None
        self._status_data = None
        self._attr_available = init_data.get("online", False)
        _LOGGER.debug("Initial data: %s", self._data)
        self.async_update()

    @property
    def name(self):
        """Return the name of the thermostat, if any."""
        return self._name

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if self._cur_settings is not None:
            self._attr_available = self._cur_settings.get("online", False)
        return self._attr_available

    @property
    def current_temperature(self):
        """Return the current temperature."""
        if self._status_data is not None:
            return self._status_data.get(ATTR_HOT, 0)

    @property
    def current_operation(self) -> str | None:
        """Return current operation ie. eco, electric, performance, ..."""
        if self._status_data is None:
            self._attr_current_operation = STATE_UNKNOWN
        elif self._status_data[ATTR_RELAY] is False:
            self._attr_current_operation = STATE_OFF
        elif self._status_data[ATTR_LOAD] is False:
            # relay is on but cylinder is at setpoint, so no power flowing
            self._attr_current_operation = STATE_ECO
        elif self._status_data[ATTR_LOAD] is True:
            self._attr_current_operation = STATE_ELECTRIC
        return self._attr_current_operation

    @property
    def temperature_unit(self):
        """Return the unit of measurement which this heater uses."""
        return TEMP_CELSIUS

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return SUPPORT_FLAGS

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        if self._status_data is None:
            data = {}
        else:
            data = {
                ATTR_COLD: show_temp(
                    self.hass,
                    self._status_data[ATTR_COLD],
                    self.temperature_unit,
                    self.precision,
                ),
                ATTR_HOT: show_temp(
                    self.hass,
                    self._status_data[ATTR_HOT],
                    self.temperature_unit,
                    self.precision,
                ),
                ATTR_HOME: show_temp(
                    self.hass,
                    self._status_data[ATTR_HOME],
                    self.temperature_unit,
                    self.precision,
                ),
                ATTR_ENERGY: self._status_data[ATTR_ENERGY],
                ATTR_VOLTAGE: self._status_data[ATTR_VOLTAGE],
                ATTR_CURRENT: self._status_data[ATTR_CURRENT],
                ATTR_RELAY: self._status_data[ATTR_RELAY],
                ATTR_LOAD: self._status_data[ATTR_LOAD],
            }
        return data

    async def async_turn_on(self):
        """Turn on Bobbie relay."""
        await self._api.async_send(
            self._serial_number, device_type="bobbie", state_data=None
        )
        await asyncio.sleep(10)
        await self.async_update()

    async def async_turn_off(self):
        """Turn off Bobbie relay."""
        await self._api.async_send(
            self._serial_number, device_type="bobbie", state_data={"state": "off"}
        )
        await asyncio.sleep(10)
        await self.async_update()

    async def async_update(self):
        """Get latest data from Bobbie."""
        try:
            self._status_data = (await self._api.async_status(cached=True))[
                self._serial_number
            ]
            _LOGGER.debug("Status: %s", self._status_data)
            self._cur_settings = (
                await self._api.async_cur_settings(self._serial_number)
            )["controller"]
            _LOGGER.debug("Current settings: %s", self._cur_settings)
        except KeyError:
            _LOGGER.warning("Unable to update entity %s", self.entity_id)
