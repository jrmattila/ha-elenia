# Home Assistant integration for Elenia

This is a custom component to integrate Home Assistant with Elenia

## Features
### Electricity consumption data
Component exposes 4 sensors, total kWh reading and one for each electric phases. The measurement is total reading, which increases in time. You can use utility helper to deduce for example hourly data from that.

Beware that Elenia returns measurements with about 30 minutes delay. Home Assistant does not currently support showing delayed data correctly in history, so the history data has this 30 minute bias.

At the moment only newer metering devices are supported.

## Future roadmap
### Relay control
I'm working on showing controls to configure the schedules to activate/disable relays on the metering device. 

## Disclaimer
This integration is neither controlled by, sponsored by, nor endorsed by the Elenia Verkko Oyj in any way. The data or functionality it offers, might not work, and you should not use it in any critical applications. Use it at your own risk.