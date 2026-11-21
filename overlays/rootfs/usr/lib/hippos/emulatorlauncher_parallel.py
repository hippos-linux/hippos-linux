from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Any, TypeVar

from emulatorlauncher_shared import _log

T = TypeVar('T')


@contextmanager
def timed(name: str, manager: AbstractContextManager[T]) -> Iterator[T]:
    started = time.perf_counter()
    with manager as value:
        _log.info("launch: %s %.2fs", name, time.perf_counter() - started)
        yield value


def _run_together(calls: list[Callable[[], Any]]) -> tuple[list[Any], list[BaseException | None]]:
    values: list[Any] = [None] * len(calls)
    errors: list[BaseException | None] = [None] * len(calls)

    def run(index: int) -> None:
        try:
            values[index] = calls[index]()
        except BaseException as exc:
            errors[index] = exc

    threads = [threading.Thread(target=run, args=(index,)) for index in range(len(calls))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return values, errors


class Parallel:
    def __init__(self, *managers: AbstractContextManager[Any]) -> None:
        self._managers = managers
        self._entered: list[AbstractContextManager[Any]] = []

    def __enter__(self) -> list[Any]:
        values, errors = _run_together([manager.__enter__ for manager in self._managers])
        self._entered = [manager for manager, error in zip(self._managers, errors) if error is None]
        if failures := [error for error in errors if error is not None]:
            self.__exit__(None, None, None)
            raise failures[0]
        return values

    def __exit__(self, *exc_info: object) -> bool:
        _, errors = _run_together([
            (lambda manager=manager: manager.__exit__(None, None, None)) for manager in reversed(self._entered)
        ])
        self._entered = []
        for error in errors:
            if error is not None:
                raise error
        return False
