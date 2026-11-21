
from datetime import timedelta

DOMAIN = "airthings_local"
CONF_URL = "url"

CONF_AUTO_BACKFILL = "auto_backfill"
CONF_BACKFILL_INTERVAL_HOURS = "backfill_interval_hours"

DEFAULT_AUTO_BACKFILL = True
DEFAULT_BACKFILL_INTERVAL_HOURS = 6

DEFAULT_SCAN_INTERVAL = timedelta(minutes=5)
PLATFORMS = ["sensor"]
API_TIMEOUT = 15

# Field, display name, unit, device class, suggested icon.
SENSOR_DESCRIPTIONS = {
    "temperature_c": ("Temperature", "°C", "temperature", "mdi:thermometer"),
    "humidity_pct": ("Humidity", "%", "humidity", "mdi:water-percent"),
    "pressure_hpa": ("Pressure", "hPa", "atmospheric_pressure", "mdi:gauge"),
    "illuminance_lux": ("Illuminance", "lx", "illuminance", "mdi:brightness-5"),
    "voc_ppb": ("VOC", "ppb", None, "mdi:air-filter"),
    "co2_ppm": ("CO₂", "ppm", "carbon_dioxide", "mdi:molecule-co2"),
    "radon_st": ("Radon (short-term)", "Bq/m³", None, "mdi:radioactive"),
    "radon_lt": ("Radon (long-term)", "Bq/m³", None, "mdi:radioactive"),
}
