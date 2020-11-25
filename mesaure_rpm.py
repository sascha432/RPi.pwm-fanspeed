#!/usr/bin/python3

import pigpio
import time
import sys

class TicksDiff(object):

    def __init__(self):
        self.diff = None
        self.ticks = None
        self.average_multiplier = 0.25
        self.avg_period = None
        self._last = []
        self.timeout = 0
        self.count = 0

    def is_timeout(self):
        return time.monotonic() >= self.timeout

    def clear(self):
        self.diff = None
        self.avg_period = None
        self.ticks = None
        self.count = 0

    def set_ticks(self, ticks):
        old_is_timeout =  self.is_timeout()
        self.timeout = time.monotonic() + 1.0
        if old_is_timeout:
            self.clear()
            self.ticks = ticks
            return

        # firrst tick after timeout
        old_ticks = self.ticks
        self.ticks = ticks
        if old_ticks==None:
            self.diff = None
            self.avg_period = None
            return

        # ticks >1
        old_diff = self.diff
        new_diff = ticks - old_ticks
        new_diff *= 2.0
        if new_diff==0:
            return
        self.diff = new_diff
        if old_diff==None or old_diff==0:
            self.avg_period = None
            return

        if self.avg_period==None:
            mul = 0
            self.avg_period = new_diff
            self.count = 1
        else:
            self.count += 1
            mul = self.average_multiplier * 1000000 / new_diff
            self.avg_period = ((self.avg_period * mul) + new_diff) / (mul + 1.0)

        # self._lastsf.append(self.diff)
        # # self._last.append((self.diff, self.ticks, self.avg_period, mul))
        # if len(self._last)>32:
        #     self._last = self._last[-32:]
        #     print(self._last)
        #     self._last = []



    def get_diff(self):
        return self.diff

    def get_period(self):
        if self.avg_period==None:
            return None
        return self.avg_period

    def get_hz(self):
        p = self.get_period()
        if p==None:
            return None
        return 1000000 / self.avg_period

    def get_rpm(self):
        p = self.get_hz()
        if p==None:
            return None
        return p * 60


if __name__ == "__main__":

    import mesaure_rpm
    import pigpio
    import time
    import sys

    gn = 16
    pi = pigpio.pi()
    pi.set_mode(gn, pigpio.INPUT)
    pi.set_pull_up_down(gn, pigpio.PUD_OFF)

    ticks_diff = TicksDiff()
    cnt = 0

    def cbf(gpio, level, tick):
        global cnt
        ticks_diff.set_ticks(tick)
        cnt = cnt + 1

    dur = 2.5

    cb1 = pi.callback(gn, pigpio.FALLING_EDGE, cbf)
    time.sleep(dur)
    cb1.cancel()

    print("count=%u frequency=%.2fHz speed=%.0f/rpm" % (ticks_diff.count, ticks_diff.get_hz(), ticks_diff.get_rpm()))
    f = cnt / dur / 2
    rpm = int(f * 60)
    print("total count %u in %.3fs = %.3fHz, rpm = %u" % (cnt, dur, f, rpm))

    # delay = 0.5
    # count = 2 / delay
    # while count>0:
    #     with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
    #         temp_value = int(f.readline().strip()) / 1000.0
    #         print('temp=%.2fC ' % temp_value, end='')
    #     if ticks_diff.get_period()==None:
    #         print("timeout")
    #     else:
    #         print("period=%.3f/ms frequency=%.2fHz speed=%.0f/rpm" % (ticks_diff.get_period(), ticks_diff.get_hz(), ticks_diff.get_rpm()))
    #     time.sleep(delay)
    #     count -= 1

    # cb1.cancel() # To cancel callback cb1.

