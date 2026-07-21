from datetime import datetime
import time


def log(stage: str, message: str):
    now = datetime.now().strftime("%H:%M:%S")

    print(
        f"[{now}] [{stage}] {message}",
        flush=True,
    )


class Timer:

    def __init__(self, stage):
        self.stage = stage

    def __enter__(self):
        self.start = time.perf_counter()
        log(self.stage, "Iniciando")

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = time.perf_counter() - self.start
        log(
            self.stage,
            f"Finalizado em {elapsed:.2f}s"
        )