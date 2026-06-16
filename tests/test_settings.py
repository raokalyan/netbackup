import os

import pytest

from netbackup.settings import device_env_name, resolve_device_secret


def test_device_env_name_converts_name_and_secret():
    assert device_env_name("panorama-01", "api_key") == "PANORAMA_01_API_KEY"
    assert device_env_name("firewall-01", "username") == "FIREWALL_01_USERNAME"
    assert device_env_name("core.switch.a", "password") == "CORE_SWITCH_A_PASSWORD"


def test_resolve_device_secret_prefers_explicit_env(monkeypatch):
    monkeypatch.setenv("EXPLICIT_KEY", "explicit-value")
    monkeypatch.setenv("FIREWALL_01_API_KEY", "conventional-value")

    assert resolve_device_secret("firewall-01", "api_key", "EXPLICIT_KEY") == "explicit-value"


def test_resolve_device_secret_falls_back_to_conventional_name(monkeypatch):
    monkeypatch.setenv("SWITCH_01_USERNAME", "admin")
    monkeypatch.delenv("EXPLICIT_USER", raising=False)

    assert resolve_device_secret("switch-01", "username", "EXPLICIT_USER") == "admin"


def test_resolve_device_secret_uses_global_default_when_nothing_else_is_set(monkeypatch):
    monkeypatch.setenv("NETBACKUP_DEFAULT_PASSWORD", "fallback")
    monkeypatch.delenv("SWITCH_01_PASSWORD", raising=False)

    assert resolve_device_secret("switch-01", "password") == "fallback"


def test_resolve_device_secret_returns_none_when_unset():
    assert resolve_device_secret("unknown-device", "api_key") is None
