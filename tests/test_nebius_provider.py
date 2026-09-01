"""Offline tests for the Nebius provider and config loader.

No network access and no real API key are required — the OpenAI
client is replaced with fakes that record what they were called with
and return canned responses.
"""

import logging

import pytest

from sae_demo.config import (
    DEFAULT_NEBIUS_BASE_URL,
    DEFAULT_NEBIUS_MODEL,
    MissingNebiusAPIKeyError,
    NebiusConfig,
    load_nebius_config,
)
from sae_demo.nebius_provider import (
    NON_REASONING_EXTRA_BODY,
    NebiusProvider,
    NebiusProviderError,
)


# --- fakes -------------------------------------------------------------

class _FakeMessage:
    def __init__(self, content, reasoning=None):
        self.content = content
        self.reasoning = reasoning


class _FakeChoice:
    def __init__(self, message, finish_reason="stop"):
        self.message = message
        self.finish_reason = finish_reason


class _FakeUsage:
    def __init__(self, completion_tokens):
        self.completion_tokens = completion_tokens


class _FakeResponse:
    def __init__(self, message, finish_reason="stop", completion_tokens=9):
        self.choices = [_FakeChoice(message, finish_reason=finish_reason)]
        self.usage = _FakeUsage(completion_tokens)


class _FakeCompletions:
    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc
        self.last_call_kwargs = None

    def create(self, **kwargs):
        self.last_call_kwargs = kwargs
        if self._exc is not None:
            raise self._exc
        return self._response


class _FakeChat:
    def __init__(self, completions):
        self.completions = completions


class _FakeClient:
    def __init__(self, response=None, exc=None):
        self.completions = _FakeCompletions(response=response, exc=exc)
        self.chat = _FakeChat(self.completions)


def _config(api_key="test-key-123"):
    return NebiusConfig(api_key=api_key)


# --- config tests --------------------------------------------------------

def test_load_nebius_config_defaults():
    env = {"NEBIUS_API_KEY": "test-key-123"}
    config = load_nebius_config(env=env)

    assert config.api_key == "test-key-123"
    assert config.base_url == DEFAULT_NEBIUS_BASE_URL
    assert config.model == DEFAULT_NEBIUS_MODEL


def test_load_nebius_config_missing_api_key():
    with pytest.raises(MissingNebiusAPIKeyError):
        load_nebius_config(env={})


def test_nebius_config_repr_never_exposes_key():
    env = {"NEBIUS_API_KEY": "super-secret-value"}
    config = load_nebius_config(env=env)

    assert "super-secret-value" not in repr(config)
    assert "super-secret-value" not in str(config)


# --- provider tests --------------------------------------------------------

def test_successful_non_reasoning_response():
    response = _FakeResponse(
        _FakeMessage("SAE-DEMO API TEST OK", reasoning=None),
        completion_tokens=9,
    )
    fake_client = _FakeClient(response=response)
    provider = NebiusProvider(_config(), client=fake_client)

    result = provider.complete([{"role": "user", "content": "hi"}], max_tokens=100)

    assert result.content == "SAE-DEMO API TEST OK"
    assert result.reasoning is None
    assert result.finish_reason == "stop"
    assert result.completion_tokens == 9
    assert result.reasoning_warning is False
    assert (
        fake_client.completions.last_call_kwargs["extra_body"]
        == NON_REASONING_EXTRA_BODY
    )


def test_response_with_reasoning_null():
    response = _FakeResponse(_FakeMessage("answer", reasoning=None))
    fake_client = _FakeClient(response=response)
    provider = NebiusProvider(_config(), client=fake_client)

    result = provider.complete([{"role": "user", "content": "hi"}])

    assert result.reasoning is None
    assert result.reasoning_warning is False


def test_response_with_unexpected_non_null_reasoning_warns(caplog):
    response = _FakeResponse(
        _FakeMessage("answer", reasoning="some internal reasoning text")
    )
    fake_client = _FakeClient(response=response)
    provider = NebiusProvider(_config(), client=fake_client)

    with caplog.at_level(logging.WARNING):
        result = provider.complete([{"role": "user", "content": "hi"}])

    assert result.reasoning == "some internal reasoning text"
    assert result.reasoning_warning is True
    assert any("reasoning" in record.message.lower() for record in caplog.records)


def test_provider_error_does_not_leak_secret():
    secret = "sk-super-secret-nebius-key-abc123"
    fake_client = _FakeClient(exc=RuntimeError(f"auth failed with key {secret}"))
    provider = NebiusProvider(_config(api_key=secret), client=fake_client)

    with pytest.raises(NebiusProviderError) as exc_info:
        provider.complete([{"role": "user", "content": "hi"}])

    assert secret not in str(exc_info.value)
    assert "RuntimeError" in str(exc_info.value)
