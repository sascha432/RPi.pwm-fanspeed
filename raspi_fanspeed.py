#!/usr/bin/python3

import pigpio
import signal
import time
import sys
import os
import os.path
import argparse
import json
import socket
try:
    import syslog
except:
    syslog = None
import re
import hashlib
import glob

VERSION = '0.0.1'

class RPiFanSpeedControl(object):

    def __init__(self, pigpio):
        self.pidfile = '/var/run/raspi_fanspeed.pid'
        self.speed = 50.0
        self.temp = 25.0
        self.args = None
        self.rpm = 0
        self.pigpio = pigpio

    def print_version(self):
        print("RPi.fanspeed version %s" % VERSION)
        sys.exit(0)

    def set_args(self, args):
        # normalize values
        args.min_fan = min(100, max(0, args.min_fan))
        args.min = min(100, max(0, args.min))
        args.max = min(100, max(args.min, args.max))
        args.onexit_speed = args.onexit_speed != -1 and min(100.0, max(args.onexit_speed, float(args.min_fan))) or 0
        if args.pid!=None and args.pid:
            self.pidfile = args.pid

        if args.min_fan<30:
            print('WARNING! minimum level below 30%. make sure the fan turns on at low levels')

        self.args = args

    def create_pid(self):
        try:
            with open(self.pidfile, 'w') as f:
                f.write(os.getpid())
        except:
            pass

    def remove_pid(self):
        if os.exists(self.pidfile):
            try:
                os.unlink(self.pidfile)
            except:
                pass

    def get_temp(self):
        return float(self.temp)

    def set_temp(self, temp):
        self.temp = temp

    def get_speed(self):
        return float(self.speed)

    def get_rpm(self):
        return int(self.rpm)

    def set_speed(self, speed):
        self.speed = speed

    # # RPM is calculated from PWM level for a specific fan
    # def speed_to_rpm(self, x):
    #     return max(0, int((-3.7624554951688460e+003 * x**0) +(1.7478905554411597e+002 * x**1) + (-6.3080904805125659e-001 * x**2)))

    def temp_to_speed(self, temp):
        if temp < args.min:
            return 0
        speed = (temp - args.min) / (args.max - args.min) * 100
        speed = (speed * (1.0 - args.min_fan / 100.0)) + args.min_fan
        return float(min(100.0, speed))

    def get_json(self, indent=None, force=False, ts=None):
        if ts==None or ts==True:
            ts = time.time()
        data = {
            'temperature': ('%.2f' % self.get_temp()),
            'duty_cycle': ('%.2f' % self.get_speed()),
            'rpm': ('%u' % self.get_rpm()),
            'ts': int(time.time()),
            # 'localtime': time.strftime('%FT%T %Z', time.localtime(ts))
        }
        return json.dumps(data, indent=indent)



class NoMQTT:
    def __init__(self):
        self.signal_counter = 0

    def server(self):
        return 'none'

    def client_begin(self):
        pass

    def client_end(self):
        pass

    def client_publish(self, temperature, speed):
        pass

    def available(self):
        return False

class reader:
   def __init__(self, pi, gpio, weighting=0.0):
      self.pi = pi
      self.gpio = gpio

      if weighting < 0.0:
         weighting = 0.0
      elif weighting > 0.99:
         weighting = 0.99

      self._new = 1.0 - weighting # Weighting for new reading.
      self._old = weighting       # Weighting for old reading.

      self._high_tick = None
      self._period = None
      self._high = None

      pi.set_mode(gpio, pigpio.INPUT)

      self._cb = pi.callback(gpio, pigpio.EITHER_EDGE, self._cbf)

   def _cbf(self, gpio, level, tick):

      if level == 1:

         if self._high_tick is not None:
            t = pigpio.tickDiff(self._high_tick, tick)

            if self._period is not None:
               self._period = (self._old * self._period) + (self._new * t)
            else:
               self._period = t

         self._high_tick = tick

      elif level == 0:

         if self._high_tick is not None:
            t = pigpio.tickDiff(self._high_tick, tick)

            if self._high is not None:
               self._high = (self._old * self._high) + (self._new * t)
            else:
               self._high = t

   def frequency(self):
      if self._period is not None:
         return 1000000.0 / self._period
      else:
         return 0.0

   def pulse_width(self):
      if self._high is not None:
         return self._high
      else:
         return 0.0

   def duty_cycle(self):
      if self._high is not None:
         return 100.0 * self._high / self._period
      else:
         return 0.0

   def cancel(self):
      self._cb.cancel()

# PWM_GPIO = 4
# RUN_TIME = 60.0
# SAMPLE_TIME = 2.0

pi = pigpio.pi()
# p = read_PWM.reader(pi, PWM_GPIO)
# start = time.time()
# while (time.time() - start) < RUN_TIME:
#     time.sleep(SAMPLE_TIME)
#     f = p.frequency()
#     pw = p.pulse_width()
#     dc = p.duty_cycle()
#     print("f={:.1f} pw={} dc={:.2f}".format(f, int(pw+0.5), dc))
# p.cancel()


fsc = RPiFanSpeedControl(pi)
mqtt = NoMQTT()

hostname = socket.gethostname()
if hostname.startswith('localhost'):
    hostname = 'RPi.fanspeed.' + hostname

parser = argparse.ArgumentParser(description='adjustable fanspeed with temperature monitoring')
parser.add_argument('-i', '--interval', help='fan speed update interval in seconds', type=int, default=10)
parser.add_argument('--set', type=float, help='set speed in %%', default=None)
parser.add_argument('--measure', type=float, help='measure rpm for n seconds and exit', default=None)
parser.add_argument('--min', type=float, help='minimum temperature to turn on fan in \u00b0C (30-70)', default=45)
parser.add_argument('--max', type=float, help='maximum fan speed if temperature exceeds this value (40-90)', default=70)
parser.add_argument('--min-fan', type=float, help='minimum fan speed in %%', default=40)
parser.add_argument('-p', '--pin', type=int, choices=[12, 13, 18, 19], help='fan PWM pin. must be capable of hardware PWM', default=19)
parser.add_argument('--rpm-pin', type=int, help='read RPM signal from pin', default=16)
parser.add_argument('-f', '--frequency', type=int, help='PWM frequency', default=32000)
parser.add_argument('-S', '--print-speed', action='store_true', help='Print fan speed table and exit', default=False)
parser.add_argument('-E', '--onexit-speed', type=float, help='turn fan to 30-100%% when exiting. -1 disable fan on exit', default=75)
parser.add_argument('--mqttuser', type=str, default=None, help="use phyton mqtt client to connect to MQTT")
parser.add_argument('--mqttpass', type=str, default='')
parser.add_argument('--mqttdevicename', type=str, default=hostname, help='mqtt device name')
parser.add_argument('--mqtttopic', type=str, default='home/{device_name}/{entity}')
parser.add_argument('--mqtthass', type=str, default=None)
parser.add_argument('--mqttupdateinterval', type=int, default=60, help="mqtt update interval (30-900 seconds)")
parser.add_argument('-H', '--mqtthost', type=str, default=None)
parser.add_argument('-P', '--mqttport', type=int, default=1883)
parser.add_argument('-L', '--log', type=str, help='write temperature and speed to this file i.e. --log=/var/log/tempmon.json', default=None)
parser.add_argument('-V', '--version', action='store_true', default=False)
parser.add_argument('-v', '--verbose', action='store_true', default=False)
parser.add_argument('--pid', type=str, default=None)
args = parser.parse_args()

if args.version:
    fsc.print_version()

fsc.set_args(args)

def verbose(msg):
    if fsc.args.verbose:
        print(msg)

def error(msg):
#    if fsc.args.verbose and (sys.stderr.fileno()!=2 or sys.stdout.fileno()!=1):
    print(msg)
#    sys.stderr.write(msg)
#    sys.stderr.write(os.linesep)
    if syslog!=None:
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
        self.keepalive = max(15, int(update_rate / 4))
        self.update_rate = update_rate;
        self.connected = False
        self.topic = type('obj', (object,), {
            'status': topic.format(device_name=device_name,entity='RPi.fanspeed/status'),
            'json': topic.format(device_name=device_name,entity='RPi.fanspeed/json'),
        })()
        self.device_name = device_name
        self.auto_discovery = type('obj', (object,), {
            'prefix': hass_autoconfig_prefix,
            'thermal_zone0': '{auto_discovery_prefix}/sensor/{device_name}_thermal-zone0/config',
            'duty_cycle': '{auto_discovery_prefix}/sensor/{device_name}_duty-cycle/config',
            'rpm': '{auto_discovery_prefix}/sensor/{device_name}_rpm/config',
        })()
        self.client = client

    def server(self):
        account = (not self.user or not self.passwd) and 'anonymous' or self.user
        return '%s@%s:%u' % (account, self.host, self.port)

    def on_connect(self, client, userdata, flags, rc):
        verbose("connected to mqtt server")
        self.next_update = time.monotonic() + 5
        self.connected = True
        self.client.will_set(self.topic.status, payload='0', qos=2, retain=True)
        self.publish(self.topic.status, payload="1", retain=True)
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

    def get_topic(self, topic, payload):
        return topic.format(auto_discovery_prefix=self.auto_discovery.prefix, json=payload, device_name=self.device_name)

    def publish(self, topic, payload, retain=True):
        topic = self.get_topic(topic, payload)
        verbose('publish mqtt %s: %s' % (topic, payload))
        self.client.publish(topic, payload, retain)

    def send_homeassistant_auto_config(self):
        verbose('publishing homeassistant auto discovery')
        self.publish(self.auto_discovery.thermal_zone0, payload=self.create_hass_auto_conf('thermal_zone0', "\u00b0C", 'temperature'), retain=True)
        self.publish(self.auto_discovery.duty_cycle, payload=self.create_hass_auto_conf('duty_cycle', '%', 'duty_cycle'), retain=True)
        self.publish(self.auto_discovery.rpm, payload=self.create_hass_auto_conf('rpm', "rpm", 'rpm'), retain=True)

    def on_disconnect(self, client, userdata, rc):
        verbose("disconnected from mqtt server")
        self.connected = False

    def on_message(self, client, userdata, msg):
        print(msg.topic+" "+str(msg.payload))

    def client_begin(self):
        verbose('connecting to mqtt server %s' % (mqtt.server()))
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)
        self.client.will_set(self.topic.status, payload='0', qos=2, retain=True)
        self.client.connect_async(self.host, port=self.port, keepalive=self.keepalive)
        self.client.loop_start();

    def client_end(self):
        verbose('disconnecting from mqtt server')
        if self.connected:
            # self.publish(self.topic.status, payload="0", retain=True)
            self.client.disconnect();
        self.client.loop_stop(force=False)
        time.sleep(1.0)
        self.client.loop_stop(force=True)
        self.client = False

    def client_publish(self, temperature, speed):
        if self.connected and time.monotonic()>=self.next_update:
            self.next_update = time.monotonic() + self.update_rate
            self.publish(self.topic.json, payload=fsc.get_json(indent=0, ts=True), retain=True);
            self.publish(self.topic.status, payload="1", retain=True)

    def available(self):
        return True

try:
    if args.mqtthost==None:
        raise RuntimeError()
    import paho.mqtt.client
    mqtt = MQTT(args.mqttuser, args.mqttpass, args.mqtthost, args.mqttport, args.mqttdevicename, args.mqtttopic, paho.mqtt.client.Client(), update_rate=args.mqttupdateinterval, hass_autoconfig_prefix=args.mqtthass)
except:
    mqtt = NoMQTT()

def str_valid(s):
    if not isinstance(s, str):
        return False
    if not s.strip():
        return False
    return True

def update_log(args):
    # mqtt
    mqtt.client_publish(fsc.get_temp(), fsc.get_speed())

    if not str_valid(args.log):
        return
    if re.match('/^(NUL{1,2}|nul{1,2}|nul|\/dev\/nul{1,2})$/', args.log):
        args.log = None
        return
    if args.log=='-':
        print(fsc.get_json())
    else:
        verbose('temperature %.2f speed %.2f%% rpm %d, time %u, log %s' % (fsc.get_temp(), fsc.get_speed(), fsc.get_rpm(), time.time(), args.log))
        with open(args.log, 'w') as f:
            f.write(fsc.get_json())

def measure_rpm(duration = 2.5):
    gn = args.rpm_pin
    fsc.pigpio.set_mode(gn, pigpio.INPUT)
    fsc.pigpio.set_pull_up_down(gn, pigpio.PUD_OFF)

    global counter
    counter = 0

    def cbf(gpio, level, tick):
        global counter
        counter = counter + 1

    cb1 = pi.callback(gn, pigpio.FALLING_EDGE, cbf)
    time.sleep(duration)
    cb1.cancel()

    if counter>10:
        f = counter / duration / 2.0
        fsc.rpm = f * 60
    else:
        f = 0
        fsc.rpm = 0

    verbose("rpm measurement: count=%u frequency=%.2fHz speed=%.0f/rpm" % (counter, f, fsc.rpm))

# pin 12, 13, 18 and 19 supported
# level 0.0-100.0
def set_pwm(pin, level, measure = True) :
    fsc.pigpio.hardware_PWM(pin, args.frequency, int(level * 10000))
    fsc.set_speed(level)
    if measure:
        time.sleep(2) # give it some time to change
        measure_rpm()

    # mqtt
    mqtt.client_publish(fsc.get_temp(), fsc.get_speed())

def signal_term_handler(sig, frame):
    if os.exists(args.pidfile):
        verbose('removing: %s')
        os.unlink(args.pidfile)
    sys.exit(15)

def signal_handler(sig, frame):
    verbose('SIGINT')
    mqtt.signal_counter += 1
    if mqtt.signal_counter>1:
        verbose('sending SIGTERM')
        os.kill(os.getpid(), signal.SIGTERM)

    speed = args.onexit_speed
    args.speed = speed
    set_pwm(pi, args.pin, args.speed)
    update_log(args)

    if mqtt.signal_counter>1:
        print('sending SIGKILL')
        time.sleep(1.0)
        os.kill(os.getpid(), signal.SIGKILL)

    mqtt.client_end()
    if os.exists(args.pidfile):
        verbose('removing: %s')
        os.unlink(args.pidfile)
    sys.exit(2)


if args.set:
    level = max(0 ,min(100, args.set))
    print("set level to %f" % level)
    args.speed = level
    fsc.pigpio.hardware_PWM(args.pin, args.frequency, int(level * 10000))
    fsc.set_speed(level)

    # mqtt
    sys.exit(0)


# print table
if args.verbose or args.print_speed:
    i = 30
    j = -1
    json_output = {}
    while i<=90:
        n = fsc.temp_to_speed(i)
        # i += incr
        key = '%03.0f%%' % float(n)
        if key not in json_output:
            json_output[key] = '%.1f\u00b0C' % i
        i += 1


    if args.print_speed:
        indent = 2
        separators = (', ', ': ')
    else:
        indent = None
        separators = (',', ':')

    # if args.json:
    print(json.dumps(json_output, indent=indent, separators=separators, ensure_ascii=not sys.getdefaultencoding().startswith('utf') and '<stdin>' in sys.stdin.name))
    # else:
    #     for key, val in json_output.items():
    #         print('%s: %s' % (key, val))

# and exit and exit
if args.print_speed:
    sys.exit(0)

if args.measure:
    verbose('measing for %f seconds' % args.measure)
    measure_rpm(args.measure)
    print(int(fsc.rpm))
    sys.exit(0)

# check if mqtt is enabled
if mqtt.available():
    mqtt.client_begin()
    mqttupdateinterval = max(30, min(900, args.mqttupdateinterval))
    if args.interval>args.mqttupdateinterval:
        args.interval = args.mqttupdateinterval

# sigint handler
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_term_handler)

fsc.create_pid()

if args.verbose:
    verbose('min. fan speed %d%%' % args.min_fan)
    verbose('min. temperature %.2f°C' % args.min)
    verbose('max. temperature %.2f°C' % args.max)
    verbose('check interval %d seconds' % args.interval)
    verbose('mqtt server %s' % mqtt.server())
    if mqtt.available():
        verbose('mqtt update interval %d seconds' % args.mqttupdateinterval)
        verbose('mqtt device name %s' % args.mqttdevicename)
        verbose('homeassistant prefix %s' % args.mqtthass)

# loop_forever
while True:
    try:
        with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
            fsc.set_temp(float(f.readline()) / 1000.0)
        fsc.set_speed(fsc.temp_to_speed(fsc.get_temp()))
        verbose('temp %.2f speed %.2f%% rpm %.0f' % (fsc.get_temp(), fsc.get_speed(), fsc.get_rpm()))

        set_pwm(args.pin, fsc.get_speed())
        update_log(args)
    except Exception as e:
        print(e)

    if args.interval<1:
        verbose('interval < 1 second, exiting...')
        break

    time.sleep(args.interval)
