"""
Shared configuration and utilities for risk-intelligence scripts.

Adapted from fraud-intelligence for same-cluster / self-managed GAE compatibility.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urlparse, urlunparse


@dataclass(frozen=True)
class ArangoConfig:
    mode: str  # LOCAL | REMOTE
    url: str
    username: str
    password: str
    database: str


def load_dotenv(dotenv_path: Optional[Path] = None) -> None:
    """
    Minimal .env loader.
    Does NOT overwrite already-set environment variables.
    """
    if dotenv_path is None:
        dotenv_path = Path(__file__).resolve().parents[1] / ".env"
    if not dotenv_path.exists():
        return

    for line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if not k:
            continue
        os.environ.setdefault(k, v)


def sanitize_url(url: str) -> str:
    """Remove userinfo from URL so we can safely print it."""
    try:
        u = urlparse(url)
        netloc = u.hostname or ""
        if u.port:
            netloc = f"{netloc}:{u.port}"
        return urlunparse((u.scheme, netloc, u.path, u.params, u.query, u.fragment))
    except Exception:
        return re.sub(r"//[^/@]+@", "//***@", url)


def ensure_endpoint_has_port(url: str, default_port: int = 8529) -> str:
    """
    Append :8529 to ArangoDB endpoint if no port is present.
    Prevents 401 errors when the platform expects the port.
    """
    if not url:
        return url
    try:
        u = urlparse(url)
        if u.port is not None:
            return url
        netloc = f"{u.hostname or u.netloc}:{default_port}"
        return urlunparse((u.scheme, netloc, u.path or "", u.params, u.query, u.fragment))
    except Exception:
        return url


def get_mode() -> str:
    """Resolve execution mode: LOCAL (Docker) or REMOTE (cluster)."""
    return (os.getenv("MODE") or os.getenv("ARANGO_MODE") or "REMOTE").strip().upper()


def _first(*vals: Optional[str]) -> Optional[str]:
    for v in vals:
        if v is not None and v != "":
            return v
    return None


def get_arango_config(forced_mode: Optional[str] = None) -> ArangoConfig:
    """Resolve mode-aware configuration (default REMOTE)."""
    mode = (forced_mode or get_mode()).strip().upper()
    if mode not in {"LOCAL", "REMOTE"}:
        mode = "REMOTE"

    local_url = _first(os.getenv("LOCAL_ARANGO_URL"), os.getenv("LOCAL_ARANGO_ENDPOINT"))
    local_user = _first(os.getenv("LOCAL_ARANGO_USERNAME"), os.getenv("LOCAL_ARANGO_USER"))
    local_pass = _first(os.getenv("LOCAL_ARANGO_PASSWORD"), os.getenv("LOCAL_ARANGO_PASS"))
    local_db = _first(os.getenv("LOCAL_ARANGO_DATABASE"), os.getenv("LOCAL_ARANGO_DB"))

    url = _first(os.getenv("ARANGO_URL"), os.getenv("ARANGO_ENDPOINT"))
    user = _first(os.getenv("ARANGO_USERNAME"), os.getenv("ARANGO_USER"), "root")
    passwd = _first(os.getenv("ARANGO_PASSWORD"), os.getenv("ARANGO_PASS"), "")
    db = _first(os.getenv("ARANGO_DATABASE"), os.getenv("ARANGO_DB"), "risk-intelligence")

    if mode == "LOCAL":
        port = os.getenv("ARANGO_PORT")
        default_local = f"http://localhost:{port}" if port else "http://localhost:8529"
        return ArangoConfig(
            mode="LOCAL",
            url=_first(local_url, url, default_local) or default_local,
            username=_first(local_user, user, "root") or "root",
            password=_first(local_pass, os.getenv("ARANGO_DOCKER_PASSWORD"), passwd, "") or "",
            database=_first(local_db, db, "risk-intelligence") or "risk-intelligence",
        )

    return ArangoConfig(
        mode="REMOTE",
        url=_first(url, local_url) or "",
        username=user or "root",
        password=passwd or "",
        database=db or "risk-intelligence",
    )


def apply_config_to_env(cfg: ArangoConfig) -> None:
    """
    Normalize env vars. Ensures ARANGO_URL and ARANGO_ENDPOINT include :8529 when missing.
    """
    url = ensure_endpoint_has_port(cfg.url)
    os.environ["MODE"] = cfg.mode
    os.environ["ARANGO_URL"] = url
    os.environ["ARANGO_ENDPOINT"] = url
    os.environ["ARANGO_USERNAME"] = cfg.username
    os.environ["ARANGO_PASSWORD"] = cfg.password
    os.environ["ARANGO_DATABASE"] = cfg.database
    os.environ["ARANGO_DB"] = cfg.database
