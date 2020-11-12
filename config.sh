#!/bin/bash

# set to false to run setup.sh
RASPI_FANSPEED_CONFIG_EMPTY="FALSE"

# copy to /usr/bin and install service
#RASPI_FANSPEED_INSTALL_TYPE="INSTALL"

# show CLI for the configuration only
RASPI_FANSPEED_INSTALL_TYPE="SHOWCLI"

# hardware PWM pin
FAN_PWM_PIN="19"

# Hz
FAN_PWM_FREQUENCY="32000"

# MQTT is disabled by default
# push temperature and speed to MQTT_TOPIC
#MQTT_HOST="localhost"

# auto discovery prefix for homeassistant
#HOMEASSISTANT_AUTO_DISCOVERY_PREFIX="homeassistant"
HOMEASSISTANT_AUTO_DISCOVERY_PREFIX=""

# store temperature and speed in this file
#LOG_FILENAME=/var/log/fanspeed.json
