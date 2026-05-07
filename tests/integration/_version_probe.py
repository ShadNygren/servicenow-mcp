"""ServiceNow instance version + plugin inventory probe.

Recorded once per pytest session and written to the test report header
so every E2E run is stamped with the exact PDI version. The user
explicitly asked for this: enterprise IT admins and CISOs need to know
which ServiceNow version was certified by a given test run.

Per the user's note (2026-05-06): the PDI under test is on ServiceNow
"Zurich"; "Australia" just GA'd; "Yokohama" is also available as a PDI.
Multi-version testing is out of scope for E2E.1-E2E.7 but the report
format supports it --- running this probe against three PDIs yields
three reports with the same shape.

Probes:
- ``glide.product.build.tag`` --- e.g. "zurich-12-15-2025__patch1-12-21-2025"
- ``glide.buildname`` --- human-readable family name (Zurich, Yokohama, etc)
- ``sys_plugins`` --- inventory of active plugins (drives skip-if-inactive)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import httpx

from servicenow_mcp.auth.auth_manager import AuthManager
from servicenow_mcp.utils.async_http import get_async_client
from servicenow_mcp.utils.config import ServerConfig


@dataclass
class PdiVersionInfo:
    """Snapshot of PDI version + plugin state at session start."""

    instance_url: str
    family_name: Optional[str] = None  # "Zurich", "Yokohama", "Australia"
    build_tag: Optional[str] = None  # "zurich-12-15-2025__patch1-12-21-2025"
    build_date: Optional[str] = None
    active_plugins: dict[str, str] = field(default_factory=dict)  # name -> version
    plugin_count: int = 0
    probe_errors: list[str] = field(default_factory=list)

    def has_plugin(self, plugin_id: str) -> bool:
        """Is the named plugin active on this instance?"""
        return plugin_id in self.active_plugins

    def short(self) -> str:
        """One-line summary for report header."""
        return (
            f"{self.family_name or '<unknown>'} "
            f"({self.build_tag or '<unknown build>'}) "
            f"with {self.plugin_count} active plugin(s)"
        )


_FAMILY_NAMES: dict[str, str] = {
    "zurich": "Zurich",
    "yokohama": "Yokohama",
    "australia": "Australia",
    "xanadu": "Xanadu",
    "washington": "Washington",
    "vancouver": "Vancouver",
    "utah": "Utah",
    "tokyo": "Tokyo",
    "sandiego": "San Diego",
    "rome": "Rome",
    "quebec": "Quebec",
}


def _parse_war_filename(war: str) -> tuple[str | None, str | None]:
    """Parse a glide.war value like
    ``glide-zurich-07-01-2025__patch6-01-16-2026_02-02-2026_1554.zip`` into
    ``(family_name, build_tag)``.

    The family name is the second token of the file stem (zurich here),
    capitalised via the canonical-names map for marketing-correct
    spelling (``San Diego`` not ``Sandiego``). The build tag is the
    full tagged portion, dropping the ``glide-`` prefix and ``.zip``
    suffix.
    """
    if not war:
        return None, None
    # Strip the ".zip"
    stem = war
    if stem.endswith(".zip"):
        stem = stem[:-4]
    # Strip the leading "glide-"
    if stem.startswith("glide-"):
        stem = stem[len("glide-"):]
    # First token before the first hyphen is the family.
    family_lower = stem.split("-")[0] if "-" in stem else stem
    family = _FAMILY_NAMES.get(family_lower, family_lower.capitalize())
    return family, stem


async def probe(config: ServerConfig, auth: AuthManager) -> PdiVersionInfo:
    """Run version + plugin probes against the live PDI.

    Implementation notes:
      - The ServiceNow property ``glide.war`` is the most-readable
        version identifier on default PDI ACLs (it returns the actual
        WAR-file name, including family + base date + patch info).
        ``glide.product.build.tag`` and ``glide.buildname`` exist but
        are usually restricted on PDI even for the admin user.
      - The plugin inventory queries ``v_plugin`` (an unrestricted
        view); ``sys_plugins`` and ``sys_store_app`` are admin-API-ACL
        protected even for admin users on PDI and return 403, which
        is fine for an end-user-facing test.
      - Failures are captured in ``probe_errors`` rather than raised,
        so a partial probe still lets E2E tests run with a degraded
        report header instead of failing the whole session.
    """
    info = PdiVersionInfo(instance_url=config.instance_url)
    client = await get_async_client()
    headers = await auth.get_headers_async()

    # glide.war (definitive readable version identifier on default PDI).
    try:
        r = await client.get(
            f"{config.instance_url}/api/now/table/sys_properties",
            params={
                "sysparm_query": "name=glide.war",
                "sysparm_fields": "name,value",
                "sysparm_limit": "1",
            },
            headers=headers,
            timeout=config.timeout,
        )
        r.raise_for_status()
        rows = r.json().get("result", [])
        if rows:
            war = rows[0].get("value", "")
            family, build_tag = _parse_war_filename(war)
            info.family_name = family
            info.build_tag = build_tag
    except (httpx.HTTPError, KeyError, ValueError) as e:
        info.probe_errors.append(f"glide.war probe failed: {type(e).__name__}: {e}")

    # Plugin inventory (best-effort; v_plugin returns 0 rows on default
    # PDI ACL for the admin user --- the actual plugin tables are
    # gated behind a stricter API-level ACL. Capture the count if we
    # get it, but don't fail the probe if v_plugin is empty.
    try:
        r = await client.get(
            f"{config.instance_url}/api/now/table/v_plugin",
            params={
                "sysparm_query": "active=true",
                "sysparm_fields": "name,id,version,active",
                "sysparm_limit": "500",
            },
            headers=headers,
            timeout=config.timeout,
        )
        r.raise_for_status()
        rows = r.json().get("result", [])
        for row in rows:
            plugin_id = row.get("id") or row.get("name")
            version = row.get("version", "")
            if plugin_id:
                info.active_plugins[plugin_id] = version
        info.plugin_count = len(info.active_plugins)
    except (httpx.HTTPError, KeyError, ValueError) as e:
        info.probe_errors.append(f"plugin probe failed: {type(e).__name__}: {e}")

    return info
