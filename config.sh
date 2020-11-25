#!/bin/bash

# copy to /usr/bin and install service
#RASPI_FANSPEED_INSTALL_TYPE="INSTALL"

# show CLI for the configuration only
RASPI_FANSPEED_INSTALL_TYPE="SHOWCLI"

# hardware PWM pin
FAN_PWM_PIN="19"

# Hz
FAN_PWM_FREQUENCY="32000"

# anonymous login
MQTT_USER=""
MQTT_PASS=""
# MQTT is disabled by default
MQTT_HOST=""
# push temperature and speed to MQTT_TOPIC
#MQTT_HOST="localhost"
# mqtt port
MQTT_PORT=1883
# update interval in seconds
MQTT_UPDATE_INTERVAL=60
# defaults
#MQTT_DEVICE_NAME=$(hostname)
#MQTT_TOPIC="home/$MQTT_DEVICE_NAME/{entity}"

# auto discovery prefix for homeassistant
#HOMEASSISTANT_AUTO_DISCOVERY_PREFIX="homeassistant"
HOMEASSISTANT_AUTO_DISCOVERY_PREFIX=""

# store temperature and speed in this file
#LOG_FILENAME=/var/log/raspi_fanspeed.json
