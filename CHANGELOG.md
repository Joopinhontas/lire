# Changelog

All notable changes to Lire. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versions follow [SemVer](https://semver.org/).

## [2.2.1] - 2026-10-01

### Fixed
- "Continue reading" reopened volume 1 at page 0 for readers who started a series at a later volume: Lire now resumes the chapter read most recently (or the next one when it is finished) instead of Kavita's first unfinished chapter.

## [2.2.0] - 2026-10-01

### Added
- Accounts page creates the friend's Pocket ID account too (same email as Kavita, marked verified) and shows a one-time enrolment link to send; a "Sign-in link" button issues a new one for any account; deleting an account removes it at the provider.
- One sign-in for everything: after single sign-on Lire goes through Kavita's own sign-in (silent with a fresh provider session) and comes back, so the reader opens straight to the right volume.

## [2.1.0] - 2026-10-01

### Added
- Single sign-on with any OpenID Connect provider (authorization code with PKCE): a "Sign in with …" button above the password form, accounts created on first sign-in, password accounts kept.
- Reading progress linked automatically for single sign-on users: when Kavita shares Lire's domain, the page hands Lire the reader's own Kavita key once, and Lire checks that the key belongs to that reader.

## [2.0.0] - 2026-10-01

First public release.

### Library and reading
- Library home with a "Continue reading" row (Kavita's On Deck, per account) that opens the reader at your page; a series can be removed from it, which marks it unread for that reader only.
- Detail sheet with synopsis in your language, reading progress, and a volume and page picker that opens Kavita's reader exactly there.
- Accounts for friends, each with a twin Kavita account.
- French and English interface; synopses from MangaDex and AniList, with optional translation by a local LLM (Ollama).

### Finding and fetching
- Series search across AniList, Kitsu (typo recovery) and MangaDex; trending and all-time favourite manga, plus curated comics essentials and the latest comics releases on your indexers.
- Parser for manga and comics release names: volume ranges, packs, lists, counts, editions, formats and languages, with explicit reasons for every release left out.
- Weighted set cover planner choosing the fewest, healthiest releases for every missing volume, shown as a shelf of owned, on the way, planned, missing and unavailable volumes.
- Release language per series (French, English, Japanese, Spanish, Italian, German), remembered per reader, each language in its own Kavita library created on first use.
- Followed series: checked on a schedule, new volumes after the last one owned are fetched automatically; volumes only found inside mostly-owned packs are left for review.
- Watchdog replacing stalled downloads with the best available alternative.
- Releases made of loose images are packed into one CBZ per volume, and Lire's Kavita libraries skip loose images so a series never appears twice.

### Operations
- Installable PWA designed for tablets; hardened container (read-only, no capabilities, unprivileged); multi-arch image on GHCR, started and checked in CI before every release.

[2.2.1]: https://github.com/Joopinhontas/lire/releases/tag/v2.2.1
[2.2.0]: https://github.com/Joopinhontas/lire/releases/tag/v2.2.0
[2.1.0]: https://github.com/Joopinhontas/lire/releases/tag/v2.1.0
[2.0.0]: https://github.com/Joopinhontas/lire/releases/tag/v2.0.0
