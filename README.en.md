# Iran Press Archive

A minimal fetcher for archiving Iranian historical newspapers and documents from heterogeneous link structures (public Google Drive folders, directory index pages, direct file lists).

- Config: `urls.yml` — one entry per source (see commented examples inside).
- Fetcher: `fetch.py` — run `python fetch.py`, `python fetch.py --source <id>`, or `--dry-run`.
- `state.json` tracks downloaded files so re-runs only fetch new items; output goes to `archive/<id>/`.

Install: `pip install -r requirements.txt`

See `README.md` (Persian) for full documentation.
