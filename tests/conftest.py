"""Shared test fixtures."""

from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable

import pytest


@pytest.fixture
def wait_for() -> Callable[..., Awaitable[bool]]:
    """Return a helper that pumps a Textual app until a condition holds."""

    async def _wait_for(pilot, condition, timeout: float = 5.0) -> bool:
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            if condition():
                return True
            await asyncio.sleep(0.02)
            await pilot.pause()
        return condition()

    return _wait_for
