from datetime import timedelta

DOMAIN = "elenia"
PLATFORMS = ["sensor"]
AUTH_URL = "https://cognito-idp.eu-west-1.amazonaws.com/"
API_URL = "https://public.sgp-prod.aws.elenia.fi/api"
CUSTOMER_DATA_URL = API_URL + "/gen/customer_data_and_token"
METER_READING_URL = API_URL + "/gen/meter_reading"
RELAY_CONTROL_URL = API_URL + "/gen/relay_control"
RELAY_MARKET_URL = API_URL + "/gen/relay_market"
UPDATE_INTERVAL = timedelta(hours=1)
CONF_CUSTOMER_ID = "customer_id"
CONF_GSRN = "gsrn"
CONF_PRICE_SENSOR_FOR_EACH_HOUR="price_sensor_for_each_hour"
CONF_RELAY_SENSOR_FOR_EACH_HOUR="relay_sensor_for_each_hour"
AUTH_CLIENT_ID = "k4s2pnm04536t1bm72bdatqct"
