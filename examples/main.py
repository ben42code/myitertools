from itertools import islice
from typing import NamedTuple

from ben42code.myitertools import islice_extended

input = list(range(10))


class TestCase(NamedTuple):
    start: int | None
    stop: int | None
    step: int | None


TestCases = [
    # fmt: off
    TestCase(start=0,   stop=5,     step=1),
    TestCase(start=5,   stop=0,     step=-1),
    TestCase(start=-10, stop=-5,    step=1),
    TestCase(start=-10, stop=5,     step=1),
    TestCase(start=0,   stop=-5,    step=1),
    TestCase(start=-5,  stop=-10,   step=-1),
    TestCase(start=-5,  stop=0,     step=-1),
    TestCase(start=5,   stop=-10,   step=-1),
    # fmt: on
]

print(f"Input: {input}")
print("=" * 40)

for testcase in TestCases:
    print(f"Input: {testcase}")
    print(f"myitertools.islice_extended Output: {list(islice_extended(input, *testcase))}")
    try:
        print(f"itertools.islice            Output: {list(islice(input, *testcase))}")
    except Exception as e:
        print(f"itertools.islice            Error: {e}")
    print("-" * 40)

exit()
