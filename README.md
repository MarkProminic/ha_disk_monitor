# Disk Monitor

![GitHub release (latest by date)](https://img.shields.io/github/v/release/MarkProminic/ha_disk_monitor?style=plastic)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=plastic)](https://github.com/hacs/integration)
![GitHub all releases](https://img.shields.io/github/downloads/MarkProminic/ha_disk_monitor/total?style=plastic)
![GitHub Release Workflow Status](https://img.shields.io/github/actions/workflow/status/MarkProminic/ha_disk_monitor/release.yml?style=plastic)

## Disk Monitor

This is an integration for Home Assistant that polls a [disk-agent](https://github.com/MarkProminic/disk-agent) on each storage host and creates one device per disk, keyed by serial, and one device per ZFS pool, keyed by name. Disks and pools that appear on the host appear in Home Assistant on the next poll; disks and pools that leave the host are removed.

Each disk device carries a SMART problem binary sensor and sensors for temperature, power-on hours and the SMART counters the drive reports. Each pool device carries a health problem binary sensor, the health state, capacity, fragmentation, sizes, the last scan line and the member states.

### Installation

#### HACS

1. Install [HACS](https://hacs.xyz)
1. Go to any of the sections (integrations, frontend, automation).
1. Click on the 3 dots in the top right corner.
1. Select "Custom repositories"
1. Add the URL to the repository: https://github.com/MarkProminic/ha_disk_monitor
1. Select the integration category.
1. Click the "ADD" button.
1. Go to Home Assistant settings -> Integrations and add Disk Monitor
1. Restart HA

#### Manual

1. Clone this repository
2. Copy `custom_components/ha_disk_monitor` to your Home Assistant instance on `<config dir>/custom_components/`
3. Restart Home Assistant Core
4. Add the integration via the Integrations page

### Setup

1. Install and start disk-agent on the host, then read its setup token from `/etc/disk-agent/setup.token`
2. Go to the *Integrations* page and click **+ ADD INTEGRATION**
3. Select *Disk Monitor*
4. Enter the host, the port (9431 for HTTPS, 9430 for HTTP) and the setup token; the integration mints its own API key from it
5. The poll interval is set in the integration's options, 300 seconds by default
