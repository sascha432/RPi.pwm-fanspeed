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

    OPTS="-d -r"
    "$PUBSUB_BIN" -t "$STATUS" $OPTS -m "1"

elif [ "$CMD" == "publish" ] ; then

    echo

elif [ "$CMD" == "disconnect" ] ; then

    OPTS="-d -r"
    "$PUBSUB_BIN" -t "$STATUS" $OPTS -m "0"

elif [ "$CMD" == "autoconfig" ] ; then

    OPTS="-d -r"
    MACS="$(echo $(cat /sys/class/net/*/address|grep -v 00:00:00)|sed s'/ /\"],[\"mac\",\"/g')"
    MUID1="$(echo "$MACS $DEVICE_NAME thermal" | md5sum | cut -b 1-12)"
    MUID2="$(echo "$MACS $DEVICE_NAME fanspeed" | md5sum | cut -b 1-12)"

    DEVICE='"device":{"identifiers":["'$MUID1'"],"connections":[["mac","'$MACS'"]],"model":"Raspberry_Pi","sw_version":"'$VERSION'","manufacturer":"KFCLabs"},"availability_topic":"'$STATUS'","payload_available":1,"payload_not_available":0'
    "$PUBSUB_BIN" -t "$HASS_PREFIX/sensor/${DEVICE_NAME}_cpu-thermal/config" $OPTS -m '{"name":"'${DEVICE_NAME}'_cpu-temperature","platform":"mqtt","unique_id":"'$MUID1'",'$DEVICE',"state_topic":"'$TOPIC'/json","unit_of_measurement":"\u00b0C","value_template":"{{ value_json.temperature }}"}'

    DEVICE='"device":{"identifiers":["'$MUID2'"],"connections":[["mac","'$MACS'"]],"model":"Raspberry_Pi","sw_version":"'$VERSION'","manufacturer":"KFCLabs"},"availability_topic":"'$STATUS'","payload_available":1,"payload_not_available":0'
    "$PUBSUB_BIN" -t "$HASS_PREFIX/sensor/${DEVICE_NAME}_cpu-fan/config" $OPTS -m '{"name":"'${DEVICE_NAME}'_cpu-fan","platform":"mqtt","unique_id":"'$MUID2'",'$DEVICE',"state_topic":"'$TOPIC'/json","unit_of_measurement":"%","value_template":"{{ value_json.speed }}"}'

else

    echo "usage: hass-mqtt.sh <connect|disconnect|publish|autoconfig>"

fi
