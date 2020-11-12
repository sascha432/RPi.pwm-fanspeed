#!/bin/bash


INST_DIR=$(dirname $(readlink -nf $0))
CONFIG_SH="$INST_DIR/config.sh"
RPI_FANSPEED_SRC="$INST_DIR/raspi_fanspeed.py"
PYTHON_BIN=$(which python3)
PIP_BIN=$(which pip3)
PIP_LIBS="pigpio"
SYSTEMD_DIR=/etc/systemd/system
RPI_FANSPEED_SRC="$INST_DIR/raspi_fanspeed.py"
RPI_FANSPEED_BIN=/usr/bin/raspi_fanspeed
SERVICE_NAME=raspi_fanspeed
SYSTEMCTL_BIN=$(which systemctl)
MQTT_USER=""
MQTT_PASS=""
MQTT_HOST=""

. $CONFIG_SH

if [ "$RASPI_FANSPEED_CONFIG_EMPTY" != "FALSE" ] ; then
	echo "edit $CONFIG_SH first..."
	exit 1
fi

if [ "$MQTT_HOST" != "" ] ; then
	PIP_LIBS="$PIP_LIBS paho-mqtt"
fi

declare -a CMD_ARGS

CMD_ARGS+=("$RPI_FANSPEED_BIN")

if [ "$FAN_PWM_PIN" != "" ] ; then
	CMD_ARGS+=("--pin=$FAN_PWM_PIN")
fi

if [ "$FAN_PWM_FREQUENCY" != "" ] ; then
	CMD_ARGS+=("--frequency=$FAN_PWM_FREQUENCY")
fi

if [ "$LOG_FILENAME" != "" ] ; then
	CMD_ARGS+=("--log=$LOG_FILENAME")
fi

if [ "$MIN_TEMP" != "" ] ; then
	CMD_ARGS+=("--min=$MIN_TEMP")
fi

if [ "$MAX_TEMP" != "" ] ; then
	CMD_ARGS+=("--max=$MAX_TEMP")
fi

if [ "$MIN_FAN_DUTY_CYCLE" != "" ] ; then
	CMD_ARGS+=("--min-fan=$MIN_FAN_DUTY_CYCLE")
fi

if [ "$MQTT_HOST" != "" ] ; then
	CMD_ARGS+=("--mqttuser=$MQTT_USER")
	CMD_ARGS+=("--mqttpass=$MQTT_PASS")
	CMD_ARGS+=("--mqtthost=$MQTT_HOST")
	if [ "$MQTT_PORT" != "" ] ; then
		CMD_ARGS+=("--mqttport=$MQTT_PORT")
	fi
	if [ "$MQTT_TOPIC" != "" ] ; then
		CMD_ARGS+=("--mqtttopic=$MQTT_TOPIC")
	fi
	if [ "$HOMEASSISTANT_AUTO_DISCOVERY_PREFIX" != "" ] ; then
		CMD_ARGS+=("--mqtthass=$HOMEASSISTANT_AUTO_DISCOVERY_PREFIX")
	fi
else
	CMD_ARGS+=("--mqttuser=")
fi

RPI_FANSPEED_COMMAND_LINE="${CMD_ARGS[@]@Q}"

if [ "$RASPI_FANSPEED_INSTALL_TYPE" == "SHOWCLI" ] ; then

	echo
	echo "Command to start the service in foreground"
	echo
	echo "$RPI_FANSPEED_COMMAND_LINE"
	exit 0

elif [ "$RASPI_FANSPEED_INSTALL_TYPE" != "INSTALL" ] ; then

	echo "invalid RASPI_FANSPEED_INSTALL_TYPE"
	exit 1

fi

PIP_INSTALL="$PIP_BIN install $PIP_LIBS"

if [ ! -x "$PYTHON_BIN" ] ; then
	echo "$PYTHON_BIN" not found
	exit 1
fi
if [ ! -x "$PIP_BIN" ] ; then
	echo "$PIP_BIN" not found
	exit 1
fi

function escape_sed {
	ESCAPED_SED=$((echo "$@"|sed -r 's/([\$\.\*\/\[\\^])/\\\1/g'|sed 's/[]]/\[]]/g')>&1)
}

echo "Installing python3 libraries: $PIP_LIBS"

$PIP_INSTALL

escape_sed "#!$PYTHON_BIN"
cat "$RPI_FANSPEED_SRC" | sed "1 s/^.*$/$ESCAPED_SED/" > "$RPI_FANSPEED_BIN" && \
chmod o+x "$RPI_FANSPEED_BIN" || \
echo "Failed to copy $RPI_FANSPEED_SRC to $RPI_FANSPEED_BIN"

if [ -x "$SYSTEMD_DIR" ] ; then
	echo Installing systemd service
	escape_sed "$RPI_FANSPEED_BIN"
	"$SYSTEMCTL_BIN" stop "$SERVICE_NAME" &> /dev/null
	"$SYSTEMCTL_BIN" disable "$SERVICE_NAME" &> /dev/null
	cat "systemd/$SERVICE_NAME.service" | sed "s/\$RPI_FANSPEED_COMMAND_LINE/$ESCAPED_SED/" > "$SYSTEMD_DIR/raspi_fanspeed.service" && \
	"$SYSTEMCTL_BIN" enable "$SERVICE_NAME" && \
	"$SYSTEMCTL_BIN" start "$SERVICE_NAME" && echo -e "Success!\n\n" || \
	echo "Failed to start service $SERVICE_NAME"
else
	echo "$SYSTEMD_DIR" not found
fi

echo -e "\nservice command line\n${RPI_FANSPEED_COMMAND_LINE}\n"
echo -e "try\n$RPI_FANSPEED_BIN --help\n"

