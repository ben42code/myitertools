import time


class CatchTime:
    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, exception_type, exception_value, exception_traceback):
        self.end = time.perf_counter()
        self.duration = self.end - self.start
