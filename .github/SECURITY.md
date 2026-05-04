# Security Policy

## Supported Versions

This is an actively maintained fork of `echelon-ai-labs/servicenow-mcp` (the upstream has been effectively unmaintained since October 2025). Only the current `main` is supported with security updates.

| Branch | Supported |
|---|---|
| `main` (this fork) | Yes |
| upstream `echelon-ai-labs/servicenow-mcp:main` | No (unmaintained) |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do NOT** open a public GitHub issue.
2. Use [GitHub's private security advisory](https://github.com/ShadNygren/servicenow-mcp/security/advisories/new) on this repository, or email the repository owner via the address listed on the GitHub profile.
3. Include steps to reproduce, affected versions, and impact assessment if possible.

We aim to respond within 5 business days and to publish a fix in the same reasonable window for high-severity issues.

## Security Measures

This project includes:

- **CodeQL** — automated static analysis on every push and PR.
- **pip-audit** — dependency vulnerability scanning in CI.
- **Dependabot** — weekly automated dependency updates (pip + GitHub Actions).
- **Log-redaction CI gate** — `tests/conftest.py` fails the build if any captured log line matches `access_token`, `refresh_token`, or `Authorization: Bearer/Basic` patterns. Catches OAuth-body-logging regressions.
- **Inbound auth** — bearer token + Host/Origin allowlist on the HTTP `/mcp` endpoint, loopback-bind by default (from upstream's `fix/sse-auth-hardening` branch, merged here as `c77861e`; the Streamable HTTP transport carries the same defenses unchanged in `transport_security.py`).
- **Default-package security gate** — arbitrary-script-execution tools (`execute_script_include`, `create_script_include`, etc.) are registered but NOT included in any default tool package. Mitigates Issue [#43](https://github.com/echelon-ai-labs/servicenow-mcp/issues/43) finding #1.

## Known Considerations

- **Never commit `.env` files or credentials** to the repository.
- **OAuth client_credentials grant is the recommended auth path.** The legacy `password` grant remains supported for environments that require it but is deprecated by the OAuth Best Current Practice (Issue #43 finding #2).
- **Plaintext passwords in `claude_desktop_config.json` are a real exfiltration risk.** Configure credentials via env vars loaded at runtime instead. Issue #43 finding #3.
- ServiceNow instance URLs and credentials should be passed via environment variables.
- HTTP transport binds to loopback (`127.0.0.1`) by default; non-loopback bind requires explicit `--allow-remote` AND `MCP_AUTH_TOKEN`.

## Upstream security audit

[mcpscan.ai](https://mcpscan.ai/) audited the upstream repo on 2025-09-09 and reported four findings. Status of each in this fork:

| # | Finding | Status |
|---|---|---|
| 1 | RCE via script_include tools | **Mitigated.** Removed from default packages; security gate documented in `config/tool_packages.yaml`. |
| 2 | OAuth password-grant insecurity | **Mitigated.** client_credentials is now the primary path; password-grant kept as fallback only. |
| 3 | Plaintext password in claude_desktop_config.json | **Documented.** README warns against; full fix (OS keyring) deferred to Phase 10. |
| 4 | Insecure default `0.0.0.0` Docker binding | **Resolved** by hardening branch merge — loopback default. |
