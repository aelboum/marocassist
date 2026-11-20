"""Product configuration (non-secret tunables).

Secrets and connection strings (`DATABASE_URL`, `REDIS_URL`, OIDC, SMTP,
...) are never read here: SaaS-OS resolves them through its own secrets
provider. This module reads only MarocAssist's own non-secret settings from
the process environment and validates them at first use. An invalid value
is an error, never a silent default.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

# Copilot pairing credential lifetime (docs/phase-1/EXTENSION_AUTH.md).
# The ceiling is hard-coded so configuration can only shorten it.
_COPILOT_KEY_TTL_DEFAULT = 8 * 60 * 60
_COPILOT_KEY_TTL_MAX = 12 * 60 * 60
_COPILOT_KEY_TTL_MIN = 5 * 60
_COPILOT_MAX_DEVICES_DEFAULT = 3
_COPILOT_MAX_DEVICES_MAX = 10
# SaaS-OS keeps a revoked device as a disabled service account (it has no
# delete), so repeated pair/revoke cycles grow the tenant's identity list.
# Every pairing ever made counts; the tenant purge removes them all.
_COPILOT_MAX_DEVICE_HISTORY_DEFAULT = 50
_COPILOT_MAX_DEVICE_HISTORY_MAX = 500


class ConfigurationError(ValueError):
    """A MarocAssist setting is present but invalid. The message names the
    variable, never its value."""


@dataclass(frozen=True)
class ProductSettings:
    copilot_key_ttl_seconds: int
    copilot_max_devices: int
    copilot_max_device_history: int


def _int_setting(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ConfigurationError(f"{name} must be between {minimum} and {maximum}")
    return value


@lru_cache(maxsize=1)
def get_settings() -> ProductSettings:
    return ProductSettings(
        copilot_key_ttl_seconds=_int_setting(
            "MAROCASSIST_COPILOT_KEY_TTL_SECONDS",
            _COPILOT_KEY_TTL_DEFAULT,
            _COPILOT_KEY_TTL_MIN,
            _COPILOT_KEY_TTL_MAX,
        ),
        copilot_max_devices=_int_setting(
            "MAROCASSIST_COPILOT_MAX_DEVICES",
            _COPILOT_MAX_DEVICES_DEFAULT,
            1,
            _COPILOT_MAX_DEVICES_MAX,
        ),
        copilot_max_device_history=_int_setting(
            "MAROCASSIST_COPILOT_MAX_DEVICE_HISTORY",
            _COPILOT_MAX_DEVICE_HISTORY_DEFAULT,
            1,
            _COPILOT_MAX_DEVICE_HISTORY_MAX,
        ),
    )
