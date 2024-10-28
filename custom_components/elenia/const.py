from datetime import timedelta

DOMAIN = "elenia"
PLATFORMS = ["sensor"]
AUTH_URL = "https://cognito-idp.eu-west-1.amazonaws.com/"
CUSTOMER_DATA_URL = "https://public.sgp-prod.aws.elenia.fi/api/gen/customer_data_and_token"
METER_READING_URL = "https://public.sgp-prod.aws.elenia.fi/api/gen/meter_reading"
UPDATE_INTERVAL = timedelta(hours=1)
CONF_CUSTOMER_ID = "customer_id"
CONF_GSRN = "gsrn"