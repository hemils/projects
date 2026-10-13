"""Shared helpers for experiments A and C: timed Entra auth and Trino queries."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import msal

AZURE_CLI_CLIENT_ID = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"
DENY_MARKERS = (
    "denied by identity-aware routing policy",
    "poc country header is missing or invalid",
)


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"Set {name}.")
    return value


class TokenProvider:
    """In-process MSAL token acquisition so auth overhead can be timed."""

    def __init__(self) -> None:
        tenant = _require("ENTRA_TENANT_ID")
        resource = _require("ENTRA_APP_CLIENT_ID")
        self.scopes = [f"api://{resource}/access"]
        self._app = msal.PublicClientApplication(
            os.getenv("ENTRA_CLIENT_ID", AZURE_CLI_CLIENT_ID),
            authority=f"https://login.microsoftonline.com/{tenant}",
        )

    def login(self, login_hint: str | None = None) -> str:
        """Interactive sign-in (untimed: includes user think time); returns the UPN.

        With login_hint the account picker is forced and the signed-in account must match.
        """
        kwargs = {"login_hint": login_hint, "prompt": "select_account"} if login_hint else {}
        result = self._app.acquire_token_interactive(self.scopes, **kwargs)
        if "access_token" not in result:
            raise SystemExit(result.get("error_description", "Interactive login failed"))
        claims = result.get("id_token_claims", {})
        upn = claims.get("preferred_username") or self._app.get_accounts()[0]["username"]
        if login_hint and upn.lower() != login_hint.lower():
            raise SystemExit(f"Signed in as {upn}, expected {login_hint}")
        return upn

    def acquire(
        self, *, force_refresh: bool = False, username: str | None = None
    ) -> tuple[str, float, str]:
        """Return (token, seconds, source); force_refresh bypasses the token cache."""
        accounts = self._app.get_accounts(username=username)
        if not accounts:
            raise RuntimeError(f"No signed-in account for {username or 'default'}")
        account = accounts[0]
        start = time.perf_counter()
        result = self._app.acquire_token_silent(
            self.scopes, account=account, force_refresh=force_refresh
        )
        elapsed = time.perf_counter() - start
        if not result or "access_token" not in result:
            detail = (result or {}).get("error_description") or "no cached refresh token for this account"
            raise RuntimeError(f"Silent token acquisition failed: {detail}")
        return result["access_token"], elapsed, result.get("token_source", "unknown")


@dataclass(frozen=True)
class Target:
    label: str
    host: str
    port: int
    scheme: str


def parse_target(spec: str) -> Target:
    """Parse 'label=host:port' (scheme from TRINO_HTTP_SCHEME, default http)."""
    label, _, address = spec.partition("=")
    host, _, port = address.partition(":")
    if not (label and host and port.isdigit()):
        raise SystemExit(f"Invalid target '{spec}', expected label=host:port")
    return Target(label, host, int(port), os.getenv("TRINO_HTTP_SCHEME", "http"))


def run_query(
    target: Target, *, user: str, token: str, country: str, sql: str
) -> tuple[str, float, str]:
    """Run one query; return (outcome, seconds, detail). Outcome: allow, deny or error."""
    from trino.dbapi import connect

    headers = {"Authorization": f"Bearer {token}"}
    if country:
        headers["X-Poc-User-Country"] = country
    start = time.perf_counter()
    try:
        connection = connect(
            host=target.host,
            port=target.port,
            user=user,
            http_scheme=target.scheme,
            http_headers=headers,
        )
        try:
            cursor = connection.cursor()
            cursor.execute(sql)
            cursor.fetchall()
        finally:
            connection.close()
    except Exception as exc:  # any client error is classified below
        message = str(exc)
        outcome = "deny" if any(m in message.lower() for m in DENY_MARKERS) else "error"
        return outcome, time.perf_counter() - start, message[:300]
    return "allow", time.perf_counter() - start, ""
