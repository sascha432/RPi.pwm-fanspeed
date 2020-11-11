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

client = False
mqtt = {}
try:
    import paho.mqtt.client
    client = paho.mqtt.client.Client()
except:
    pass

hostname = socket.gethostname()
if hostname.startswith('localhost'):
    hostname = 'RPi.fanspeed.' + hostname

parser = argparse.ArgumentParser(description='Set fan speed')
parser.add_argument('-i', '--interval', help='Fan speed update interval in seconds', type=int, default=60)
parser.add_argument('--min', type=int, help='Minimum temperature to turn on fan in \u00b0C', default=45)
parser.add_argument('--max', type=int, help='Maximum fan speed if temperature exceeds this value', default=70)
parser.add_argument('--min-fan', type=int, help='Minimum fan speed in %%', default=40)
parser.add_argument('-p', '--pin', type=int, help='fan enable PIN', default=19)
parser.add_argument('-f', '--frequency', type=int, help='PWM frequency', default=32000)
parser.add_argument('-S', '--print-speed', action='store_true', help='Print fan speed table and exit', default=False)
parser.add_argument('-E', '--exit-value', type=float, help='Turn fan to 30-100%% when exiting the program, set to -1 to disable the fan on exit', default=75)
parser.add_argument('--mqttuser', type=str, default=None)
parser.add_argument('--mqttpass', type=str, default='')
parser.add_argument('--mqtttopic', type=str, default='home/{hostname}/{entity}')
parser.add_argument('-H', '--mqtthost', type=str, default='localhost')
parser.add_argument('-P', '--mqttport', type=int, default=1883)
parser.add_argument('-C', '--cmd', type=str, help='execute command and pipe temperature and speed "/usr/bin/mosquitto_pub -r -t \'home/{hostname}/RPi.fanspeed/json\' -m \'{message}\'"', default=None)#'/usr/bin/mosquitto_pub -r -t \'home/{hostname}/RPi.fanspeed/json\' -m \'{json}\''.format(hostname=hostname))
parser.add_argument('-t', '--temp', type=float, help='temperature preset', default=25.0)
parser.add_argument('-v', '--verbose', action='store_true', default=False)
parser.add_argument('--log', type=str, help='Write temperature and speed into this file instead of executing --cmd, --log=/var/log/tempmon.json', default=None) #'/var/log/tempmon.json'
parser.add_argument('--no-json', action='store_true', default=False)
args = parser.parse_args()

min_fan = min(1, max(0, args.min_fan / 100.0))
args.json = not args.no_json

def verbose(msg):
    if args.verbose:
        print(msg)

def error(msg):
    if args.verbose and (sys.stderr.fileno()!=2 or sys.stdout.fileno()!=1):
        print(msg)
    write(sys.stderr, msg)
    write(sys.stderr, os.linesep)
    syslog.syslog(syslog.LOG_ERR, msg)

def error_and_exit(msg, code=-1):
    error(msg)
    sys.exit(code)

def temp_to_speed(temp):
    if temp < args.min:
        return 0
    speed = (temp - args.min) / (args.max - args.min)
    speed = (speed * (1.0 - min_fan)) + min_fan
    return min(1.0, speed) * 100.0

def get_json(speed, indent=None, force=False):
    if args.no_json and force==False:
        return '%.0f%% @ %.2f\u00b0C' % (args.temp, speed)
    return json.dumps({'temperature': str(round(args.temp, 2)), 'speed': str(round(speed, 2))}, indent=indent)

def write(f, speed):
    f.write(get_json(speed))

cmd_errors = 0

def update_log(args, speed):
    global cmd_errors

    # mqtt
    if client!=False:
        verbose('publish')
        client.publish(mqtt.topic.json, payload=get_json(speed, 0, True), retain=True);
        client.publish(mqtt.topic.status, payload="1")

    # command
    if args.cmd!=None and args.cmd.strip()!='':
        cmd = args.cmd.strip()
        args = shlex.split(cmd, posix=True)
        parts = []
        for val in args:
            val = val.format(message=get_json(speed))
            parts.append(shlex.quote(val))
        cmd_str = ' '.join(parts)
        verbose('executing command: %s' % cmd_str)
        return_code = subprocess.run(cmd_str, shell=True).returncode
        if return_code!=0:
            error('Failed to execute command: exit code %u: %s' % (return_code, cmd_str))
            cmd_errors += 1
            if cmd_errors>10:
                error('Stopping command: %d error(s): %s' % (cmd_errors, cmd_str))
                args.cmd = None
        else:
            cmd_errors = 0

    # log file
    if args.log==None or args.log.strip()=='':
        return
    if isinstance(args.log, str) and re.match('/^(NUL{1,2}|nul{1,2}|nul|\/dev\/nul{1,2})$/', args.log):
        return
    if args.log=='-':
        write(sys.stdout, speed)
        print()
    else:
        verbose('temperature %.2f speed %.2f%% log %s' % (args.temp, speed, args.log))
        with open(args.log, 'w') as f:
            write(f, speed)


def signal_handler(sig, frame):
    verbose('SIGINT')
    speed = args.exit_value
    pi.hardware_PWM(19, 32000, int(speed * 10000))
    update_log(args, speed)
    if client!=False:
        verbose('disconnecting from mqtt server')
        client.disconnect();
        client.loop_stop(force=False)
        time.sleep(1.0)
        client.loop_stop(force=True)
        client = False
    sys.exit(0)

args.exit_value = args.exit_value != -1 and min(100.0, max(args.exit_value, float(args.min_fan))) or 0

if args.mqttuser!=None:
    if client==False:
        error('MQTT client not available')
    else:
        class MQTT:
            def __init__(self, user, passwd, host, port, hostname, topic, client):
                self.user = user
                self.passwd = passwd
                self.host = host
                self.port = port
                self.keepalive = 60
                self.thread_id = 1000
                self.topic = type('obj', (object,), {
                    'status': topic.format(hostname=hostname,entity='RPi.fanspeed/status'),
                    'json': topic.format(hostname=hostname,entity='RPi.fanspeed/json'),
                })()
                self.auto_discovery = type('obj', (object,), {
                    'prefix': 'homeassistant',
                    'thermal': '{auto_discovery_prefix}/sensor/{hostname}/cpu-thermal/config',
                    'fanspeed': '{auto_discovery_prefix}/sensor/{hostname}/cpu-fanspeed/config',
                })()
                self.client = client

            def server(self):
                return '%s@%s:%u' % (self.user, self.host, self.port)

            def on_connect(self, client, userdata, flags, rc):
                print("Connected with result code "+str(rc))
                self.client.publish(self.topic.status, payload="1")

            def on_message(self, client, userdata, msg):
                print(msg.topic+" "+str(msg.payload))

            # def start_thread(self, callback, args = (), delay = 0):
            #     thread = threading.Thread(target=self.___thread, args=(self.thread_id, callback, args, delay), daemon=True)
            #     thread.start()
            #     self.thread_id += 1
            #     return thread

            # self.start_thread(, (pin, value, duration_milliseconds))



        mqtt = MQTT(args.mqttuser, args.mqttpass, args.mqtthost, args.mqttport, hostname, args.mqtttopic, client)

        client.on_connect = mqtt.on_connect
        client.on_message = mqtt.on_message
        client.reconnect_delay_set(min_delay=1, max_delay=300)
        client.will_set(mqtt.topic.status, payload='0', qos=0, retain=True)
        client.connect_async(mqtt.host, port=mqtt.port, keepalive=mqtt.keepalive)
        # client.loop(timeout=1.0)
        client.loop_start();
        verbose('connecting to mqtt server %s' % (mqtt.server()))


if args.verbose or args.print_speed:
    i = 30
    j = -1
    incr = temp_to_speed(90) - temp_to_speed(30)
    incr = int(incr / 60.0) + 1
    json_output = {}
    while i<90:
        n = temp_to_speed(i)
        i += incr
        json_output['%03.0f%%' % float(n)] = '%.1f\u00b0C' % i
    if args.print_speed or args.verbose:
        if args.json:
            print(json.dumps(json_output, indent=2, ensure_ascii=not sys.getdefaultencoding().startswith('utf') and '<stdin>' in sys.stdin.name))
        else:
            for key, val in json_output.items():
                print('%s: %s' % (key, val))

signal.signal(signal.SIGINT, signal_handler)
pi = pigpio.pi()

while not args.print_speed:
    with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
        args.temp = float(f.readline()) / 1000.0
    speed = temp_to_speed(args.temp)
    verbose('temp %.2f speed %.2f%%' % (args.temp, speed))

    dcn = int(speed * 10000)
    pi.hardware_PWM(args.pin, args.frequency, dcn)
    update_log(args, speed)

    if args.interval<1:
        verbose('interval < 1 second, exiting...')
        break

    time.sleep(args.interval)

