# Maigret Intelligence Dashboard

The dashboard is a FastAPI application in `main.py` that calls Maigret's existing async `maigret.search` engine. It stores investigations, searches, site results, extracted identifiers, and analyst notes with SQLModel.

## Run locally

Install the project dependencies (the dashboard dependencies are `fastapi`, `sqlmodel`, and `uvicorn`):

```bash
pip install -e .
python main.py
```

Open <http://127.0.0.1:8000>. The alternative development command is:

```bash
uvicorn main:app --reload
```

The default SQLite database is `maigret-dashboard.db` in the repository root. Set `MAIGRET_DASHBOARD_DB` to use another SQLite path. `HOST`, `PORT`, and `LOG_LEVEL` are also supported.

## Search behavior

A search request creates a persisted `Search` row and is executed after the HTTP response in a background task. The worker loads `maigret/resources/data.json`, applies the requested site limit and tag filters, and calls Maigret's existing async library function. Progress is persisted after each completed site check. Maigret statuses, URLs, HTTP status, rank, tags, profile extraction, and discovered usernames are retained in relational rows and JSON columns for dynamic profile fields.

The dashboard polls `/api/searches/{id}/status` while a job runs. Results are available at `/api/searches/{id}/results`; reports are available as JSON or CSV at `/api/searches/{id}/report?format=json` and `?format=csv`.

## API overview

- `GET /api/dashboard` and `GET /api/statistics` provide database-backed metrics.
- `GET|POST /api/investigations` and `GET|DELETE /api/investigations/{id}` manage cases.
- `POST /api/search`, `GET /api/searches`, and `GET /api/searches/{id}` manage collection jobs.
- `GET /api/results/{id}` and `PATCH /api/results/{id}` expose evidence details.
- `POST /api/results/{id}/notes` and `POST /api/investigations/{id}/notes` save analyst notes.
- `GET /api/sites` reads the current Maigret site database.

Proxy, Tor, I2P, AI, and cookie settings remain server-side Maigret configuration concerns and are not exposed by the dashboard form.
