import signal
from contextlib import contextmanager


class TimeoutException(Exception):
    pass


def timeout_handler(signum, frame):
    raise TimeoutException("Operação excedeu o tempo limite")


@contextmanager
def timeout(seconds: int):

    signal.signal(
        signal.SIGALRM,
        timeout_handler,
    )

    signal.alarm(seconds)

    try:
        yield

    finally:
        signal.alarm(0)