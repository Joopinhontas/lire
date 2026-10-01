# Contributing to Lire

Thanks for helping. Lire gets better mostly through two things: release titles it misreads, and people running it on setups other than the author's.

## The most useful contribution: a misread release

Lire's value is its parser. If a release is rejected, matched to the wrong series, or given the wrong volumes, open a **Release title misread** issue with the exact title, what Lire did, and what it should have done. That is enough; a test case and a fix usually follow quickly.

If you want to fix it yourself:

1. Add the title as a case in `tests/test_parse.py` (expected volumes, or expected rejection code).
2. Run `pytest -q` and watch it fail.
3. Fix `app/parse.py` until the whole suite passes. Other fixtures must not regress.

## Development setup

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt pytest
pytest -q
```

Running the app needs Prowlarr, qBittorrent and Kavita; copy `lire.env.example` to `lire.env` and point it at yours, then `docker compose up -d --build`.

## Ground rules

- **No build step.** The frontend is plain ES modules in `app/static`. Keep it that way.
- **Both languages.** Every interface string goes in `app/static/i18n.js` under `fr` and `en`; server messages go in `app/i18n.py`.
- **Design.** Read [`docs/DESIGN.md`](docs/DESIGN.md) before touching the UI: the shelf is the answer, one tap for the common case, honest states.
- **Security.** No new external origins without updating the CSP; no secrets in code, tests or fixtures (fixtures carry no real info hashes or download URLs).
- **Dependencies.** Pinned in `requirements.txt`; CI runs `pip-audit`.
- **Commits.** [Conventional Commits](https://www.conventionalcommits.org/) (`fix(parse): ...`, `feat(ui): ...`), small and focused.

## License of contributions

Lire is under the [PolyForm Noncommercial License 1.0.0](LICENSE). By opening a pull request you agree that your contribution is licensed under the same terms, and that the maintainer may also offer it under a separate commercial license.
