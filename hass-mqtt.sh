#!/bin/bash

PUBSUB_BIN="$(which mosquitto_pub)"
HASS_PREFIX="homeassistant"
DEVICE_NAME=$HOSTNAME
TMPFILE_T=$(tempfile)
TMPFILE_S=$(tempfile)
TOPIC="home/${DEVICE_NAME}/RPi.fanspeed"
STATUS="$TOPIC/status"
VERSION="0.0.1"
CMD="$1"

if [ "$CMD" == "connect" ] ; then

    "$PUBSUB_BIN" -t "$STATUS" -m "1" -r

elif [ "$CMD" == "publish" ] ; then

    echo

elif [ "$CMD" == "disconnect" ] ; then

    "$PUBSUB_BIN" -t "$STATUS" -m "0" -r

elif [ "$CMD" == "autoconfig" ] ; then

    MACS="$(echo $(cat /sys/class/net/*/address|grep -v 00:00:00)|sed s'/ /\",\"/g')"
    MUID="$(echo "$MACS $DEVICE_NAME" | md5sum | cut -b 1-12)"
    # CONFIG='{"name":"'${DEVICE_NAME}'_cpu-temperature","platform":"mqtt","unique_id":"'$MUID'","device":{"identifiers":["'$MUID'"],"connections":["mac","'$MACS'"]},"model":"Raspberry Pi","name":"RPi.fanspeed","sw_version":"0.0.1","manufacturer":"KFCLabs","state_topic":"'$TOPIC'/json"
    # echo '{"name": "'${DEVICE_NAME}'_cpu-temperature","platform":"mqtt","unique_id":"'$MUID'","availability_topic":"$STATUS","device":"identifiers":["'$MUID'"],"connections":["mac","'$MACS'"],"model":"Raspberry Pi","name":"RPi.fanspeed","sw_version":"0.0.1","manufacturer":"KFCLabs",}'

    "$PUBSUB_BIN" -t "$HASS_PREFIX/sensor/${DEVICE_NAME}_cpu-thermal/config" -m '{"name":"'${DEVICE_NAME}'_cpu-temperature","platform":"mqtt","unique_id":"'$MUID'","device":{"identifiers":["'$MUID'"],"connections":["mac","'$MACS'"]},"model":"Raspberry Pi","name":"RPi.fanspeed","sw_version":"'$VERSION'","manufacturer":"KFCLabs","availability_topic":"'$STATUS'","state_topic":"'$TOPIC'/json","unit_of_measurement":"\\u00b0","value_template":"{{ value_json.temperature }}"}' -r
    "$PUBSUB_BIN" -t "$HASS_PREFIX/sensor/${DEVICE_NAME}_cpu-fan/config" -m '{"name":"'${DEVICE_NAME}'_cpu-fan","platform":"mqtt","unique_id":"'$MUID'","device":{"identifiers":["'$MUID'"],"connections":["mac","'$MACS'"]},"model":"Raspberry Pi","name":"RPi.fanspeed","sw_version":"'$VERSION'","manufacturer":"KFCLabs","availability_topic":"'$STATUS'","state_topic":"'$TOPIC'/json","unit_of_measurement":"%","value_template":"{{ value_json.speed }}"}' -r


else

    echo "usage: hass-mqtt.sh <connect|disconnect|publish|autoconfig>"

fi
