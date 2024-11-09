from datetime import datetime, timedelta
from logging import Logger

import async_timeout
from homeassistant.util import dt as dt_util
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from .const import (
    CONF_GSRN,
    CONF_CUSTOMER_ID,
    AUTH_CLIENT_ID,
    RELAY_CONTROL_URL,
    UPDATE_INTERVAL,
)
from custom_components.elenia import AUTH_URL, CUSTOMER_DATA_URL, METER_READING_URL
import aiohttp
from homeassistant.core import HomeAssistant

from .types import (
    Measurements,
    RelayData,
    parse_relay,
)
from pydantic import ValidationError


class EleniaData:
    """Class to manage fetching data from Elenia API."""

    def __init__(self, hass: HomeAssistant, config, logger: Logger):
        """Initialize the data object."""
        self.hass = hass
        self.username = config[CONF_USERNAME]
        self.password = config[CONF_PASSWORD]
        self.customer_id = config[CONF_CUSTOMER_ID]
        self.gsrn = config[CONF_GSRN]
        self.session = aiohttp.ClientSession()
        self.tokens = {}
        self.authenticated = False
        self.token_expiration = datetime.utcnow()
        self.customer_token = None  # The token from customer_data_and_token
        self.customer_token_expiry = datetime.utcnow()
        self.logger = logger
        self.customer_data = None  # set from customer_data
        self.meteringpoint = None  # set from customer_data
        self.serialnumber = None  # set from customer_data

    async def authenticate(self):
        """Authenticate with AWS Cognito and store tokens."""
        payload = {
            "AuthFlow": "USER_PASSWORD_AUTH",
            "ClientId": AUTH_CLIENT_ID,
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
                    AUTH_URL, json=payload, headers=headers
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        auth_result = data["AuthenticationResult"]
                        self.tokens = {
                            "AccessToken": auth_result["AccessToken"],
                            "IdToken": auth_result["IdToken"],
                            "RefreshToken": auth_result.get("RefreshToken"),
                        }
                        expires_in = auth_result["ExpiresIn"]
                        self.token_expiration = await self.resolve_expiration_time(
                            expires_in
                        )
                        self.authenticated = True
                        self.logger.debug("Authentication successful")
                    else:
                        error_text = await resp.text()
                        self.logger.error(
                            "Authentication failed: %s - %s", resp.status, error_text
                        )
                        raise Exception("Authentication failed")
        except Exception as e:
            self.logger.error("Exception during authentication: %s", str(e))
            raise

    async def refresh_token(self):
        """Refresh the tokens using the REFRESH_TOKEN_AUTH flow."""
        if not self.tokens.get("RefreshToken"):
            self.logger.debug("No refresh token available to refresh tokens")
            await self.authenticate()
            return

        payload = {
            "AuthFlow": "REFRESH_TOKEN_AUTH",
            "ClientId": AUTH_CLIENT_ID,
            "AuthParameters": {
                "REFRESH_TOKEN": self.tokens["RefreshToken"],
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
                    AUTH_URL, json=payload, headers=headers
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        auth_result = data["AuthenticationResult"]
                        self.tokens["AccessToken"] = auth_result["AccessToken"]
                        self.tokens["IdToken"] = auth_result["IdToken"]

                        expires_in = auth_result["ExpiresIn"]
                        self.token_expiration = await self.resolve_expiration_time(
                            expires_in
                        )
                        self.authenticated = True
                        self.logger.debug("Token refresh successful")
                    else:
                        error_text = await resp.text()
                        self.logger.debug(
                            "Token refresh failed: %s - %s", resp.status, error_text
                        )
                        # If refresh fails, re-authenticate
                        await self.authenticate()
        except Exception as e:
            self.logger.debug(
                "Exception during token refresh, retrying authentication: %s", str(e)
            )
            # If an exception occurs, re-authenticate
            await self.authenticate()

    async def resolve_expiration_time(self, expires_in):
        expiration = datetime.utcnow() + timedelta(seconds=expires_in) - UPDATE_INTERVAL
        self.logger.debug(
            "Original expiration: %s, Expiration set to %s", expires_in, expiration
        )
        return expiration

    async def ensure_authenticated(self):
        """Ensure the session is authenticated and tokens are valid."""
        if not self.authenticated or datetime.utcnow() >= self.token_expiration:
            self.logger.debug("Tokens expired or not authenticated, refreshing tokens")
            await self.refresh_token()

    async def fetch_customer_data_and_token(self):
        """Fetch customer data and get the token for meter readings."""
        if self.customer_token and datetime.utcnow() < self.customer_token_expiry:
            self.logger.debug("Using cached customer token")
            return  # Token is still valid

        await self.ensure_authenticated()
        headers = {"Authorization": f"Bearer {self.tokens.get('IdToken')}"}
        try:
            async with async_timeout.timeout(10):
                async with self.session.get(CUSTOMER_DATA_URL, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self.customer_token = data.get("token")
                        if not self.customer_token:
                            self.logger.error("No token found in customer data")
                            raise Exception("No token in customer data")
                        # Set customer token expiry time to 2 hours 55 minutes from now
                        self.customer_token_expiry = datetime.utcnow() + timedelta(
                            hours=2, minutes=55
                        )
                        # Store the customer data
                        self.customer_data = data.get("customer_datas", {})

                        meteringpoints = self.customer_data.get(
                            self.customer_id, {}
                        ).get("meteringpoints", [])

                        self.meteringpoint = next(
                            (
                                mp
                                for mp in meteringpoints
                                if mp.get("gsrn") == self.gsrn
                            ),
                            None,
                        )
                        self.serialnumber = self.meteringpoint.get(
                            "device_serialnumber"
                        )
                        self.logger.debug("Fetched new customer token")
                        return data
                    else:
                        error_text = await resp.text()
                        self.logger.error(
                            "Failed to fetch customer data: %s - %s",
                            resp.status,
                            error_text,
                        )
                        raise Exception("Failed to fetch customer data")
        except Exception as e:
            self.logger.error("Exception during customer data fetch: %s", str(e))
            raise

    async def fetch_relay_schedule(self) -> RelayData | None:
        headers = {"Authorization": f"Bearer {self.customer_token}"}

        params = {"gsrn": self.gsrn, "serialnumber": self.serialnumber}

        url = RELAY_CONTROL_URL
        try:
            async with async_timeout.timeout(10):
                async with self.session.get(
                    url, headers=headers, params=params
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if (
                            data is None
                            or not isinstance(data, dict)
                            or not isinstance(data.get("relay1"), dict)
                        ):
                            self.logger.error("Invalid data format received")
                            return None
                        try:
                            return RelayData(
                                gsrn=data["gsrn"],
                                serialnumber=data["serialnumber"],
                                relay1=parse_relay(data.get("relay1")),
                                relay2=parse_relay(data.get("relay2")),
                            )
                        except (KeyError, ValidationError, ValueError) as e:
                            self.logger.error("Data validation error: %s", str(e))
                            return None

                    else:
                        error_text = await resp.text()
                        self.logger.error(
                            "Failed to fetch device data: %s - %s",
                            resp.status,
                            error_text,
                        )
                        return None
        except Exception as e:
            self.logger.error("Error during fetching relay data: %s", str(e))
        return None

    async def fetch_5min_readings(self) -> Measurements or None:
        await self.ensure_authenticated()
        await self.fetch_customer_data_and_token()

        headers = {"Authorization": f"Bearer {self.customer_token}"}
        params = {
            "customer_ids": self.customer_id,
            "gsrn": self.gsrn,
            "day": dt_util.now().astimezone(dt_util.UTC).strftime("%Y-%m-%d"),
        }
        url = METER_READING_URL

        try:
            async with async_timeout.timeout(10):
                async with self.session.get(
                    url, headers=headers, params=params
                ) as resp:
                    if resp.status == 200:
                        data: Measurements = await resp.json()
                        if data is None or type(data) != list or not len(data):
                            self.logger.error("Invalid data format received")
                            return None
                        return data
                    else:
                        error_text = await resp.text()
                        self.logger.error(
                            "Failed to fetch meter readings: %s - %s",
                            resp.status,
                            error_text,
                        )
                        return None

        except Exception as e:
            self.logger.error("Exception during data fetching readings: %s", str(e))
        return None

    async def fetch_meter_readings(self):
        """Fetch the latest hourly consumption data. Used for old metering points"""
        await self.ensure_authenticated()
        await self.fetch_customer_data_and_token()
        headers = {"Authorization": f"Bearer {self.customer_token}"}
        params = {
            "customer_ids": self.customer_id,
            "gsrn": self.gsrn,
            "day": dt_util.now().year,
            "dh": "true",
        }
        url = METER_READING_URL
        try:
            async with async_timeout.timeout(10):
                async with self.session.get(
                    url, headers=headers, params=params
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if "months" in data:
                            return data
                        else:
                            self.logger.error("Invalid data format received")
                            return None
                    else:
                        error_text = await resp.text()
                        self.logger.error(
                            "Failed to fetch meter readings: %s - %s",
                            resp.status,
                            error_text,
                        )
                        return None
        except Exception as e:
            self.logger.error("Exception during data fetch: %s", str(e))
            return None

    async def close(self):
        """Close the session."""
        await self.session.close()
