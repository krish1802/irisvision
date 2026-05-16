#!/usr/bin/env python3
"""
Single-site config for irisvision.ai.

WordPress and other authenticated services have been removed. Only public-web
SEO data and (optionally) Google Analytics 4 read-only access remain.

GA4 credentials can be set here OR via environment variables:
    GA_PROPERTY_ID            e.g. "123456789"
    GA_CREDENTIALS_JSON       e.g. "/abs/path/to/service-account.json"
Env vars take precedence over the values set on SITE.

Other modules import:
    from sites_config import SITE
"""


from __future__ import annotations


from dataclasses import dataclass, field
import os
import re



@dataclass(frozen=True)
class Site:
    domain: str
    site_url: str
    brand_name: str
    site_description: str
    tracked_keywords: tuple[str, ...] = field(default_factory=tuple)
    competitors: tuple[str, ...] = field(default_factory=tuple)
    # Google Analytics 4 — overridden by env vars when set.
    ga_property_id: str | None = None
    ga_credentials_json: str | None = None


    @property
    def slug(self) -> str:
        """Filesystem-safe identifier used as the per-site report folder."""
        return re.sub(r"[^a-z0-9]+", "-", self.domain.lower()).strip("-")


    def output_dir(self, base: str = "seo_reports") -> str:
        path = os.path.join(base, self.slug)
        os.makedirs(path, exist_ok=True)
        return path



# ── The one and only site ───────────────────────────────────────────────


SITE = Site(
    domain="irisvision.ai",
    site_url="https://irisvision.ai",
    brand_name="IrisVision",
    site_description=(
        "IrisVision builds AI-powered low-vision wearable glasses that help "
        "people with macular degeneration, glaucoma, and other visual "
        "impairments see, read, and live independently."
    ),
    tracked_keywords=(
        "low vision glasses",
        "low vision aids",
        "wearable low vision device",
        "macular degeneration glasses",
        "glaucoma vision aid",
        "AI vision assistance",
        "electronic glasses for the blind",
        "assistive technology for low vision",
        "vision rehabilitation device",
        "smart glasses for visually impaired",
    ),
    competitors=(
        "esighteyewear.com",
        "nueyes.com",
        "orcam.com",
        "envisionamerica.com",
    ),
    # Either fill these in or set GA_PROPERTY_ID / GA_CREDENTIALS_JSON env vars.
    ga_property_id=None,            # e.g. "123456789"
    ga_credentials_json=None,       # e.g. "/abs/path/to/service-account.json"
)


# Backwards-compat aliases — some scripts iterate `SITES`.
SITES: list[Site] = [SITE]



def get_site(domain: str | None = None) -> Site:
    """Return the only registered site. `domain` is accepted for API parity."""
    if domain and domain.lower() != SITE.domain.lower():
        raise ValueError(
            f"Unknown site '{domain}'. This toolkit is configured for "
            f"'{SITE.domain}' only."
        )
    return SITE
