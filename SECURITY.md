# Security policy

Lire handles accounts, session cookies and credentials for Prowlarr, qBittorrent and Kavita, so security reports are welcome and taken seriously.

## Reporting a vulnerability

Please **do not open a public issue**. Use [GitHub private vulnerability reporting](https://github.com/Joopinhontas/lire/security/advisories/new) with the affected version, a description, and steps to reproduce. You will get an answer within a few days, and credit in the release notes if you want it.

## Supported versions

Only the latest release receives fixes.

## Hardening already in place

Scrypt password hashes, HMAC signed `__Host-` session cookies revoked on password change, login throttling per IP and per username, CSRF header on every write, strict CSP and cross-origin isolation headers, read-only container without capabilities, pinned dependencies audited in CI.
