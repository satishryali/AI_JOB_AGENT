"""Export the saved shortlist as an Excel-friendly CSV."""

import csv
import io
from pathlib import Path

from src.db.repository import job_to_dict, list_jobs
from src.db.session import session_scope


COLUMNS = ["id", "title", "company", "location", "source", "salary", "match_score",
           "application_status", "job_url", "posted_date", "collected_at",
           "matched_skills", "missing_skills", "match_explanation", "description"]


def jobs_csv() -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=COLUMNS, extrasaction="ignore")
    writer.writeheader()
    with session_scope() as session:
        # Export the entire database, including unscored and low scoring jobs.
        for record in list_jobs(session, limit=None):
            data = job_to_dict(record)
            for key in COLUMNS:
                value = data.get(key)
                if isinstance(value, list):
                    value = "; ".join(value)
                if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
                    value = "'" + value
                data[key] = value
            writer.writerow(data)
    return "\ufeff" + output.getvalue()


def save_jobs_csv(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(jobs_csv(), encoding="utf-8", newline="")
    return path.resolve()
