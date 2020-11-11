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

hostname = socket.gethostname()
if hostname.startswith('localhost'):
    hostname = 'RPi.fanspeed.' + hostname

parser = argparse.ArgumentParser(description='Set fan speed')
parser.add_argument('-i', '--interval', help='Fan speed update interval in seconds', type=int, default=60)
parser.add_argument('--min', type=int, help='Minimum temperature to turn on fan in °C', default=45)
parser.add_argument('--max', type=int, help='Maximum fan speed if temperature exceeds this value', default=70)
parser.add_argument('--min-fan', type=int, help='Minimum fan speed in %', default=40)
parser.add_argument('-p', '--pin', type=int, help='output PIN', default=19)
parser.add_argument('-f', '--frequency', type=int, help='PWM frequency', default=32000)

parser.add_argument('-ps', '--print-speed', action='store_true', help='Print fan speed for temperature and end program', default=False)
parser.add_argument('-nj', '--no-json', action='store_true', default=False)
parser.add_argument('-E', '--exit-value', type=float, help='Turn fan to 30-100% when exiting the program, set -1 to disable the fan', default=75)
parser.add_argument('-C', '--cmd', type=str, help='execute command and pipe temperature and speed', default='/usr/bin/mosquitto_pub -r -t \'home/{hostname}/RPi.fanspeed\' -m \'{message}\''.format(hostname=hostname, message='{message}'))
parser.add_argument('--log', type=str, help='Write temperature and speed info this file', default=None) #'/var/log/tempmon.json'
parser.add_argument('-t', '--temp', type=float, help='temperature preset', default=25.0)
parser.add_argument('-v', '--verbose', action='store_true', default=False)
args = parser.parse_args()

min_fan = min(1, max(0, args.min_fan / 100.0))
args.json = not args.no_json

def verbose(msg):
    if args.verbose:
        print(msg)

def error(msg):
    if args.verbose and (sys.stderr.fileno()!=2 or sys.stdout.fileno()!=1):
        print(msg, file=sys.stdout)
    print(msg, file=sys.stderr)
    syslog.syslog(syslog.LOG_ERR, msg)

def temp_to_speed(temp):
    if temp < args.min:
        return 0
    speed = (temp - args.min) / (args.max - args.min)
    speed = (speed * (1.0 - min_fan)) + min_fan
    return min(1.0, speed) * 100.0

def get_json(speed, indent=None):
    return json.dumps({'temperature': round(args.temp, 2), 'speed': round(speed, 2)}, indent=indent)

def write(f, speed):
    f.write(get_json(speed))

cmd_errors = 0

def update_log(args, speed):
    global cmd_errors
    if args.log==None and args.cmd!=None:
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
    else:
        if args.log.lower() in ['/dev/nul', '/dev/null', 'null', 'nul']:
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
    sys.exit(0)

args.exit_value = args.exit_value != -1 and min(100.0, max(args.exit_value, float(args.min_fan))) or 0

if args.verbose:
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
