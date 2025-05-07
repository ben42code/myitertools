import asyncio
from typing import NamedTuple

from helpers.measureperf import AMeasurePerf, MeasurePerf

from myproject.fibonacci import fibo, fibo_async


async def main():

    class Timing(NamedTuple):
        sync_t: float
        async_t: float

    lastTiming = None
    for n in range(0, 15):

        timing = Timing(
            sync_t=MeasurePerf(fibo, n),
            async_t=await AMeasurePerf(fibo_async, n)
        )

        if lastTiming is None:
            lastTiming = timing

        print(f'''Fibo/AFibo({n}) took [{timing.sync_t:.8f}s]({(timing.sync_t*100/lastTiming.sync_t-100):+.2f}%)/[{timing.async_t:.8f}s]({(timing.async_t*100/lastTiming.async_t-100):+.2f}%) to execute''')    # noqa: E501

        lastTiming = timing

if __name__ == "__main__":
    asyncio.run(main())

exit()
