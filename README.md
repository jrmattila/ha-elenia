# Home Assistant integration for Elenia

This is a custom component to integrate Home Assistant with Elenia

## Features
### Electricity consumption data
Component exposes 4 sensors, total kWh reading and one for each electric phases. The measurement is total reading, which increases in time. You can use utility helper to deduce for example hourly data from that.

Beware that Elenia returns measurements with about 30 minutes delay. Home Assistant does not currently support showing delayed data correctly in history, so the history data has this 30 minute bias.

At the moment only newer metering devices are supported.

#### Example of showing hourly consumption data
Define first a Utility Meter -helper to collect hourly data. Set total consumption sensor as an input sensor. Meter reset cycle should be set to "Hourly".
[Apexcharts-card](https://github.com/RomRider/apexcharts-card) can be used to show hourly consumption data in a graph:

![apexcharts-example](https://github.com/jrmattila/ha-elenia/blob/main/docs/apexcharts-example.png?raw=true)

Example config:
```yaml
type: custom:apexcharts-card
graph_span: 1d
apex_config:
  chart:
    stacked: true
span:
  end: day
show:
  last_updated: true
header:
  show: true
  title: Electricity consumption
series:
  - entity: sensor.hourly_electricity_consumption # utility meter helper
    name: Consumption
    type: column
    unit: " kWh"
    group_by:
      func: max
      duration: 1h
```

## Future roadmap
### Relay control
I'm working on showing controls to configure the schedules to activate/disable relays on the metering device. 

## Disclaimer
This integration is neither controlled by, sponsored by, nor endorsed by the Elenia Verkko Oyj in any way. The data or functionality it offers, might not work, and you should not use it in any critical applications. Use it at your own risk.