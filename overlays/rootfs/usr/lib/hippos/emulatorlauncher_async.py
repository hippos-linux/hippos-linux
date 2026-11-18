from __future__ import annotations

import asyncio
import time
from contextlib import AbstractAsyncContextManager, AbstractContextManager, asynccontextmanager
from typing import Any, AsyncIterator, TypeVar

from emulatorlauncher_shared import _log

T = TypeVar('T')


@asynccontextmanager
async def in_thread(manager: AbstractContextManager[T]) -> AsyncIterator[T]:
    value = await asyncio.to_thread(manager.__enter__)
    try:
        yield value
    finally:
        await asyncio.to_thread(manager.__exit__, None, None, None)


@asynccontextmanager
async def timed(name: str, manager: AbstractAsyncContextManager[T]) -> AsyncIterator[T]:
    started = time.perf_counter()
    async with manager as value:
        _log.info("launch: %s %.2fs", name, time.perf_counter() - started)
        yield value


class Parallel:
    def __init__(self, *managers: AbstractAsyncContextManager[Any]) -> None:
        self._managers = managers
        self._entered: list[AbstractAsyncContextManager[Any]] = []

    async def __aenter__(self) -> list[Any]:
        results = await asyncio.gather(*(m.__aenter__() for m in self._managers), return_exceptions=True)
        self._entered = [m for m, r in zip(self._managers, results) if not isinstance(r, BaseException)]
        failures = [r for r in results if isinstance(r, BaseException)]
        if failures:
            await self.__aexit__(None, None, None)
            raise failures[0]
        return list(results)

    async def __aexit__(self, *exc_info: object) -> bool:
        results = await asyncio.gather(
            *(m.__aexit__(None, None, None) for m in reversed(self._entered)), return_exceptions=True,
        )
        self._entered = []
        for result in results:
            if isinstance(result, BaseException):
                raise result
        return False
