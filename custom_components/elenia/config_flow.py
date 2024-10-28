import logging

import voluptuous as vol
import aiohttp
import async_timeout

from homeassistant import config_entries
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD

from .const import (
    DOMAIN,
    AUTH_URL,
    CUSTOMER_DATA_URL,
    CONF_CUSTOMER_ID,
    CONF_GSRN,
)

_LOGGER = logging.getLogger(__name__)

class EleniaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):

    VERSION = 1

    def __init__(self):
        self.credentials = {}
        self.customer_data = {}
        self.elenia_api = None

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            self.credentials = user_input
            self.elenia_api = EleniaAPI(user_input[CONF_USERNAME], user_input[CONF_PASSWORD])
            try:
                await self.elenia_api.authenticate()
                customer_data = await self.elenia_api.fetch_customer_data_and_token()
                self.customer_data = customer_data
                return await self.async_step_select_metering_point()
            except Exception as e:
                _LOGGER.error("Authentication failed: %s", str(e))
                errors["base"] = "auth"

        data_schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=data_schema, errors=errors)

    async def async_step_select_metering_point(self, user_input=None):
        errors = {}
        if user_input is not None:
            metering_point = user_input["metering_point"]
            customer_id, gsrn = metering_point.split(":")
            data = {
                CONF_USERNAME: self.credentials[CONF_USERNAME],
                CONF_PASSWORD: self.credentials[CONF_PASSWORD],
                CONF_CUSTOMER_ID: customer_id,
                CONF_GSRN: gsrn,
            }
            await self.elenia_api.close()
            return self.async_create_entry(title="Elenia", data=data)

        metering_points = {}
        customer_datas = self.customer_data.get("customer_datas", {})
        for customer_id, data in customer_datas.items():
            for point in data.get("meteringpoints", []):
                address = point["address"]["streetaddress"]
                fusesize = point["productcode_description"]
                gsrn = point["gsrn"]
                key = f"{customer_id}:{gsrn}"
                display_name = f"{address}, {fusesize}, {gsrn}"
                metering_points[key] = display_name

        if not metering_points:
            errors["base"] = "no_metering_points"
            return self.async_show_form(step_id="select_metering_point", errors=errors)

        data_schema = vol.Schema(
            {
                vol.Required("metering_point"): vol.In(metering_points),
            }
        )
        return self.async_show_form(step_id="select_metering_point", data_schema=data_schema, errors=errors)


class EleniaAPI:
    AUTH_URL = AUTH_URL
    CUSTOMER_DATA_URL = CUSTOMER_DATA_URL

    def __init__(self, username, password):
        """Initialize."""
        self.username = username
        self.password = password
        self.tokens = {}
        self.session = aiohttp.ClientSession()
        self.authenticated = False

    async def authenticate(self):
        """Authenticate and obtain tokens."""
        payload = {
            "AuthFlow": "USER_PASSWORD_AUTH",
            "ClientId": "k4s2pnm04536t1bm72bdatqct",
            "AuthParameters": {
                "USERNAME": self.username,
                "PASSWORD": self.password,
            },
            "ClientMetadata": {},
        }
        headers = {
            "Content-Type": "application/x-amz-json-1.1",
            "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth",
        }
        try:
            async with async_timeout.timeout(10):
                async with self.session.post(
                    self.AUTH_URL, json=payload, headers=headers
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        self.tokens = data["AuthenticationResult"]
                        self.authenticated = True
                        _LOGGER.debug("Authentication successful in config flow")
                    else:
                        error_text = await resp.text()
                        _LOGGER.error(
                            "Authentication failed: %s - %s", resp.status, error_text
                        )
                        raise Exception("Authentication failed")
        except Exception as e:
            _LOGGER.error("Exception during authentication: %s", str(e))
            raise

    async def fetch_customer_data_and_token(self):
        """Fetch customer data and get the token. This is a separate token to access metering data. """
        if not self.authenticated:
            await self.authenticate()
        headers = {
            "Authorization": f"Bearer {self.tokens.get('IdToken')}"
        }
        try:
            async with async_timeout.timeout(10):
                async with self.session.get(
                    self.CUSTOMER_DATA_URL, headers=headers
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self.customer_token = data.get("token")
                        if not self.customer_token:
                            _LOGGER.error("No token found in customer data")
                            raise Exception("No token in customer data")
                        return data
                    else:
                        error_text = await resp.text()
                        _LOGGER.error(
                            "Failed to fetch customer data: %s - %s",
                            resp.status,
                            error_text,
                        )
                        raise Exception("Failed to fetch customer data")
        except Exception as e:
            _LOGGER.error("Exception during customer data fetch: %s", str(e))
            raise

    async def close(self):
        await self.session.close()
