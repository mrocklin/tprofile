import bisect
from collections import deque
import sys
import threading
import time

from toolz import pluck
from tornado.ioloop import IOLoop, PeriodicCallback
from . import profile


class Profiler(object):
    def __init__(self, io_loop=None, trigger_interval=10, cycle_interval=1000,
                 serve=True, **kwargs):
        self.recent = profile.create()
        self.history = deque(maxlen=3600)
        self.trigger_interval = trigger_interval
        self.cycle_interval = cycle_interval

        if io_loop is None:
            io_loop = IOLoop()
            from threading import Thread
            self.thread = Thread(target=io_loop.start, name='Profiler')
            self.thread.daemon = True
            self.thread.start()
        else:
            self.thread = None

        self.io_loop = io_loop
        self.pcs = {}

        def initialize():
            self.pcs['trigger'] = PeriodicCallback(self.trigger, trigger_interval)
            self.pcs['cycle'] = PeriodicCallback(self.cycle, cycle_interval)

            for pc in self.pcs.values():
                pc.start()

        io_loop.add_callback(initialize)

        if serve:
            from .bokeh import serve
            serve(self, **kwargs)

    def trigger(self):
        """
        Get a frame from all actively computing threads

        Merge these frames into existing profile counts
        """
        my_thread = threading.get_ident()
        frames = sys._current_frames()
        frames = {k: v for k, v in frames.items() if k != my_thread}
        for ident, frame in frames.items():
            if frame is not None:
                profile.process(frame, None, self.recent)

    def cycle(self):
        now = time.time()
        prof, self.recent = self.recent, profile.create()
        self.history.append((now, prof))

    def stop(self):
        def _stop():
            self.io_loop.stop()
        self.io_loop.add_callback(_stop)

        if self.thread:
            self.thread.join()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.stop()

    def get_profile(self, start=None, stop=None):
        now = time.time()
        history = self.history
        if start is None:
            istart = 0
        else:
            istart = bisect.bisect_left(history, (start,))

        if stop is None:
            istop = None
        else:
            istop = bisect.bisect_right(history, (stop,)) + 1
            if istop >= len(history):
                istop = None  # include end

        if istart == 0 and istop is None:
            history = list(history)
        else:
            iistop = len(history) if istop is None else istop
            history = [history[i] for i in range(istart, iistop)]

        prof = profile.merge(*pluck(1, history))

        if not history:
            return profile.create()

        if istop is None and (start is None or start < now):
            prof = profile.merge(prof, self.recent)

        return prof

    def get_profile_metadata(self, start=0, stop=None):
        if stop is None:
            add_recent = True
        now = time.time()
        stop = stop or now
        start = start or 0
        result = {'counts': [(t, d['count']) for t, d in self.history
                             if start < t < stop]}
        if add_recent:
            result['counts'].append((now, self.recent['count']))
        return result
