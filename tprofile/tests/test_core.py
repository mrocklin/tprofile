from tprofile import Profiler
import time


def test_basic():
    with Profiler(cycle_interval=50) as prof:
        time.sleep(0.2)

    assert prof.history and 'sleep' in str(prof.history)
    assert 2 < len(prof.history) < 10
