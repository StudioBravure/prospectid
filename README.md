# Antigravity Prospector 🚀

A SaaS-grade B2B prospecting engine built with FastAPI, Celery, and Google Places API (New).

## Quick Start

1.  **Environment**
    Create a `.env` file in this directory (see `.env.example` in parent or create new):
    ```ini
    GOOGLE_PLACES_API_KEY=your_key
    DATABASE_URL=postgresql+asyncpg://antigravity:password@localhost:5432/prospector
    REDIS_URL=redis://localhost:6379/0
    ```

2.  **Infrastructure**
    Start Postgres and Redis:
    ```bash
    docker-compose up -d
    ```

3.  **Install Dependencies**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Run System**
    Start both API and Worker:
    ```bash
    python ../run_system.py
    ```
    *Note: Adjust `run_system.py` path if running from inside this folder.*

5.  **Access UI**
    Open `ui/index.html` in your browser.

## Architecture

*   **API**: FastAPI (Port 8000)
*   **Worker**: Celery (Scalable, Unbounded)
*   **Database**: Postgres (Schema in `models/`)
*   **Cache**: Redis (Deduplication fingerprints)

## Compliance

*   **Official Sources Only**: Scrapers strictly limit to the official website found in Google Maps.
*   **Opt-out**: Checks `opt_out_registry` before any enrichment.
*   **Audit**: Critical actions are logged to `audit_logs`.
