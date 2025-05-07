
import asyncio

# Disclaimer: purpose is not to be efficient.
# Using recursive implementation just for the fun of it.


def fibo(n: int) -> int:
    assert n >= 0
    if n == 0:
        return 0
    elif n == 1:
        return 1
    else:
        return fibo(n - 1) + fibo(n - 2)


async def fibo_async(n: int) -> int:
    assert n >= 0
    if n == 0:
        async def return_f0_async():
            return fibo(0)
        return await asyncio.create_task(return_f0_async())
    elif n == 1:
        async def return_f1_async():
            return fibo(1)
        return await asyncio.create_task(return_f1_async())
    else:
        async with asyncio.TaskGroup() as tg:
            task_f_1 = tg.create_task(fibo_async(n - 1))
            task_f_2 = tg.create_task(fibo_async(n - 2))
        return task_f_1.result() + task_f_2.result()
