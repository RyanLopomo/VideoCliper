import time
import concurrent.futures
from typing import Callable, Any

from app.utils.pipeline_logger import log


class RetryException(Exception):
    pass


class TimeoutException(Exception):
    pass


def _run_with_timeout(
    func: Callable[..., Any],
    timeout: int,
    *args,
    **kwargs,
):

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:

        future = executor.submit(
            func,
            *args,
            **kwargs,
        )

        try:

            return future.result(
                timeout=timeout
            )

        except concurrent.futures.TimeoutError as e:

            future.cancel()

            raise TimeoutException(
                f"Operação excedeu {timeout}s"
            ) from e


def retry(
    func: Callable[..., Any],
    *args,
    retries: int = 3,
    delay: float = 2,
    backoff: float = 2,
    timeout: int | None = None,
    stage: str = "",
    **kwargs,
):

    current_delay = delay
    last_exception = None

    for attempt in range(1, retries + 1):

        try:

            log(
                "RETRY",
                f"{stage} tentativa {attempt}/{retries}"
            )

            if timeout is not None:

                result = _run_with_timeout(
                    func,
                    timeout,
                    *args,
                    **kwargs,
                )

            else:

                result = func(
                    *args,
                    **kwargs,
                )

            if attempt > 1:

                log(
                    "RETRY",
                    f"{stage} recuperado na tentativa {attempt}"
                )

            return result

        except Exception as e:

            last_exception = e

            log(
                "RETRY",
                f"{stage} falhou: {e}"
            )

            if attempt == retries:
                break

            log(
                "RETRY",
                f"Aguardando {current_delay}s antes da próxima tentativa"
            )

            time.sleep(current_delay)

            current_delay *= backoff

    raise RetryException(
        f"{stage} falhou após {retries} tentativas: {last_exception}"
    ) from last_exception