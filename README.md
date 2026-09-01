# Maigret

<div align="center">

<img src="static2/maigret%20logo.png" width="760" alt="Maigret intelligence logo">

**Username-based OSINT discovery across 3,000+ websites.**

Maigret builds a dossier from a username, checks public profiles, extracts available account data, and follows discovered identities. No API keys are required for the core search.

[![PyPI version](https://img.shields.io/pypi/v/maigret?style=flat-square)](https://pypi.org/project/maigret/)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-brightgreen?style=flat-square)](https://github.com/soxoj/maigret)
[![License](https://img.shields.io/github/license/soxoj/maigret?style=flat-square)](LICENSE)
[![Downloads](https://static.pepy.tech/badge/maigret)](https://pepy.tech/project/maigret)

English | [简体中文](README.zh-CN.md)

</div>

## What Maigret does

Maigret is a Python OSINT tool and library for finding public accounts that reuse a username. It combines a maintained site database with asynchronous checks, profile extraction, recursive identity discovery, and report generation.

The default scan checks the 500 highest-ranked sites. Use `-a` for all available sites or narrow a scan with tags and countries.

### Highlights

- Checks 3,000+ sites. See the [full site list](sites.md).
- Extracts profile information and links to other accounts using [socid-extractor](https://github.com/soxoj/socid_extractor).
- Performs recursive searches using discovered usernames and identifiers.
- Filters sites by categories and country tags.
- Detects and partially bypasses blocks, censorship, and CAPTCHA challenges.
- Auto-updates the site database from GitHub once every 24 hours, with an offline built-in fallback.
- Supports Tor, I2P, domain checks, proxies, and optional Cloudflare/FlareSolverr integration.
- Produces HTML, PDF, CSV, JSON, TXT, XMind, Markdown, graph, and Neo4j reports.
- Includes both a CLI and a Python library API.
- Offers optional AI analysis through an OpenAI-compatible API. See [AI analysis](#ai-analysis).

For the complete feature list, read the [feature documentation](https://maigret.readthedocs.io/en/latest/features.html).

## Start in one minute

Requirements: Python 3.10 or newer.

```bash
pip install maigret
maigret YOUR_USERNAME
```

The command prints the scan as it runs and writes reports when report flags are supplied. Run `maigret --help` to see every option.

No local installation? Try the [community Telegram bot](https://sites.google.com/view/maigret-bot-link) or one of the [cloud options](#cloud-shells-and-notebooks).

## Dashboard

This repository includes a FastAPI + SQLModel investigation dashboard in `main.py`. It uses Maigret's existing asynchronous search engine, stores searches and findings in SQLite, tracks progress, and serves the custom interface from `static2/`.

### Run the dashboard locally

From the repository root:

```bash
pip install -e .
python main.py
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000).

For development with automatic reload:

```bash
uvicorn main:app --reload
```

The dashboard workflow is:

1. Enter a username and choose any advanced collection options.
2. Start an investigation.
3. Watch site checks and progress update while Maigret runs in the background.
4. Review found accounts, profile data, source URLs, tags, and discovered identities.
5. Add analyst notes and download a JSON or CSV report.

Dashboard data is persisted in `maigret-dashboard.db` by default. Set `MAIGRET_DASHBOARD_DB` to use another SQLite file. The application also accepts `HOST`, `PORT`, and `LOG_LEVEL` environment variables.

The dashboard API includes:

| Endpoint | Purpose |
| --- | --- |
| `GET /api/dashboard` | Database-backed metrics and recent activity |
| `GET/POST /api/investigations` | List or create cases |
| `GET/DELETE /api/investigations/{id}` | Inspect or remove a case |
| `POST /api/search` | Start a real Maigret search |
| `GET /api/searches/{id}/status` | Read live job progress |
| `GET /api/searches/{id}/results` | Retrieve persisted findings |
| `GET /api/results/{id}` | Open evidence and extracted profile data |
| `POST /api/results/{id}/notes` | Save an analyst note |
| `GET /api/searches/{id}/report?format=json` | Download JSON results |
| `GET /api/searches/{id}/report?format=csv` | Download CSV results |
| `GET /api/graph` | Read persisted identity relationships |

The dashboard's full implementation notes are in [docs/dashboard.md](docs/dashboard.md).

### Dashboard configuration boundaries

Proxy, Tor, I2P, AI credentials, and cookie files remain server-side configuration. Secrets are not placed in the frontend. The primary dashboard form exposes only collection options supported by the application, including site limits, tags, recursive extraction, and profile extraction.

## Installation options

### From source

```bash
git clone https://github.com/soxoj/maigret
cd maigret
pip install .
maigret username
```

For dashboard development, use `pip install -e .` instead.

### Windows standalone executable

Download `maigret_standalone.exe` from [Releases](https://github.com/soxoj/maigret). Double-click it for an interactive default scan, or run it from Command Prompt or PowerShell:

```cmd
cd %USERPROFILE%\Downloads
maigret_standalone.exe USERNAME
maigret_standalone.exe USERNAME --html
maigret_standalone.exe --help
```

See the [Windows video guide](https://youtu.be/qIgwTZOmMmM).

### Cloud Shells and notebooks

- [Google Cloud Shell](https://console.cloud.google.com/cloudshell/open?git_repo=https://github.com/soxoj/maigret&tutorial=cloudshell-tutorial.md)
- [Replit](https://repl.it/github/soxoj/maigret)
- [Google Colab](https://colab.research.google.com/gist/soxoj/879b51bc3b2f8b695abb054090645000/maigret-collab.ipynb)
- [Binder](https://mybinder.org/v2/gist/soxoj/9d65c2f4d3bec5dd25949197ea73cf3a/HEAD)

### Docker

Two official image variants are published:

- `soxoj/maigret:latest` for CLI usage.
- `soxoj/maigret:web` for the built-in Flask web interface.

```bash
docker pull soxoj/maigret
docker run -v /mydir:/app/reports soxoj/maigret:latest username --html

docker run -p 5000:5000 soxoj/maigret:web
docker run -e PORT=8080 -p 8080:8080 soxoj/maigret:web
```

Build locally when needed:

```bash
docker build -t maigret .
docker build --target web -t maigret-web .
```

The published Docker web image exposes the existing Flask interface on port 5000. The repository dashboard described above runs with `python main.py` on port 8000.

### Optional PDF support

PDF generation is an optional extra:

```bash
pip install 'maigret[pdf]'
```

Linux and macOS may require system graphics libraries. Read the [PDF installation guide](https://maigret.readthedocs.io/en/latest/installation.html#optional-pdf-reports-maigret-pdf) for platform-specific steps.

## CLI usage

### Common searches and reports

```bash
# Reports
maigret user --html
maigret user --pdf
maigret user --xmind
maigret user --json ndjson
maigret user --csv
maigret user --txt
maigret user --graph
maigret user --neo4j

# Filter by category or country tag
maigret user --tags photo,dating
maigret user --tags us

# Highlight pages containing keywords
maigret user --keywords python rust

# Search multiple usernames across all available sites
maigret user1 user2 user3 -a

# Optional AI summary
maigret user --ai
```

The `--neo4j` option writes a re-importable `*_neo4j.cypher` script. Load it with `cypher-shell -u neo4j -p <password> < report_user_neo4j.cypher` or paste it into Neo4j Browser. See the [Neo4j export documentation](https://maigret.readthedocs.io/en/latest/command-line-options.html#neo4j-export).

Useful flags:

- `--parse URL` parses a profile page, extracts identifiers, and can begin a recursive search.
- `--permute` generates likely username variants from two or more inputs.
- `--self-check [--auto-disable]` audits site database presence/absence markers.
- `--ai` and `--ai-model` create an AI-assisted summary.

Read the [CLI options](https://maigret.readthedocs.io/en/latest/command-line-options.html) and [usage examples](https://maigret.readthedocs.io/en/latest/usage-examples.html) for the full reference.

### Built-in Flask web interface

Maigret also retains its original Flask web interface with a result graph and downloadable reports:

```console
maigret --web 5000
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000). The hosted version can be deployed through [Render](https://render.com/deploy?repo=https://github.com/soxoj/maigret&path=utils/render.yaml). It has no login, so anyone with the deployed URL can use it.

## Python library

Maigret can be embedded in Python projects. The CLI is a wrapper around an asynchronous library function, so custom pipelines can load the site database, filter sites, run searches, and process result objects directly.

```python
import asyncio
import logging
import maigret
from maigret.sites import MaigretDatabase

async def find_accounts(username):
    database = MaigretDatabase().load_from_path("maigret/resources/data.json")
    sites = database.ranked_sites_dict(top=500, disabled=False, id_type="username")
    return await maigret.search(
        username=username,
        site_dict=sites,
        logger=logging.getLogger("maigret.example"),
        no_progressbar=True,
    )

results = asyncio.run(find_accounts("username"))
```

See the complete [library usage guide](https://maigret.readthedocs.io/en/latest/library-usage.html) for filtering, async patterns, and result handling.

## Advanced networking

### Tor, I2P, and proxies

```bash
maigret user --proxy socks5://127.0.0.1:1080
maigret user --tor-proxy socks5://127.0.0.1:9050
maigret user --i2p-proxy http://127.0.0.1:4444
```

Start the Tor or I2P daemon before running Maigret. Maigret does not manage these gateways.

### AI analysis

AI analysis sends a generated Markdown report to an OpenAI-compatible chat completion endpoint and streams a short, neutral summary containing likely identity details, interests, confidence, and follow-up leads.

```bash
export OPENAI_API_KEY=sk-...
maigret user --ai
maigret user --ai --ai-model gpt-4o-mini
```

The key can also be set as `openai_api_key` in `settings.json`. The endpoint defaults to `https://api.openai.com/v1`; set `openai_api_base_url` for Azure OpenAI, OpenRouter, or a local compatible server. See the [settings documentation](https://maigret.readthedocs.io/en/latest/settings.html).

### Cloudflare bypass

> **Experimental:** the Cloudflare webgate is under active development. Its configuration schema, CLI behavior, and routed sites may change.

Run a local [FlareSolverr](https://github.com/FlareSolverr/FlareSolverr) instance and opt in:

```bash
docker run -d -p 8191:8191 --name flaresolverr ghcr.io/flaresolverr/flaresolverr:latest
maigret --cloudflare-bypass username
```

Read the [Cloudflare feature documentation](https://maigret.readthedocs.io/en/latest/features.html#cloudflare-bypass) for backend options.

## Examples and reports

- [Console recording](https://asciinema.org/a/Ao0y7N0TTxpS0pisoprQJdylZ)
- [PDF report](https://raw.githubusercontent.com/soxoj/maigret/main/static/report_alexaimephotographycars.pdf)
- [HTML report](https://htmlpreview.github.io/?https://raw.githubusercontent.com/soxoj/maigret/main/static/report_alexaimephotographycars.html)
- [Full recursive-search output](https://raw.githubusercontent.com/soxoj/maigret/main/static/recursive_search.md)

<details>
<summary>Report and web-interface screenshots</summary>

![HTML report screenshot](https://raw.githubusercontent.com/soxoj/maigret/main/static/report_alexaimephotography_html_screenshot.png)

![XMind report screenshot](https://raw.githubusercontent.com/soxoj/maigret/main/static/report_alexaimephotography_xmind_screenshot.png)

![Web interface: start](https://raw.githubusercontent.com/soxoj/maigret/main/static/web_interface_screenshot_start.png)

![Web interface: results](https://raw.githubusercontent.com/soxoj/maigret/main/static/web_interface_screenshot.png)

</details>

## Development and contribution

To contribute site definitions, edit `maigret/resources/data.json` surgically and regenerate derived metadata:

```bash
./utils/update_site_data.py
```

Run the test suite with:

```bash
make test
```

See the [contribution guide](CONTRIBUTING.md), [development documentation](https://maigret.readthedocs.io/en/latest/development.html), and [release history](CHANGELOG.md). For installation issues, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Sponsors

<p align="center">
  <a href="https://www.ipcook.com/?ref=githubmaigret&utm_source=github&utm_medium=referral&utm_campaign=maigret"><img src="https://github.com/user-attachments/assets/8c02d81a-8135-408d-a5e0-7558a1f49a2d" width="400" alt="IPcook"></a>
  <br>
  <a href="https://www.rapidproxy.io/?ref=soxoj"><img src="https://github.com/user-attachments/assets/4ed589d1-37cb-4a40-9273-bff4d6f1a514" width="500" alt="RapidProxy"></a>
</p>

[IPcook](https://www.ipcook.com/?ref=githubmaigret&utm_source=github&utm_medium=referral&utm_campaign=maigret) provides residential proxies for online research and public data collection, with a free 100MB trial and code `WELCOME20` for 20% off.

[RapidProxy](https://www.rapidproxy.io/?ref=soxoj) provides rotating residential proxies for scraping and web data extraction. Plans start at $0.65/GB with code `RAPID10` for 10% off.

## Commercial use

Maigret is MIT-licensed and free for commercial use without restriction. Production deployments still require active maintenance because site behavior changes over time.

For a daily-updated private site database or a username-check API, contact [maigret@soxoj.com](mailto:maigret@soxoj.com). Commercial offerings include:

- Private database with 5,000+ sites, updated daily.
- Username-check API for product integrations.

## Responsible use

Use Maigret for educational, authorized, and lawful research only. You are responsible for complying with applicable laws and regulations, including GDPR and CCPA. The authors are not responsible for misuse.

Relevant SOWEL classifications:

- [SOTL-2.2: Search for accounts on other platforms](https://sowel.soxoj.com/other-platform-accounts)
- [SOTL-6.1: Check login reuse](https://sowel.soxoj.com/logins-reuse)
- [SOTL-6.2: Check nickname reuse](https://sowel.soxoj.com/nicknames-reuse)

## Community and license

- [Open an issue](https://github.com/soxoj/maigret/issues)
- [GitHub Discussions](https://github.com/soxoj/maigret/discussions)
- [Telegram](https://t.me/soxoj)

MIT © [Maigret](https://github.com/soxoj/maigret)
