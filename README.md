# Airthings Local

A Home Assistant custom integration for a locally hosted Airthings history API.

Home Assistant never communicates directly with Airthings devices over Bluetooth. Your existing Python collector remains responsible for BLE communication, collecting readings, and making historical data available through the API.

## Features

- UI-based configuration with optional mDNS/Zeroconf discovery.
- Discovers enabled Airthings devices through the local API.
- Polls each device's latest sample every five minutes.
- Creates applicable environmental sensors for temperature, humidity, pressure, illuminance, VOC, CO₂, and radon.
- Preserves source measurement timestamps as entity attributes.
- Imports five-minute source records into completed hourly statistics.
- Backfills existing sensor entities with historical samples using their original timestamps.
- Supports scheduled automatic backfill with a configurable interval and an automatically calculated lookback period (interval + one hour).

## Companion Project: Airthings Decoder

**Airthings Decoder** is the companion BLE collection and decoding project currently in development.

It communicates directly with Airthings devices, collects and decodes their readings, and makes the data available through the local API consumed by Airthings Local.

Together, the projects provide a fully local data pipeline:

**Airthings devices → Airthings Decoder → Local API → Airthings Local → Home Assistant**

The goal is a local, subscription-free solution for bringing Airthings data into Home Assistant.

Repository: *Coming soon.*

## Requirements

- A running instance of **Airthings Decoder**, which provides the local API used by this integration.
- Airthings Decoder must be configured and running before adding Airthings Local to Home Assistant.

See the [Airthings Decoder](https://github.com/zhoulander/airthings-decoder) documentation for installation, configuration, and API requirements.

## Installation

### Home Assistant Marketplace

Home Assistant 2026.11+ includes the built-in Marketplace, which replaces the need to install HACS separately.

This repository is available at:

[https://github.com/zhoulander/airthings-local](https://github.com/zhoulander/airthings-local)

To install:

1. Open **Settings → Marketplace** in Home Assistant.
2. Choose **Add from link**.
3. Enter the repository URL above.
4. Add the repository.
5. Open its entry and choose **Install**.
6. Restart Home Assistant if prompted.
7. Go to **Settings → Devices & services → Add integration** and search for **Airthings Local**.

The Marketplace requires a public GitHub repository with a root-level `hacs.json`, which this repository includes.

Adding a custom repository requires connecting a GitHub account from Home Assistant. That connection is read-only and separate from your GitHub login in a browser.

## Configuration

Add the integration through **Settings → Devices & services → Add integration → Airthings Local**.

Enter the base URL of your Airthings API, for example:

`http://192.168.1.50:8000`

Home Assistant must be able to reach that address over your local network.

## Historical Statistics Import

The `airthings_local.import_history` action imports historical readings and creates hourly external statistics.

To run it:

1. Open **Developer Tools → Actions**.
2. Select `airthings_local.import_history`.
3. Run the action.

The importer:

- Fetches stored source records from the Airthings API.
- Aggregates five-minute readings into completed UTC hours.
- Creates hourly statistics for hours containing at least six readings.
- Leaves the original five-minute records untouched in the Airthings API.

You can run the import again. Home Assistant updates existing statistic rows for matching hours.

The first import may take some time when a large history is available. Do not run multiple imports simultaneously.

## Entity History Backfill

The `airthings_local.backfill_entity_history` action imports historical sensor readings from the local Airthings history API into Home Assistant Recorder.

Unlike the historical statistics importer, this backfill creates timestamped entity states. Readings therefore appear in the normal Home Assistant History interface.

### Manual Backfill

Open **Developer Tools → Actions** and select:

`airthings_local.backfill_entity_history`

Provide the number of hours to import:

```yaml
hours: 240
```

The `hours` parameter is optional. If omitted, the integration uses the configured lookback period, which defaults to seven hours.

| Setting | Value |
|---|---:|
| Default lookback | 7 hours |
| Minimum | 1 hour |
| Maximum | 336 hours (14 days) |
| Parameter type | Integer |

Examples:

```yaml
# Last 3 hours
hours: 3

# Last 6 hours
hours: 6

# Last 3 days
hours: 72

# Last 10 days
hours: 240
```

### Automatic Backfill

Automatic backfill is configured through the integration's **Configure** options.

The available settings are:

- **Enable automatic backfill:** Turns scheduled backfill on or off.
- **Backfill interval:** Determines how frequently automatic backfill runs.

The lookback period is automatically calculated as one hour longer than the configured interval.

| Backfill interval | Automatic lookback |
|---:|---:|
| 1 hour | 2 hours |
| 2 hours | 3 hours |
| 3 hours | 4 hours |
| 6 hours | 7 hours |
| 12 hours | 13 hours |
| 24 hours | 25 hours |

Default configuration:

- Automatic backfill: Enabled
- Backfill interval: 6 hours
- Lookback period: 7 hours

The additional hour provides an overlap between scheduled runs, helping account for differences in polling and backfill timing. Checkpointing prevents previously imported timestamps from being imported again.

The first scheduled backfill runs after the configured interval, not immediately when Home Assistant starts.

Manual backfills remain available independently of automatic backfill. An optional `hours` parameter can override the configured lookback period.

Examples:

```yaml
# Use the configured lookback period
{}

# Override the lookback with 10 days
hours: 240
```

Disabling automatic backfill does not disable manual backfill actions.

### Backfill Implementation and Safety

- History is retrieved in pages of 100 records, newest first.
- Records are replayed chronologically into Home Assistant.
- A 0.5-second pause is used between records to reduce load on Home Assistant and Recorder.
- A maximum of 5,000 records per device is enforced as a safety limit.
- Progress is checkpointed separately for each requested lookback window, allowing interrupted runs to resume.
- Existing entity IDs are used, including entities that have been renamed in Home Assistant.
- Original live sensor states are restored after backfill completes.
- A coordinator lock prevents overlapping backfill operations.

Do not run multiple manual backfills simultaneously.

### Expected Runtime

Runtime depends on the number of devices, available history, and Home Assistant hardware.

Successful tests:

| Lookback | States imported | Skipped | Runtime |
|---|---:|---:|---:|
| 3 hours | 233 | 0 | — |
| 3 days | 8,943 | 0 | 13 minutes 28 seconds |
| 10 days | 30,473 | 0 | Approximately 46 minutes |

Longer backfills can take considerable time. Start with a shorter window when testing on new hardware or a new installation.

## Network Discovery (Optional mDNS)

The integration listens for:

`_airthings-api._tcp.local.`

To advertise the API, install `zeroconf` in the Python environment running the API and start:

```bash
tools/airthings_api_mdns.py --port 8000
```

Keep that helper running while the API is available.

The announcement advertises only the API endpoint. It does not establish a BLE connection or communicate directly with Airthings devices.

URL-based setup remains available if you do not use mDNS.

## Sensors

The integration creates sensors according to the connected device model.

| Device | Model ID | Available sensors |
|---|---:|---|
| Wave Mini | 2920 | Temperature, humidity, pressure, illuminance, VOC |
| Wave Plus | 2930 | Temperature, humidity, pressure, illuminance, VOC, CO2, short-term radon, long-term radon |

Additional notes:

- `x3` and `x4` are not exposed because their units and meaning are not confirmed.
- Radon values are represented in Bq/m³.
- VOC is represented in ppb.
- CO2 is represented in ppm.

## Development Status

Version 0.5.0 is an early community integration release.

The integration has been tested in a Home Assistant instance, including a successful 10-day entity-history backfill importing 30,473 states with no skipped values.

Backfill is bounded and paginated to reduce load on Home Assistant and Recorder.

Backups are recommended before installation or large historical imports.