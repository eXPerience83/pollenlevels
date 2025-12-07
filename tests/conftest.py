"""Pytest configuration for lightweight async test support."""

from __future__ import annotations

import asyncio

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Register the asyncio marker used for lightweight async tests."""

    config.addinivalue_line(
        "markers", "asyncio: run test in an event loop without external plugins"
    )


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> bool | None:
    """Run coroutine tests marked with @pytest.mark.asyncio via a local loop."""

    marker = pyfuncitem.get_closest_marker("asyncio")
    if marker is None or not asyncio.iscoroutinefunction(pyfuncitem.obj):
        return None

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(pyfuncitem.obj(**pyfuncitem.funcargs))
    finally:
        # Ensure all tasks and async generators are properly cleaned up
        try:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
        finally:
            # Shutdown async generators and close the loop
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()
            asyncio.set_event_loop(None)

    return True
