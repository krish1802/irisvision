#!/usr/bin/env python3
"""
Google Analytics 4 (Data API) client for irisvision.ai SEO dashboard.

Live-queries GA4 using a service account. Credentials can be supplied in
THREE ways, checked in this order:

  1. Individual GA4_* env vars (recommended for .env + GitHub workflows)
       GA4_TYPE, GA4_PROJECT_ID, GA4_PRIVATE_KEY_ID, GA4_PRIVATE_KEY,
       GA4_CLIENT_EMAIL, GA4_CLIENT_ID, GA4_AUTH_URI, GA4_TOKEN_URI,
       GA4_AUTH_PROVIDER_X509_CERT_URL, GA4_CLIENT_X509_CERT_URL,
       GA4_UNIVERSE_DOMAIN
     Plus the property ID:
       GA_PROPERTY_ID

  2. Full JSON blob in one env var
       GA_CREDENTIALS_JSON_CONTENT  (the entire service-account JSON)
       GA_PROPERTY_ID

  3. File path on disk
       GA_CREDENTIALS_JSON          (path to service-account.json)
       GA_PROPERTY_ID

If python-dotenv is installed and a .env file is present at CWD, it's
loaded automatically.
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from functools import lru_cache
from typing import Optional

import pandas as pd

# Auto-load .env if available (no hard dependency).
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import (
        DateRange,
        Dimension,
        Metric,
        RunReportRequest,
        OrderBy,
    )
    from google.oauth2 import service_account
    _GA_SDK_OK = True
    _GA_IMPORT_ERROR: Optional[str] = None
except Exception as exc:  # pragma: no cover
    _GA_SDK_OK = False
    _GA_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"


# ── CONFIG ──────────────────────────────────────────────────────────────


# Mapping: GA4_* env var → key inside the service-account JSON.
_GA4_ENV_KEYS = {
    "GA4_TYPE": "type",
    "GA4_PROJECT_ID": "project_id",
    "GA4_PRIVATE_KEY_ID": "private_key_id",
    "GA4_PRIVATE_KEY": "private_key",
    "GA4_CLIENT_EMAIL": "client_email",
    "GA4_CLIENT_ID": "client_id",
    "GA4_AUTH_URI": "auth_uri",
    "GA4_TOKEN_URI": "token_uri",
    "GA4_AUTH_PROVIDER_X509_CERT_URL": "auth_provider_x509_cert_url",
    "GA4_CLIENT_X509_CERT_URL": "client_x509_cert_url",
    "GA4_UNIVERSE_DOMAIN": "universe_domain",
}

# These must be present to assemble a valid credential.
_REQUIRED_GA4_KEYS = (
    "type", "project_id", "private_key",
    "client_email", "token_uri",
)


def _property_id() -> Optional[str]:
    pid = os.environ.get("GA_PROPERTY_ID", "535643252").strip()
    if pid:
        return pid
    try:
        from sites_config import SITE
        return getattr(SITE, "ga_property_id", None) or None
    except Exception:
        return None


def _credentials_path() -> Optional[str]:
    p = os.environ.get("GA_CREDENTIALS_JSON", "").strip()
    if p:
        return p
    try:
        from sites_config import SITE
        return getattr(SITE, "ga_credentials_json", None) or None
    except Exception:
        return None


def _info_from_ga4_env() -> Optional[dict]:
    """Build a service-account info dict from GA4_* env vars."""
    # Reverse map: json key -> env-var name, so we can look up the right env var
    # for each required JSON key.
    _JSON_TO_ENV = {v: k for k, v in _GA4_ENV_KEYS.items()}
    if not all(
        os.environ.get(_JSON_TO_ENV[k], "").strip() for k in _REQUIRED_GA4_KEYS
    ):
        return None

    info: dict = {}
    for env_key, json_key in _GA4_ENV_KEYS.items():
        val = os.environ.get(env_key, "")
        if val == "":
            continue
        if json_key == "private_key":
            # Normalize every shape the key can arrive in.
            val = val.strip().strip('"').strip("'")
            val = val.replace("\\n", "\n")
            val = val.replace("\r\n", "\n").replace("\r", "\n")
            if not val.endswith("\n"):
                val += "\n"
        info[json_key] = val
    return info


def _info_from_blob_env() -> Optional[dict]:
    raw = os.environ.get("GA_CREDENTIALS_JSON_CONTENT", "").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def ga_is_configured() -> tuple[bool, str]:
    """Return (ok, reason). reason is empty when ok=True."""
    if not _GA_SDK_OK:
        return False, (
            "google-analytics-data SDK not installed. "
            f"Run: pip install google-analytics-data  ({_GA_IMPORT_ERROR})"
        )
    if not _property_id():
        return False, "GA_PROPERTY_ID is not set."

    # Any one source is enough.
    if _info_from_ga4_env() is not None:
        return True, ""
    if _info_from_blob_env() is not None:
        return True, ""
    cred_path = _credentials_path()
    if cred_path and os.path.exists(cred_path):
        return True, ""

    _JSON_TO_ENV = {v: k for k, v in _GA4_ENV_KEYS.items()}
    missing = [
        _JSON_TO_ENV[k]
        for k in _REQUIRED_GA4_KEYS
        if not os.environ.get(_JSON_TO_ENV[k], "").strip()
    ]
    return False, (
        "No GA4 credentials found. Set GA4_* env vars in .env "
        f"(missing: {', '.join(missing) or 'all'}), or set "
        "GA_CREDENTIALS_JSON_CONTENT, or GA_CREDENTIALS_JSON=path/to/file."
    )


# ── CLIENT ──────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _client() -> "BetaAnalyticsDataClient":
    scopes = ["https://www.googleapis.com/auth/analytics.readonly"]

    info = _info_from_ga4_env() or _info_from_blob_env()
    if info is not None:
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=scopes,
        )
        return BetaAnalyticsDataClient(credentials=creds)

    cred_path = _credentials_path()
    if not cred_path or not os.path.exists(cred_path):
        raise RuntimeError(
            "GA4 credentials not configured. See ga_is_configured() for details."
        )
    creds = service_account.Credentials.from_service_account_file(
        cred_path, scopes=scopes,
    )
    return BetaAnalyticsDataClient(credentials=creds)


def _property() -> str:
    return f"properties/{_property_id()}"


def _run_report(
    *,
    dimensions: list[str],
    metrics: list[str],
    start: str,
    end: str,
    order_by_metric: Optional[str] = None,
    desc: bool = True,
    limit: Optional[int] = None,
) -> pd.DataFrame:
    req_kwargs = dict(
        property=_property(),
        dimensions=[Dimension(name=d) for d in dimensions],
        metrics=[Metric(name=m) for m in metrics],
        date_ranges=[DateRange(start_date=start, end_date=end)],
    )
    if order_by_metric:
        req_kwargs["order_bys"] = [
            OrderBy(metric=OrderBy.MetricOrderBy(metric_name=order_by_metric), desc=desc)
        ]
    if limit:
        req_kwargs["limit"] = limit

    request = RunReportRequest(**req_kwargs)
    response = _client().run_report(request)

    rows = []
    for row in response.rows:
        rec = {}
        for i, d in enumerate(dimensions):
            rec[d] = row.dimension_values[i].value
        for i, m in enumerate(metrics):
            v = row.metric_values[i].value
            try:
                rec[m] = float(v) if "." in v else int(v)
            except (TypeError, ValueError):
                rec[m] = v
        rows.append(rec)
    return pd.DataFrame(rows)


# ── PUBLIC QUERIES ──────────────────────────────────────────────────────


def ga_daily_traffic(start: str, end: str) -> pd.DataFrame:
    df = _run_report(
        dimensions=["date"],
        metrics=["sessions", "totalUsers", "screenPageViews", "newUsers"],
        start=start,
        end=end,
    )
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d").dt.strftime("%Y-%m-%d")
    return df.sort_values("date").reset_index(drop=True)


def ga_totals(start: str, end: str) -> dict:
    df = _run_report(
        dimensions=[],
        metrics=["sessions", "totalUsers", "screenPageViews", "newUsers"],
        start=start,
        end=end,
    )
    if df.empty:
        return {"sessions": 0, "totalUsers": 0, "screenPageViews": 0, "newUsers": 0}
    row = df.iloc[0].to_dict()
    return {
        "sessions": int(row.get("sessions", 0) or 0),
        "totalUsers": int(row.get("totalUsers", 0) or 0),
        "screenPageViews": int(row.get("screenPageViews", 0) or 0),
        "newUsers": int(row.get("newUsers", 0) or 0),
    }


def ga_top_pages(start: str, end: str, limit: int = 25) -> pd.DataFrame:
    return _run_report(
        dimensions=["pagePath"],
        metrics=["screenPageViews", "sessions", "totalUsers"],
        start=start,
        end=end,
        order_by_metric="screenPageViews",
        desc=True,
        limit=limit,
    )


def default_range(days: int = 28) -> tuple[str, str]:
    end = date.today()
    start = end - timedelta(days=days - 1)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")