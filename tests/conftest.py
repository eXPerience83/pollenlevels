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
    """Run @pytest.mark.asyncio tests locally when no other async plugin is active."""

    marker = pyfuncitem.get_closest_marker("asyncio")
    if marker is None or not asyncio.iscoroutinefunction(pyfuncitem.obj):
        return None

    # If another asyncio-aware plugin is active, let it handle the test.
    plugin_manager = pyfuncitem.config.pluginmanager
    if plugin_manager.hasplugin("asyncio") or plugin_manager.hasplugin(
        "pytest-asyncio"
    ):
        return None

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        running_loop = False
    else:
        running_loop = True

    if running_loop:
        raise RuntimeError(
            "Detected a running event loop without an asyncio-aware pytest plugin. "
            "Disable conflicting plugins or install/enable pytest-asyncio."
        )

    try:
        previous_loop = asyncio.get_event_loop()
    except RuntimeError:
        previous_loop = None

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
        except Exception:
            # Continue teardown even if cleanup raises
            pass
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass
            finally:
                loop.close()
                try:
                    asyncio.set_event_loop(previous_loop)
                except Exception:
                    asyncio.set_event_loop(None)

    return True
