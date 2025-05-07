from statistics import median
from typing import Awaitable, Callable

from myproject.tools.catchtime import CatchTime


def MeasurePerf(f: Callable, *args):
    durations = []
    for _ in range(15):
        with CatchTime() as t:
            f(*args)
        durations.append(t.duration)
    return median(durations)


async def AMeasurePerf(f: Awaitable, *args):
    durations = []
    for _ in range(15):
        with CatchTime() as t:
            await f(*args)
        durations.append(t.duration)
    return median(durations)
