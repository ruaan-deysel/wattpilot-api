# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.x     | ✅ Yes     |
| < 1.0   | ❌ No      |

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Report security issues **privately** via [GitHub Security Advisories](https://github.com/ruaan-deysel/wattpilot-api/security/advisories/new) or by emailing the maintainer directly (address available on the [GitHub profile](https://github.com/ruaan-deysel)).

Include as much detail as possible:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

You can expect an acknowledgement within **48 hours** and a patch within **14 days** for confirmed vulnerabilities.

## Security Measures

This library implements a reverse-engineered WebSocket API for Fronius Wattpilot EV chargers. The following security controls are in place:

### Authentication (OWASP A07)
- **PBKDF2-SHA512** with 100 000 iterations for standard devices
- **bcrypt** (cost factor 8) with SHA-256 pre-hashing for Wattpilot Flex devices — matches the firmware's bcrypt.js implementation
- Authentication tokens are generated with `secrets.token_hex()` (cryptographically secure RNG)

### Cryptographic Integrity (OWASP A02)
- `setValue` messages are wrapped in a `securedMsg` envelope signed with **HMAC-SHA256** over the JSON payload
- Passwords are never transmitted in plaintext — only the derived hash is used in authentication handshakes
- Cloud connections use `wss://` (TLS); local LAN connections use `ws://` which is standard for home-network device APIs

### Dependency Management (OWASP A06)
- **Dependabot** is enabled for both `pip` (Python) and `github-actions` dependencies with weekly updates
- **OSV.dev scanner** (`google/osv-scanner-action`) runs on every push, pull request, and weekly schedule
- **pip-audit** scans installed dependencies on every CI run
- **Bandit** SAST scans are run on every push and pull request, with results uploaded to GitHub Security

### CI/CD Pipeline (OWASP A05, A08)
- GitHub Actions workflows use **least-privilege permissions** (`contents: read` by default)
- PyPI publishing uses **OIDC Trusted Publishing** — no long-lived API tokens stored as secrets
- All third-party actions are pinned to major versions and kept up-to-date via Dependabot

### Input Handling (OWASP A03)
- MQTT topic values containing format-string characters are sanitised before use in template substitution
- Property names received from MQTT are validated against the YAML API definition before processing
- Unknown properties from newer firmware are gracefully ignored (no `KeyError` crashes)

## Vulnerability Disclosure History

None to date.
