# AI Job Hunter

Python job-search assistant: collect listings, score them against your resume, tailor documents, and **prepare** applications. Final submission always stays under your control.

## Requirements

- Python 3.10+
- Optional: Docker (PostgreSQL + app)
- Optional: Playwright browsers (only for in-browser application assistance)
- Optional: LLM API key (DeepSeek/OpenAI-compatible). Matching works without an LLM.

## Installation

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
# source .venv/bin/activate

pip install -r requirements.txt
playwright install chromium
```

## Environment Variables

```bash
copy .env.example .env
# macOS/Linux: cp .env.example .env
```

Important variables (see `.env.example` for the full list):

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy URL (`sqlite:///data/job_hunter.db` or Postgres) |
| `LLM_API_KEY` | Optional. Used for cover letters / resume wording |
| `LLM_MODEL` | Default `deepseek-chat` |
| `USER_EMAIL`, `USER_FIRST_NAME`, `USER_LAST_NAME`, `USER_PHONE` | Form-fill profile |
| `RESUME_PATH` | Path to your resume |
| `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | Optional extra job API |
| `BROWSER_HEADLESS` | Playwright headless flag |
| `LOG_LEVEL` | `INFO` by default |

Do not put secrets in source files. `.env` is gitignored.

## Database Setup

Tables are created automatically on startup (`jobs`, `applications`, `user_profiles`). Existing data is not dropped.

**SQLite (default)**

```text
DATABASE_URL=sqlite:///data/job_hunter.db
```

**PostgreSQL** (Docker Compose provides this):

```text
DATABASE_URL=postgresql://jobhunter:jobhunter@localhost:5432/jobhunter
```

## Running the Application

Dashboard (default):

```bash
python -m src.main
```

Open http://127.0.0.1:8000

Collect and score jobs from the CLI (does **not** apply):

```bash
python -m src.main pipeline
```

Docker:

```bash
docker compose up -d --build
```

App: http://localhost:8000  
Postgres: `localhost:5432`

Place a resume at `data/resumes/resume.pdf` (or set `RESUME_PATH`) and edit `data/resumes/skills.yaml`.

## Running Tests

```bash
pytest
```

Tests mock external APIs and do not call job sites or LLMs.

## Job Collection

Default collectors:

- **Remotive** — public HTTP API (no key). Isolated failures.
- **Adzuna** — skipped unless `ADZUNA_APP_ID` and `ADZUNA_APP_KEY` are set.

LinkedIn / Indeed / Naukri / Foundit portal modules still exist for **manual browser assistance**. They are not used for bulk collection because they require logins and are easy to break. A failed source never stops the others.

Use **Collect jobs** on the dashboard or `python -m src.main pipeline`.

## AI Matching

Scoring is deterministic (0–100) from skills, title, location, experience, and salary text. It uses `data/resumes/skills.yaml` plus keywords found in your resume. The LLM is **not** required and is not allowed to invent qualifications.

Each job stores matched skills, missing skills, and an explanation.

## Resume Generation

**Tailor resume** reorders skills and writes a summary from your real resume. It will not invent jobs, degrees, or technologies. Output is saved under `data/applications/`.

## Application Assistance

Workflow:

1. Collect and score jobs
2. Open a job in the dashboard
3. Generate a tailored resume / cover letter
4. **Prepare in browser** fills known fields and **stops**
5. You review the page and click Submit yourself
6. Set status to `applied` in the UI after you actually submit

The agent never auto-submits and never silently marks a job as applied.

If a site shows CAPTCHA, MFA, or a login wall, stop and continue manually.

## Troubleshooting

| Issue | What to try |
| --- | --- |
| No jobs | Remotive API must be reachable. Check logs in `data/logs/agent.log` |
| Adzuna skipped | Set `ADZUNA_APP_ID` and `ADZUNA_APP_KEY` or ignore it |
| Empty profile on forms | Set `USER_*` variables and add a resume |
| LLM errors | Matching still works. Cover letters fall back to `data/templates/cover_letter.txt` |
| Playwright failures | A screenshot is stored under `data/screenshots/`. Browser is closed afterwards |
| Database errors | Confirm `DATABASE_URL`. SQLite directory `data/` must be writable |
| Port in use | Set `PORT` in `.env` |

## Architecture

```
User profile / resume
        ↓
Collectors (Remotive, optional Adzuna) — failures isolated
        ↓
Normalize + dedupe (source + external id, else company/title/location/URL)
        ↓
SQLite or PostgreSQL
        ↓
Deterministic match scoring
        ↓
Dashboard job list
        ↓
Resume / cover letter (facts from your resume only)
        ↓
Playwright prepare (no submit)
        ↓
You review and submit
        ↓
Application tracking + overview counts
```

Entry points:

- `python -m src.main` — FastAPI dashboard
- `src/jobs/searcher.py` — collect + match
- `src/db/` — SQLAlchemy models
- `src/portals/` — site-specific browser helpers (assistance only)
- `src/ai/matcher.py` — scoring
- `src/api/app.py` — HTTP API / UI

## License

MIT
