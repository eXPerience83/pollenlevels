"""Regression tests for defensive options-flow error handling."""

from __future__ import annotations

import logging

import pytest

from tests import test_options_flow as options_flow_tests

options_flow_env = options_flow_tests.options_flow_env


async def test_options_flow_unexpected_error_is_redacted_and_recovers(
    monkeypatch: pytest.MonkeyPatch,
    options_flow_env: options_flow_tests.OptionsFlowEnv,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unexpected validation errors should redact secrets and allow retry."""

    api_key = "synthetic-options-api-key"
    flow = options_flow_tests._flow(
        options_flow_env,
        entry_data={options_flow_env.CONF_API_KEY: api_key},
    )
    validation_calls = 0

    def _validate_language(value: str) -> str:
        nonlocal validation_calls
        validation_calls += 1
        if validation_calls == 1:
            raise RuntimeError(f"validation failed for key={api_key}")
        return value

    monkeypatch.setattr(
        options_flow_env.config_flow,
        "is_valid_language_code",
        _validate_language,
    )

    with caplog.at_level(logging.ERROR, logger=options_flow_env.config_flow.__name__):
        result = await flow.async_step_init(
            {
                options_flow_env.CONF_LANGUAGE_CODE: "en",
                options_flow_env.CONF_UPDATE_INTERVAL: 6,
            }
        )

    assert result["errors"] == {"base": "unknown"}
    assert api_key not in caplog.text
    assert "RuntimeError" in caplog.text
    assert "***" in caplog.text
    assert "Traceback (most recent call last)" not in caplog.text

    result = await flow.async_step_init(
        {
            options_flow_env.CONF_LANGUAGE_CODE: "en",
            options_flow_env.CONF_UPDATE_INTERVAL: 6,
        }
    )

    assert result == {
        "title": "",
        "data": {
            options_flow_env.CONF_UPDATE_INTERVAL: 6,
            options_flow_env.CONF_LANGUAGE_CODE: "en",
        },
    }
    assert validation_calls == 2
