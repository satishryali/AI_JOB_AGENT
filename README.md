# AI Job Hunter

Python job-search assistant: collect listings, score them against your resume, tailor documents, and prepare resume drafts with application links. You review and submit applications yourself.

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
| `DATABASE_URL` | SQLAlchemy URL (`sqlite:///data/applications.db` or Postgres) |
| `LLM_API_KEY` | Optional. Used for cover letters / resume wording |
| `LLM_MODEL` | Default `deepseek-chat` |
| `USER_EMAIL`, `USER_FIRST_NAME`, `USER_LAST_NAME`, `USER_PHONE` | Form-fill profile |
| `RESUME_PATH` | Path to your resume |
| `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | Optional extra job API |
| `BROWSER_HEADLESS` | Playwright headless flag |
| `LOG_LEVEL` | `INFO` by default |

Do not put secrets in source files. `.env` is gitignored.

Settings precedence is process environment, then `.env`, then `config.yaml`, then model defaults. The default minimum match score is 70 and resume experience is 5 years; set these to your actual preferences and experience.

## Database Setup

Tables are created automatically on startup (`jobs`, `applications`, `user_profiles`). Existing data is not dropped.

**SQLite (default)**

```text
DATABASE_URL=sqlite:///data/applications.db
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
python -m src.main collect   # collect listings without scoring
python -m src.main pipeline  # collect and rank, print application links
python -m src.main pipeline --linkedin  # also collect through LinkedIn browser login
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
Temporary test files are written to `data/pytest-tmp/` to avoid Windows user-temp permission problems. The browser regression test runs when Playwright Chromium is installed.

## Job Collection

Default sources:

- LinkedIn, Indeed, Naukri, Glassdoor, and Google Jobs via [JobSpy](https://github.com/speedyapply/JobSpy).
- Remotive public API and optional Adzuna API.

Install `requirements.txt` into the interpreter used to run the app. The prepared local environment is `.venv`:

```powershell
.\.venv\Scripts\python.exe -m src.main
```

Open http://127.0.0.1:8000/jobs. Edit roles and locations, click **Collect jobs from all configured sources**, and continue reviewing saved jobs while collection runs. The page refreshes on completion and reports results or errors for each source. Click **Download CSV** for all saved jobs, including unscored jobs. Collection also updates `data/exports/jobs.csv`.

```powershell
.\.venv\Scripts\python.exe -m src.main collect --csv data/exports/jobs.csv
.\.venv\Scripts\python.exe -m src.main pipeline --csv data/exports/jobs.csv
```

The CSV includes title, company, location, source, salary, score, application status, application link, dates, skills, explanation, and description. It uses UTF-8 with BOM for Excel. Duplicates are merged before saving; existing jobs and manually tracked applications are retained.

Search saved jobs by title, company, or location; filter by source, status, and minimum score; click column headings to sort. To import a listing, paste its URL. Accessible HTML pages are read automatically, including structured JobPosting metadata. If a site requires login or blocks access, paste the job details into the optional fields instead.

Configure `JOB_COLLECTION_SITES` (comma separated), `JOB_COUNTRY` (default India), `JOB_MAX_QUERIES_PER_SOURCE` (default 6), and `JOB_SOURCE_TIMEOUT` (default 45 seconds per query). Collection searches each role and location, within the query limit, with a cap per source. Bangalore/Bengaluru are treated as one location for JobSpy searches. Sources run with at most three active collectors. If a later query fails, earlier collected listings are retained.

Some sites can return no results or block a request. This does not imply there are no jobs on that site; the source report distinguishes failures from returned results. This is multi-site collection, not guaranteed coverage of every website. Foundit and other unsupported boards can still be added through **Add a job from any platform**. The explicit `--linkedin` option adds the legacy browser collector, which may require manual login; it is not required for JobSpy's LinkedIn collection.

## AI Matching

Scoring is deterministic (0–100) from skills, title, location, experience, and salary text. It uses `data/resumes/skills.yaml` plus keywords found in your resume. The LLM is **not** required and is not allowed to invent qualifications.

Each job stores matched skills, missing skills, and an explanation.

Salary comparisons account for hourly, daily, weekly, monthly, and annual pay. Annualization assumes 40 hours per week and 260 working days per year. Known currency mismatches and ambiguous pay periods receive a neutral salary score rather than an unsupported comparison. Relative posting dates are supported; month/year offsets use 30/365 days.

## Resume Generation

**Tailor resume** reorders skills and writes a summary from your real resume. It will not invent jobs, degrees, or technologies. Resume and cover letter drafts are saved under `data/applications/` and can be downloaded as PDF, DOCX, or text. Review the content and formatting before uploading. Regeneration redirects back to the job page; documents for applications marked `applied` are preserved.

## Application Assistance

Workflow:

1. Collect and score jobs
2. Open a job in the dashboard
3. Generate a tailored resume / cover letter
4. Download and review the resume draft (PDF, DOCX, or text)
5. Open the **application link**, complete the form, and submit yourself
6. Set status to `applied` in the UI after you actually submit

The agent never auto-submits and never silently marks a job as applied.

`python -m src.main` opens the dashboard by default. `collect`, `pipeline`, and the legacy `apply` alias never fill or submit application forms. `APP_AUTO_APPLY` is a legacy setting and does not enable submission in these workflows.

LinkedIn application helpers return a manual-review result without clicking application controls. When a browser collector needs human input in a non-interactive environment, it raises an actionable error instead of waiting indefinitely.

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
Application link + downloadable resume draft
        ↓
You review and submit
        ↓
Application tracking + overview counts
```

Entry points:

- `python -m src.main` — FastAPI dashboard
- `src/jobs/searcher.py` — collect + match
- `src/db/` — SQLAlchemy models
- `src/portals/` — site-specific browser helpers; optional LinkedIn collection
- `src/ai/matcher.py` — scoring
- `src/api/app.py` — HTTP API / UI

## License

MIT
