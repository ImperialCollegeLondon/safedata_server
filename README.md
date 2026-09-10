# safedata_server

A web application providing a searchable database of metadata for datasets
published using the [`safedata_validator`](https://github.com/ImperialCollegeLondon/safedata_validator)
program.

## 1. Overview

When a dataset is published using `safedata_validator`:

1. The dataset is published to Zenodo, possibly as a new version of an
   existing dataset.
2. `safedata_validator` exports a JSON document containing validated
   metadata for the dataset.
3. That JSON is uploaded here, either via the web UI or the API, and its
   metadata is parsed into a searchable database.

The application also maintains a **gazetteer** — a spatial database of
known sampling locations — and a table of **location aliases**, so that
location names used inconsistently across datasets can still be resolved
to a single, known site.

### Tech stack

- **Django** + **GeoDjango**, with **SpatiaLite** as the spatial database
  backend (no separate database server required)
- **Django REST Framework** for the API, with token authentication for
  upload endpoints
- **Leaflet** (via CDN) for the gazetteer map and taxon browsing pages
- **uv** for Python dependency and environment management
- **pytest** / **pytest-django** for testing

### App structure

```
config/       Project settings, root URLs
gazetteer/    Gazetteer + alias models, ingestion, map/upload web pages
datasets/     Dataset metadata models, ingestion, browse/detail/taxa/upload web pages
api/          All JSON/REST endpoints: search, records, taxa, uploads, downloads
```

The rule of thumb: **`gazetteer`/`datasets`** hold models, ingestion logic,
and human-facing HTML pages; **`api`** holds everything that returns JSON.

---

## 2. Developer guide

### Prerequisites

This project uses GeoDjango, which needs several native (non-Python)
libraries installed on your system before anything will run: **GDAL**,
**GEOS**, and **SpatiaLite** (the SQLite spatial extension).

#### macOS

```bash
brew install gdal geos spatialite-tools libspatialite sqlite
```

**Important — SQLite extension loading.** macOS's system Python/SQLite is
built *without* support for loading extensions (a deliberate Apple
security choice), which SpatiaLite requires. If you're using `pyenv`, you
need to rebuild your Python version with extension loading enabled,
linked against Homebrew's SQLite (not the system one):

```bash
pyenv uninstall 3.12.8   # or whichever version you're using
rm -rf ~/.pyenv/cache

PYTHON_CONFIGURE_OPTS="--enable-loadable-sqlite-extensions" \
LDFLAGS="-L$(brew --prefix sqlite)/lib" \
CPPFLAGS="-I$(brew --prefix sqlite)/include" \
PKG_CONFIG_PATH="$(brew --prefix sqlite)/lib/pkgconfig" \
pyenv install 3.12.8
```

Verify it worked before proceeding:

```bash
$(pyenv root)/versions/3.12.8/bin/python3 -c \
  "import sqlite3; print(sqlite3.connect(':memory:').enable_load_extension)"
```

This should print a bound method, not raise an `AttributeError`.

#### Linux (Debian/Ubuntu)

```bash
sudo apt install gdal-bin libgdal-dev libgeos-dev libsqlite3-mod-spatialite spatialite-bin
```

System Python on Linux typically already supports extension loading, so
the rebuild step above usually isn't necessary.

### Project setup

```bash
git clone <repo-url>
cd safedata_server

uv python pin 3.12.8   # or your rebuilt version
uv sync
```

### Environment variables

Copy the example file and fill in real values:

```bash
cp .env.example .env
```

| Variable | Description |
|---|---|
| `GAZETTEER_LOCAL_EPSG` | EPSG code for the deployment's local projected CRS (e.g. `32650` for UTM Zone 50N — used for accurate distance/area calculations and spatial buffering). Get this right for your field site region; it cannot be safely guessed. |
| `DJANGO_SECRET_KEY` | A random secret string for Django's cryptographic signing. Generate one with `python -c "import secrets; print(secrets.token_urlsafe(50))"`. |

`GDAL_LIBRARY_PATH` / `GEOS_LIBRARY_PATH` are resolved automatically at
runtime on macOS via `brew --prefix`, so you shouldn't need to set these
by hand unless your setup is non-standard.

### Database setup

```bash
uv run python manage.py migrate
uv run python manage.py createsuperuser
```

The database is a single SpatiaLite file (`db.sqlite3`) — no separate
database server to run.

### Generate an API token

Upload endpoints require token authentication. Generate one for your
superuser (or a dedicated service account):

```bash
uv run python manage.py drf_create_token <username>
```

This prints a 40-character token. Use it in the `Authorization` header
on upload requests (see the Admin/User Guide below).

### Running the app

```bash
uv run python manage.py runserver
```

Visit `http://127.0.0.1:8000/`.

### Running tests

```bash
uv run pytest
```

Tests are organised per app, with shared fixtures (`sample_gazetteer`,
`api_client_with_token`, etc.) in the project-root `conftest.py`.

### Ingesting data in bulk

For ingesting many dataset JSON files at once (e.g. a batch migration),
use the management command rather than uploading one at a time:

```bash
uv run python manage.py ingest_datasets path/to/directory/
```

This ingests every `.json` file in the directory, printing a summary of
successes and failures. Individual dataset failures don't stop the batch.

---

## 3. Admin/user guide

There are two ways to get data into the system: the **web UI** (for a
person, in a browser, logged in) and the **API** (for scripts, tools, or
the `safedata` R package).

### Web UI

All upload pages require being logged in (`@login_required` — the same
account as the Django admin).

| Page | URL | Purpose |
|---|---|---|
| Home | `/` | Landing page with links to everything below |
| Gazetteer map | `/gazetteer/map/` | Searchable map of all known sampling locations |
| Upload gazetteer | `/gazetteer/upload/` | Upload a gazetteer GeoJSON file and/or an aliases CSV |
| Datasets | `/datasets/` | Searchable list of published datasets |
| Dataset detail | `/datasets/<zenodo_record_id>/` | Full metadata for one dataset |
| Upload dataset | `/datasets/upload/` | Upload a `safedata_validator` JSON export |
| Browse taxa | `/datasets/taxa/` | Collapsible taxonomic tree across all datasets (GBIF / Sequence toggle) |
| Admin | `/admin/` | Django admin — inspect raw table contents |

To upload via the web UI: log in at `/admin/login/`, then visit the
relevant upload page, choose a file, and submit. Success or failure is
shown as a message banner after redirect.

**Note on transaction behaviour:** a dataset upload and a gazetteer
GeoJSON upload are both all-or-nothing — if any part of the file fails,
nothing from that file is saved. The same is true of the aliases CSV
upload. Fix the file and re-upload; there's no partial state to clean up.

### API

All API endpoints are under `/api/`, with full reference documentation
— authentication, uploading, downloading, search, records, and taxon
identity notes — available at `/api/docs/` once the server is running.