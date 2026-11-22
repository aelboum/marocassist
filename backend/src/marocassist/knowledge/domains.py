"""Owner-maintained domain allow-list for knowledge sources (security review
T-8 and T-11).

Every `knowledge_sources.official_url` must be on this list, and the list
also says which source types a domain may carry. The `official`,
`consulate` and `government` types are only accepted for the domains named
here, so a look-alike domain cannot be registered as official. Adding a
domain is a reviewed code change, never a content change.

Matching is exact or by subdomain (`rdv.consulat.ma` matches `consulat.ma`);
`consulat.ma.example.com` and `evilconsulat.ma` do not match.

The same list is used at answer time (Phase 3 WP H) to drop any URL that is
not allow-listed.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Final
from urllib.parse import urlsplit

# Source types (rights document section 2.1).
MOROCCAN_OFFICIAL: Final = frozenset({"official", "consulate"})
DUTCH_GOVERNMENT: Final = frozenset({"government"})

# Domains from docs/research/OFFICIAL_DATA_SOURCES.md and docs/product/CONSULATES.md.
ALLOWED_DOMAINS: Final = MappingProxyType(
    {
        "consulat.ma": MOROCCAN_OFFICIAL,
        "diplomatie.ma": MOROCCAN_OFFICIAL,
        "idarati.ma": MOROCCAN_OFFICIAL,
        "passeport.ma": MOROCCAN_OFFICIAL,
        "cnie.ma": MOROCCAN_OFFICIAL,
        "watiqa.ma": MOROCCAN_OFFICIAL,
        "data.gov.ma": MOROCCAN_OFFICIAL,
        "rijksoverheid.nl": DUTCH_GOVERNMENT,
        "ind.nl": DUTCH_GOVERNMENT,
    }
)


def _host(url: str) -> str | None:
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    if parts.scheme != "https" or parts.username or parts.password or port is not None:
        return None
    host = (parts.hostname or "").rstrip(".").lower()
    return host or None


def allowed_source_types(url: str) -> frozenset[str]:
    """The source types `url` may carry; empty when the URL is not an
    allow-listed `https` URL (no credentials, no explicit port)."""
    host = _host(url)
    if host is None:
        return frozenset()
    for domain, types in ALLOWED_DOMAINS.items():
        if host == domain or host.endswith("." + domain):
            return types
    return frozenset()


def is_allowed_url(url: str) -> bool:
    return bool(allowed_source_types(url))
