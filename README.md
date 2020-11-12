# RPi.fanspeed

Adjustable fanspeed with temperature monitoring

## Requirements

- raspberry pi
- python 3.7
- pigpio
- paho-mqtt (only if MQTT is used)

## Installation

Edit config.sh and run setup.sh... The installation method can be set to show command line or install service.

## Configuration

The fan must be connected to one of the hardware PWM pins (12, 13, 18, 19 for RPi3B+)
The service can be configured in /etc/systemd/system/raspi_fanspeed.service using the command line arguments.

The fan can be configured to run from 30-90°C with increasing speed. For example start over 45°C with 50% PWM duty cycle and increase the level up to 100% when reaching 75°C

```
# raspi_fanspeed --min 45 --max=75 --min-fan=50 --no-json --print-speed
000%: 30.0°C
050%: 45.0°C
052%: 46.0°C
053%: 47.0°C
055%: 48.0°C
057%: 49.0°C
058%: 50.0°C
060%: 51.0°C
062%: 52.0°C
063%: 53.0°C
065%: 54.0°C
067%: 55.0°C
068%: 56.0°C
070%: 57.0°C
072%: 58.0°C
073%: 59.0°C
075%: 60.0°C
077%: 61.0°C
078%: 62.0°C
080%: 63.0°C
082%: 64.0°C
083%: 65.0°C
085%: 66.0°C
087%: 67.0°C
088%: 68.0°C
090%: 69.0°C
092%: 70.0°C
093%: 71.0°C
095%: 72.0°C
097%: 73.0°C
098%: 74.0°C
100%: 75.0°C
```

## Temperature

The temperature is read from `sys/class/thermal/thermal_zone0/temp` by default.

## MQTT and homeassistant

When the service is running with MQTT enabled, it pushes the temperature and fan speed in intervals to topic `home/{device_name}/RPi.fanspeed/json`. `device_name` is the hostname by default.

It also adds the homeassistant auto discovery with the prefix `homeassistant` and two sensors should be detected.

## CLI

```
usage: raspi_fanspeed.py [-h] [-i INTERVAL] [--min MIN] [--max MAX]
                         [--min-fan MIN_FAN] [-p {12,13,18,19}] [-f FREQUENCY]
                         [-S] [-E ONEXIT_SPEED] [--mqttuser MQTTUSER]
                         [--mqttpass MQTTPASS] [--mqtttopic MQTTTOPIC]
                         [--mqtthass MQTTHASS]
                         [--mqttupdateinterval MQTTUPDATEINTERVAL]
                         [--mqttdevicename MQTTDEVICENAME] [-H MQTTHOST]
                         [-P MQTTPORT] [-C CMD] [-L LOG] [--no-json] [-V] [-v]
                         [--temp TEMP]

adjustable fanspeed with temperature monitoring

optional arguments:
  -h, --help            show this help message and exit
  -i INTERVAL, --interval INTERVAL
                        fan speed update interval in seconds
  --min MIN             minimum temperature to turn on fan in °C (30-70)
  --max MAX             maximum fan speed if temperature exceeds this value
                        (40-90)
  --min-fan MIN_FAN     minimum fan speed in %
  -p {12,13,18,19}, --pin {12,13,18,19}
                        fan PWM pin. must be capable of hardware PWM
  -f FREQUENCY, --frequency FREQUENCY
                        PWM frequency
  -S, --print-speed     Print fan speed table and exit
  -E ONEXIT_SPEED, --onexit-speed ONEXIT_SPEED
                        turn fan to 30-100% when exiting. -1 disable fan on
                        exit
  --mqttuser MQTTUSER   use phyton mqtt client to connect to MQTT. provide an
                        empty username for an anonymous connection
  --mqttpass MQTTPASS
  --mqtttopic MQTTTOPIC
  --mqtthass MQTTHASS   home assistant MQTT auto discovery prefix
  --mqttupdateinterval MQTTUPDATEINTERVAL
                        mqtt update interval (30-900 seconds)
  --mqttdevicename MQTTDEVICENAME
                        mqtt device name
  -H MQTTHOST, --mqtthost MQTTHOST
  -P MQTTPORT, --mqttport MQTTPORT
  -L LOG, --log LOG     write temperature and speed into this file i.e.
                        --log=/var/log/tempmon.json
  --no-json
  -V, --version
  -v, --verbose
```