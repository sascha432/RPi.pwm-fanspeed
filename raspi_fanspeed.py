#!/usr/bin/python3

import pigpio
import signal
import time
import sys
import os
import os.path
import subprocess
import argparse
import json
import socket
import shlex
import syslog
import re
import hashlib
import glob

VERSION = '0.0.1'

pwm_level = {}
cmd = { "errors": 0, 'sig_counter': 0 }

class NoMQTT:
    def __init__(self):
        self.client = False

    def server(self):
        return 'disabled'

    def client_begin(self):
        pass

    def client_end(self):
        pass

    def client_publish(self, temperature, speed):
        pass

mqtt = NoMQTT()
pi = pigpio.pi()
hostname = socket.gethostname()
if hostname.startswith('localhost'):
    hostname = 'RPi.fanspeed.' + hostname

parser = argparse.ArgumentParser(description='adjustable fanspeed with temperature monitoring')
parser.add_argument('-i', '--interval', help='fan speed update interval in seconds', type=int, default=10)
parser.add_argument('--min', type=float, help='minimum temperature to turn on fan in \u00b0C (30-70)', default=45)
parser.add_argument('--max', type=float, help='maximum fan speed if temperature exceeds this value (40-90)', default=70)
parser.add_argument('--min-fan', type=float, help='minimum fan speed in %%', default=40)
parser.add_argument('-p', '--pin', type=int, choices=[12, 13, 18, 19], help='fan PWM pin. must be capable of hardware PWM', default=19)
parser.add_argument('-f', '--frequency', type=int, help='PWM frequency', default=32000)
parser.add_argument('-S', '--print-speed', action='store_true', help='Print fan speed table and exit', default=False)
parser.add_argument('-E', '--onexit-speed', type=float, help='turn fan to 30-100%% when exiting. -1 disable fan on exit', default=75)
parser.add_argument('--mqttuser', type=str, default=None, help="use phyton mqtt client to connect to MQTT")
parser.add_argument('--mqttpass', type=str, default='')
parser.add_argument('--mqtttopic', type=str, default='home/{device_name}/{entity}')
parser.add_argument('--mqtthass', type=str, default='homeassistant', help="home assistant MQTT auto discovery prefix")
parser.add_argument('--mqttupdateinterval', type=int, default=60, help="mqtt update interval (30-900 seconds)")
parser.add_argument('--mqttdevicename', type=str, default=hostname, help='mqtt device name')
parser.add_argument('-H', '--mqtthost', type=str, default='localhost', help="set to empty string to disable MQTT")
parser.add_argument('-P', '--mqttport', type=int, default=1883)
parser.add_argument('-L', '--log', type=str, help='write temperature and speed into this file i.e. --log=/var/log/tempmon.json', default=None)
parser.add_argument('--no-json', action='store_true', default=False)
parser.add_argument('-V', '--version', action='store_true', default=False)
parser.add_argument('-v', '--verbose', action='store_true', default=False)
parser.add_argument('--temp', type=float, default=25.0)
args = parser.parse_args()

if args.version:
    print("RPi fanspeed version %s" % VERSION)
    sys.exit(0)

# normalize values
args.min_fan = min(100, max(0, args.min_fan))
args.min = min(100, max(0, args.min))
args.max = min(100, max(args.min, args.max))
args.onexit_speed = args.onexit_speed != -1 and min(100.0, max(args.onexit_speed, float(args.min_fan))) or 0
args.json = not args.no_json

if args.min_fan<30:
    print('WARNING! minimum level below 30%. make sure the fan turns on at low levels')

def verbose(msg):
    global args
    if args.verbose:
        print(msg)

def error(msg):
    global args
    if args.verbose and (sys.stderr.fileno()!=2 or sys.stdout.fileno()!=1):
        print(msg)
    write(sys.stderr, msg)
    write(sys.stderr, os.linesep)
    syslog.syslog(syslog.LOG_ERR, msg)

def error_and_exit(msg, code=-1):
    error(msg)
    sys.exit(code)

class MQTT(NoMQTT):
    def __init__(self, user, passwd, host, port, device_name, topic, client, update_rate = 60, hass_autoconfig_prefix = 'homeassistant'):
        NoMQTT.__init__(self)
        self.next_update = time.monotonic();
        self.user = user
        self.passwd = passwd
        self.host = host
        self.port = port
        self.keepalive = update_rate * 2
        self.connected = False
        self.topic = type('obj', (object,), {
            'status': topic.format(device_name=device_name,entity='RPi.fanspeed/status'),
            'json': topic.format(device_name=device_name,entity='RPi.fanspeed/json'),
        })()
        self.device_name = device_name
        self.auto_discovery = type('obj', (object,), {
            'prefix': hass_autoconfig_prefix,
            'thermal_zone0': '{auto_discovery_prefix}/sensor/{device_name}_thermal-zone0/config',
            'duty_cycle': '{auto_discovery_prefix}/sensor/{device_name}_fan-duty-cycle/config',
            'fan_rpm': '{auto_discovery_prefix}/sensor/{device_name}_fan-rpm/config',
        })()
        self.client = client

    def server(self):
        if self.user=='' and self.passwd=='':
            return 'anonymous@%s:%u' % (self.host, self.port)
        return '%s@%s:%u' % (self.user, self.host, self.port)

    def on_connect(self, client, userdata, flags, rc):
        verbose("connected to mqtt server")
        self.connected = True
        self.client.publish(self.topic.status, payload="1")
        if self.auto_discovery.prefix:
            self.send_homeassistant_auto_config()


    def get_mac_addresses(self):
        parts = []
        for iface in glob.glob('/sys/class/net/*/address'):
            try:
                with open(iface, 'r') as f:
                    mac = f.readline().strip()
                    if not '00:00:00' in mac:
                        parts.append(mac)
            except:
                pass
        return parts

    def create_hass_auto_conf(self, entity, unit, value_json_name):
        m = hashlib.md5()
        m.update(self.device_name.encode())
        m.update(b':')
        m.update(entity.encode())
        m.update(b':')
        unique_id = m.digest().hex()[0:11]

        connections = []
        for mac_addr in self.get_mac_addresses():
            connections.append(["mac", mac_addr])

        return json.dumps({
            "name": "%s_%s" % (self.device_name, entity),
            "platform": "mqtt",
            "unique_id": unique_id,
            "device": {
                "identifiers": [ unique_id ],
                "connections": connections,
                "model":"RPi.fanspeed",
                "sw_version": VERSION,
                "manufacturer": "KFCLabs"
            },
            "availability_topic": self.topic.status,
            "payload_available": 1,
            "payload_not_available": 0,
            "state_topic": self.topic.json,
            "unit_of_measurement": unit,
            "value_template": "{{ value_json.%s }}" % value_json_name
        }, ensure_ascii=False, indent=None, separators=(',', ':'))

    def send_homeassistant_auto_config(self):
        verbose('publishing homeassistant auto discovery')
        self.client.publish(self.auto_discovery.thermal_zone0, payload=self.create_hass_auto_conf('thermal_zone0', "\u00b0C", 'temperature'), retain=True)
        self.client.publish(self.auto_discovery.duty_cycle, payload=self.create_hass_auto_conf('duty_cycle', '%', 'duty_cycle'), retain=True)
        self.client.publish(self.auto_discovery.thermal_zone0, payload=self.create_hass_auto_conf('fan_rpm', "rpm", 'rpm'), retain=True)

    def on_disconnect(self, client, userdata, rc):
        verbose("disconnected from mqtt server")
        self.connected = False

    def on_message(self, client, userdata, msg):
        print(msg.topic+" "+str(msg.payload))

    def client_begin(self):
        self.client.on_connect = mqtt.on_connect
        self.client.on_disconnect = mqtt.on_disconnect
        self.client.on_message = mqtt.on_message
        self.client.reconnect_delay_set(min_delay=1, max_delay=300)
        self.client.will_set(mqtt.topic.status, payload='0', qos=0, retain=True)
        self.client.connect_async(mqtt.host, port=mqtt.port, keepalive=mqtt.keepalive)
        self.client.loop_start();
        verbose('connecting to mqtt server %s' % (mqtt.server()))

    def client_end(self):
        if self.connected:
            self.client.disconnect();
        self.client.loop_stop(force=False)
        time.sleep(1.0)
        self.client.loop_stop(force=True)
        self.client = False

    def client_publish(self, temperature, speed):
        if self.client and self.connected and time.monotonic()>=self.next_update:
            self.next_update = time.monotonic() + self.next_update
            json_str = get_json(speed, 0, True)
            verbose('publish mqtt %s' % json_str)
            self.client.publish(mqtt.topic.json, payload=json_str, retain=True);
            self.client.publish(mqtt.topic.status, payload="1", retain=False)


try:
    import paho.mqtt.client
except:
    mqtt = NoMQTT()
else:
    mqtt = MQTT(args.mqttuser, args.mqttpass, args.mqtthost, args.mqttport, args.mqttdevicename, args.mqtttopic, paho.mqtt.client.Client(), update_rate=args.mqttupdateinterval, hass_autoconfig_prefix=args.mqtthass)

# RPM is calculated from PWM level for a specific fan
def speed_to_rpm(x):
    return max(0, int((-3.7624554951688460e+003 * x**0) +(1.7478905554411597e+002 * x**1) + (-6.3080904805125659e-001 * x**2)))

def temp_to_speed(temp):
    if temp < args.min:
        return 0
    speed = (temp - args.min) / (args.max - args.min) * 100
    speed = (speed * (1.0 - args.min_fan / 100.0)) + args.min_fan
    return min(100.0, speed)

def get_json(speed, indent=None, force=False, time = None):
    if args.no_json and force==False:
        return '%.0f%% @ %.2f\u00b0C' % (args.temp, speed)
    data = { 'temperature': '%.2f' % args.temp, 'duty_cycle': '%.2f' % speed, 'rpm': speed_to_rpm(speed) }
    if time!=None:
        data['ts'] = time
    return json.dumps(data, indent=indent)

def str_valid(s):
    if not isinstance(s, str):
        return False
    if not s.strip():
        return False
    return True

def update_log(args, speed):
    # mqtt
    mqtt.client_publish(args.temp, speed)

    if not str_valid(args.log):
        return
    if re.match('/^(NUL{1,2}|nul{1,2}|nul|\/dev\/nul{1,2})$/', args.log):
        return
    if args.log=='-':
        print(get_json(speed))
    else:
        verbose('temperature %.2f speed %.2f%% log %s' % (args.temp, speed, args.log))
        with open(args.log, 'w') as f:
            f.write(get_json(speed, time=int(time.time())))

# pin 12, 13, 18 and 19 supported
# level 0.0-100.0
def set_pwm(pi, pin, level, frequency = None) :
    if frequency==None:
        frequency = args.frequency
    if not pin in pwm_level:
        pwm_level[pin] = 0

    if level<args.min_fan:
        level = 0

    print(level)
    if pwm_level[pin] == 0 and level>0 and level<40:
        # short boost to spin up if less than 40%
        # max. boost 50%, lower over 650ms to level
        verbose('boost %.0f%%:100ms, %.0f%%:250ms, %.0f%%:150ms, %.0f%%:150ms, %.0f%%' % (level, 50, ((level + 50) / 2), ((level + 25) / 2), level))
        pi.hardware_PWM(pin, frequency, int(level * 10000))
        time.sleep(100)
        pi.hardware_PWM(pin, frequency, int(50 * 10000))
        time.sleep(250)
        pi.hardware_PWM(pin, frequency, int(((level + 50) / 2.0) * 10000))
        time.sleep(150)
        pi.hardware_PWM(pin, frequency, int(((level + 25) / 2.0) * 10000))
        time.sleep(150)

    pi.hardware_PWM(pin, frequency, int(level * 10000))
    pwm_level[pin] = level

    # mqtt
    if mqtt.connected:
        mqtt.client_publish(args.temp, speed)

def signal_handler(sig, frame):
    verbose('SIGINT')
    cmd['sig_counter'] += 1
    if cmd['sig_counter']>1:
        verbose('sending SIGTERM')
        os.kill(os.getpid(), signal.SIGTERM)

    speed = args.onexit_speed
    set_pwm(pi, args.pin, speed)
    update_log(args, speed)

    if cmd['sig_counter']>1:
        print('sending SIGKILL')
        time.sleep(1.0)
        os.kill(os.getpid(), signal.SIGKILL)

    if mqtt.client!=False:
        verbose('disconnecting from mqtt server')
        mqtt.client_end()
    sys.exit(0)


# print table
if args.verbose or args.print_speed:
    i = 30
    j = -1
    # incr = int((temp_to_speed(90) - temp_to_speed(30)) / 60.0) + 1
    json_output = {}
    while i<=90:
        n = temp_to_speed(i)
        # i += incr
        key = '%03.0f%%' % float(n)
        if key not in json_output:
            json_output[key] = '%.1f\u00b0C' % i
        i += 1

    if args.json:
        print(json.dumps(json_output, indent=2, ensure_ascii=not sys.getdefaultencoding().startswith('utf') and '<stdin>' in sys.stdin.name))
    else:
        for key, val in json_output.items():
            print('%s: %s' % (key, val))

# and exit
if args.print_speed:
    sys.exit(0)

# check if mqtt is enabled
if args.mqttuser!=None:
    if mqtt.client==False:
        error('MQTT client not available')
    else:
        mqtt.client_begin()
        mqttupdateinterval = max(30, min(900, args.mqttupdateinterval))
        if args.interval>args.mqttupdateinterval:
            args.interval = args.mqttupdateinterval

# sigint handler
signal.signal(signal.SIGINT, signal_handler)

if args.verbose:
    verbose('min. fan speed %d%%' % args.min_fan)
    verbose('min. temperature %.2f°C' % args.min)
    verbose('max. temperature %.2f°C' % args.max)
    verbose('check interval %d seconds' % args.interval)
    verbose('mqtt server %s' % mqtt.server())
    if mqtt.client!=False:
        verbose('mqtt update interval %d seconds' % args.mqttupdateinterval)
        verbose('mqtt device name %s' % args.mqttdevicename)
        verbose('homeassistant prefix %s' % args.mqtthass)

# loop_forever
while True:
    with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
        args.temp = float(f.readline()) / 1000.0
    speed = temp_to_speed(args.temp)
    verbose('temp %.2f speed %.2f%% rpm ~%u' % (args.temp, speed, speed_to_rpm(speed)))

    set_pwm(pi, args.pin, speed)
    update_log(args, speed)

    if args.interval<1:
        verbose('interval < 1 second, exiting...')
        break

    time.sleep(args.interval)
