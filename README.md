# Airthings Local

A Home Assistant custom integration for a locally hosted Airthings history API. Home Assistant never connects to Airthings devices over Bluetooth; your existing Python collector remains responsible for BLE communication and the API.

## Features

- UI config flow and optional mDNS/Zeroconf discovery.
- Discovers enabled Airthings devices from `/api/devices`.
- Polls each device's latest sample every five minutes.
- Creates temperature, humidity, pressure, illuminance, VOC, CO2 and radon sensors where applicable.
- Preserves measurement timestamps as entity attributes.
- Provides a historical statistics import service, aggregating five-minute source records into completed UTC hours.
- Provides a resumable, paginated entity-history backfill that writes source samples to existing sensor entities with their original timestamps.
- Supports automatic entity-history backfill on a configurable schedule.
- Supports configurable backfill frequency and lookback period.

## Requirements

The existing Airthings API must expose:

- `GET /health`
- `GET /api/devices` returning a JSON object with a `devices` array.
- `GET /api/devices/{serial}/history?limit=1&order=desc`
- `GET /api/devices/{serial}/history` supporting pagination with `limit`, `offset`, and `order` parameters.

History responses must include a `records` array, per-sample `timestamp` (Unix seconds), and `next_offset` when another page exists. The API must support `order=asc` and `order=desc`.

## Install on Home Assistant 2026.11+

Home Assistant 2026.11 includes the built-in **Marketplace**, which replaces the separately installed HACS integration. After you create the public repository [https://github.com/zhoulander/airthings-local](https://github.com/zhoulander/airthings-local) and push these files:

1. In Home Assistant, open **Settings → Marketplace**.
2. Choose **Add from link**.
3. Enter `https://github.com/zhoulander/airthings-local` and add it.
4. Open the repository entry and choose **Install**.
5. When installation finishes, follow the setup prompt or go to **Settings → Devices & services → Add integration → Airthings Local**.

The Marketplace requires a public GitHub repository with a root-level `hacs.json`. This repository includes that file. Adding a custom repository requires connecting a GitHub account from Home Assistant; that connection is read-only and separate from your GitHub login in a browser.

For manual installation, copy `custom_components/airthings_local` into the Home Assistant configuration's `custom_components` directory and restart.

## Configure

Enter the API base URL, for example `http://192.168.1.50:8000`. Home Assistant must be able to reach that address on your LAN.

## Historical Statistics Import

After setup, run the `airthings_local.import_history` action from **Developer Tools → Actions**.

The importer fetches stored source records and creates hourly external statistics for completed UTC hours with at least six readings in that hour. The original five-minute records remain untouched in the Airthings API.

You can run the import again; Home Assistant updates existing statistic rows for matching hours. The first import may take some time for a large history. Do not run multiple imports simultaneously.

## Entity History Backfill

The `airthings_local.backfill_entity_history` action imports historical sensor readings from the local Airthings history API into Home Assistant Recorder.

Unlike the long-term statistics importer, this backfill creates timestamped entity state history, allowing readings to appear in the normal Home Assistant History interface.

### Running a Manual Backfill

Go to **Developer Tools → Actions** and select:

`airthings_local.backfill_entity_history`

Provide the number of hours to import:

```yaml
hours: 240
```

The `hours` parameter is optional. If omitted, the integration uses the configured lookback period (7 hours by default).

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

Automatic backfill can be configured through the integration's **Configure** options.

Only one timing setting is required: the backfill interval. The integration automatically sets the lookback period to one hour longer than the interval.

| Backfill interval | Automatic lookback |
|---:|---:|
| 1 hour | 2 hours |
| 2 hours | 3 hours |
| 3 hours | 4 hours |
| 6 hours | 7 hours |
| 12 hours | 13 hours |
| 24 hours | 25 hours |

The default configuration is:

- Automatic backfill: Enabled
- Backfill interval: 6 hours
- Lookback period: 7 hours

The additional hour provides an overlap between scheduled runs. Checkpointing prevents previously imported timestamps from being imported again.

The first scheduled backfill runs after the configured interval, not immediately when Home Assistant starts.

Manual backfills can still be run independently, with an optional `hours` parameter to override the default lookback.

For example:

```yaml
# Use the configured interval + 1 hour
{}

# Override the lookback with 10 days
hours: 240
```

Automatic backfill can be disabled without affecting manual backfill actions.

### Backfill Implementation and Safety

- History is retrieved in pages of 100 records, newest first.
- Records are replayed chronologically into Home Assistant.
- A 0.5-second pause is used between records to reduce load on Home Assistant and Recorder.
- A maximum of 5,000 records per device is enforced as a safety limit.
- Progress is checkpointed separately for each requested lookback window, allowing interrupted runs to resume.
- Existing entity IDs are used, including entities that have been renamed in Home Assistant.
- Original live sensor states are restored after the backfill completes.
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

The integration listens for `_airthings-api._tcp.local.`.

To advertise the API, install `zeroconf` in the Python environment running the API and start:

```bash
tools/airthings_api_mdns.py --port 8000
```

Keep that helper running while the API is available. The announcement advertises only the API endpoint; it does not connect to BLE.

URL-based setup remains available if you do not use mDNS.

## Sensors

- **Wave Mini (model ID 2920):** temperature, humidity, pressure, illuminance, VOC.
- **Wave Plus (model ID 2930):** temperature, humidity, pressure, illuminance, VOC, CO2, short-term radon, long-term radon.
- `x3` and `x4` are not exposed because their units and meaning are not confirmed.
- Radon values are represented as Bq/m³.
- VOC is represented as ppb; CO2 is represented as ppm.

## Development Status

This is an early community integration draft.

The integration has been tested in a Home Assistant instance, including a successful 10-day entity-history backfill importing 30,473 states with no skipped values.

Backfill is bounded and paginated to reduce load on Home Assistant and Recorder. Backups are still recommended before installation or large historical imports.