#!/bin/bash

PYTHON_BIN=$(which python3)
PIP_BIN=$(which pip3)
PIP_LIBS=pigpio
SYSTEMD_DIR=/etc/systemd/system
RPI_FANSPEED_SRC=$(pwd)/raspi_fanspeed.py
RPI_FANSPEED_BIN=/usr/bin/raspi_fanspeed
SERVICE_NAME=raspi_fanspeed

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

"$PIP_BIN" install $PIP_LIBS

escape_sed "#!$PYTHON_BIN"
cat "$RPI_FANSPEED_SRC" | sed "1 s/^.*$/$ESCAPED_SED/" > "$RPI_FANSPEED_BIN" && \
chmod o+x "$RPI_FANSPEED_BIN" || \
echo "Failed to copy $RPI_FANSPEED_SRC to $RPI_FANSPEED_BIN"

if [ -x "$SYSTEMD_DIR" ] ; then
	echo Installing systemd service
	escape_sed "$RPI_FANSPEED_BIN"
	cat "systemd/$SERVICE_NAME.service" | sed "s/\$RPI_FANSPEED_BIN/$ESCAPED_SED/" > "$SYSTEMD_DIR/raspi_fanspeed.service" && \
	systemctl enable "$SERVICE_NAME" && \
	systemctl start "$SERVICE_NAME" && echo "Success!" || \
	echo "Failed to start service $SERVICE_NAME"
else
	echo "$SYSTEMD_DIR" not found
fi

echo -e "\ntry\n$RPI_FANSPEED_BIN --help"
