"""Deterministic job matching. LLM is optional and never invents qualifications."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

import yaml

from src.config.logging import get_logger
from src.models.job import Job, MatchResult

logger = get_logger(__name__)

SCORE_BANDS = [
    ("90-100  High match", 90.0, 100.0, True),
    ("70-90", 70.0, 90.0, False),
    ("50-70", 50.0, 70.0, False),
    ("30-50", 30.0, 50.0, False),
    ("10-30", 10.0, 30.0, False),
]


def score_band(score: float | None) -> str | None:
    """Return band label, or None if below 10 / unscored."""
    if score is None:
        return None
    if score >= 90:
        return "90-100  High match"
    if score >= 70:
        return "70-90"
    if score >= 50:
        return "50-70"
    if score >= 30:
        return "30-50"
    if score >= 10:
        return "10-30"
    return None


def group_by_score_band(items: list, score_of) -> list[tuple[str, list]]:
    """Group items into display bands. Scores below 10 are dropped."""
    buckets: dict[str, list] = {label: [] for label, *_ in SCORE_BANDS}
    for item in items:
        label = score_band(score_of(item))
        if label:
            buckets[label].append(item)
    for label in buckets:
        buckets[label].sort(key=score_of, reverse=True)
    return [(label, buckets[label]) for label, *_ in SCORE_BANDS]


COMMON_SKILLS = [
    "python", "sql", "postgresql", "mysql", "oracle", "pl/sql", "plsql", "snowflake",
    "sap hana", "hana", "etl", "elt", "airflow", "dbt", "spark", "pyspark",
    "aws", "azure", "gcp", "docker", "kubernetes", "git", "linux",
    "pandas", "numpy", "tableau", "power bi", "excel", "control-m",
    "java", "javascript", "typescript", "react", "fastapi", "django", "flask",
    "machine learning", "ml", "ai", "nlp", "llm", "data engineer", "data scientist",
]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def load_user_skills(skills_path: Path | None = None, extra: list[str] | None = None) -> list[str]:
    skills: list[str] = []
    if skills_path and skills_path.exists():
        data = yaml.safe_load(skills_path.read_text(encoding="utf-8")) or {}
        for item in data.get("skills", []):
            if isinstance(item, dict) and item.get("name"):
                skills.append(str(item["name"]))
            elif isinstance(item, str):
                skills.append(item)
    if extra:
        skills.extend(extra)
    return _unique_keep_order(skills)


def extract_skills_from_text(text: str, catalog: list[str] | None = None) -> list[str]:
    blob = _norm(text)
    found: list[str] = []
    for skill in catalog or COMMON_SKILLS:
        token = _norm(skill)
        if len(token) < 2:
            continue
        pattern = r"(?<!\w)" + re.escape(token) + r"(?!\w)"
        if re.search(pattern, blob):
            found.append(skill)
    return _unique_keep_order(found)


def _unique_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = _norm(item)
        if key and key not in seen:
            seen.add(key)
            out.append(item)
    return out


def _skill_aliases(name: str) -> set[str]:
    n = _norm(name)
    aliases = {n, n.replace("&", "and")}
    if n in {"pl/sql", "plsql"}:
        aliases.update({"pl/sql", "plsql", "pl sql"})
    if "python" in n:
        aliases.add("python")
    if "snowflake" in n:
        aliases.add("snowflake")
    if n in {"etl", "elt", "etl/elt"}:
        aliases.update({"etl", "elt", "etl/elt"})
    if "sap hana" in n or n == "hana":
        aliases.update({"sap hana", "hana"})
    if "postgresql" in n or n == "postgres":
        aliases.update({"postgresql", "postgres", "psql"})
    if n == "sql & database development":
        aliases.update({"sql", "database"})
    return aliases


def skills_match(user_skills: list[str], job_skills: list[str]) -> tuple[list[str], list[str]]:
    user_alias = []
    for skill in user_skills:
        user_alias.append((skill, _skill_aliases(skill)))

    matched: list[str] = []
    missing: list[str] = []
    used: set[str] = set()
    for job_skill in job_skills:
        job_alias = _skill_aliases(job_skill)
        hit = None
        for original, aliases in user_alias:
            if aliases & job_alias:
                hit = original
                break
            # substring overlap for compound user skills
            if any(a in _norm(original) or _norm(original) in a for a in job_alias if len(a) >= 3):
                hit = original
                break
        if hit and hit not in used:
            matched.append(job_skill)
            used.add(hit)
        elif hit:
            matched.append(job_skill)
        else:
            missing.append(job_skill)
    return _unique_keep_order(matched), _unique_keep_order(missing)


def _title_score(job_title: str, preferred_roles: list[str]) -> float:
    title = _norm(job_title)
    if not preferred_roles:
        # generic technical titles
        tokens = ["python", "data", "sql", "database", "etl", "engineer", "analyst", "developer"]
        return 100.0 if any(t in title for t in tokens) else 40.0
    for role in preferred_roles:
        role_n = _norm(role)
        if role_n and role_n in title:
            return 100.0
        role_tokens = set(role_n.split())
        title_tokens = set(title.split())
        if role_tokens and len(role_tokens & title_tokens) / len(role_tokens) >= 0.5:
            return 80.0
    return 25.0


_CITY_ALIASES = {
    "bangalore": {"bangalore", "bengaluru", "blr"},
    "bengaluru": {"bangalore", "bengaluru", "blr"},
    "hyderabad": {"hyderabad", "hyd"},
}


def _location_tokens(text: str) -> set[str]:
    n = _norm(text)
    tokens = set(n.replace(",", " ").split())
    tokens.add(n)
    expanded = set(tokens)
    for token in list(tokens):
        for key, aliases in _CITY_ALIASES.items():
            if token == key or token in aliases:
                expanded.update(aliases)
    return expanded


def _location_score(job_location: str, preferred_locations: list[str], remote: bool) -> float:
    loc = _norm(job_location)
    job_tokens = _location_tokens(job_location)
    if remote or "remote" in loc:
        if not preferred_locations or any("remote" in _norm(p) for p in preferred_locations):
            return 80.0
        return 40.0
    if not preferred_locations:
        return 60.0
    for pref in preferred_locations:
        pref_tokens = _location_tokens(pref)
        if pref_tokens & job_tokens:
            return 100.0
        if _norm(pref) in loc or loc in _norm(pref):
            return 100.0
    return 20.0


def _experience_score(required: Optional[int], years: int) -> float:
    if required is None:
        return 70.0
    if years >= required:
        return 100.0
    if years >= required - 1:
        return 70.0
    if years >= required - 2:
        return 40.0
    return 10.0


def _salary_amounts(text: str) -> tuple[float, float, str, str] | None:
    """Return annualized bounds when a pay period is explicit.

    Hourly/day rates assume 40 hours/week and 260 working days/year. Different
    currencies or an explicit period on only one side are not compared.
    """
    blob = text.lower()
    currency = ""
    for code, pattern in [("INR", r"inr|\u20b9|\brs\.?|lpa|lakh|lac\b|crore"),
                          ("USD", r"usd|us\$|\$"), ("EUR", r"eur|\u20ac"), ("GBP", r"gbp|\u00a3")]:
        if re.search(pattern, blob):
            currency = code
            break
    period, factor = "", 1.0
    for label, pattern, multiplier in [
        ("hour", r"hour|hourly|/hr|per hr|\bhr\b", 2080),
        ("month", r"month|monthly|p\.m\.", 12),
        ("week", r"week|weekly", 52), ("day", r"daily|per day|/day", 260),
        ("year", r"year|annual|annum|lpa|p\.a\.", 1),
    ]:
        if re.search(pattern, blob):
            period, factor = label, multiplier
            break
    scale = 1.0
    if re.search(r"lpa|lakh|lac\b", blob):
        scale = 100000.0
    elif "crore" in blob:
        scale = 10000000.0
    values = []
    for amount, suffix in re.findall(r"(\d[\d,]*(?:\.\d+)?)\s*(million|crore|lakhs?|lacs?|lpa|k|m)?(?!\w)", blob):
        multiplier = {"k": 1000.0, "m": 1000000.0, "million": 1000000.0,
                      "lakh": 100000.0, "lakhs": 100000.0, "lac": 100000.0,
                      "lacs": 100000.0, "lpa": 100000.0, "crore": 10000000.0}.get(suffix, scale)
        values.append(float(amount.replace(",", "")) * multiplier * factor)
    if not values:
        return None
    return min(values), max(values), currency, period


def _salary_score(salary_text: str, expectation: str) -> float:
    job, expected = _salary_amounts(salary_text), _salary_amounts(expectation)
    if not job or not expected:
        return 70.0
    if job[2] and expected[2] and job[2] != expected[2]:
        return 70.0
    if bool(job[3]) != bool(expected[3]):
        return 70.0
    if job[1] >= expected[0]:
        return 100.0
    if job[1] >= expected[0] * 0.8:
        return 60.0
    return 30.0


def score_job(
    job: Job,
    user_skills: list[str],
    resume_text: str = "",
    preferred_locations: list[str] | None = None,
    preferred_roles: list[str] | None = None,
    years_experience: int = 0,
    salary_expectation: str = "",
    min_score: float = 50.0,
) -> MatchResult:
    """Compute a reproducible 0-100 match score from structured inputs."""
    catalog = _unique_keep_order(COMMON_SKILLS + user_skills)
    job_skills = list(job.skills_required) or extract_skills_from_text(job.description + " " + job.title, catalog)
    resume_skills = extract_skills_from_text(resume_text, catalog) if resume_text else []
    all_user = _unique_keep_order(user_skills + resume_skills)

    matched, missing = skills_match(all_user, job_skills)
    skill_ratio = (len(matched) / len(job_skills)) if job_skills else 0.5
    skill_component = skill_ratio * 100.0

    title_component = _title_score(job.title, preferred_roles or [])
    loc_component = _location_score(job.location, preferred_locations or [], job.remote)
    exp_component = _experience_score(job.experience_required, years_experience)
    salary_component = _salary_score(job.salary_range or "", salary_expectation)

    score = (
        skill_component * 0.50
        + title_component * 0.15
        + loc_component * 0.15
        + exp_component * 0.10
        + salary_component * 0.05
        + 5.0  # technology-stack presence already in skills; small baseline
    )
    score = round(max(0.0, min(100.0, score)), 1)

    explanation = (
        f"Score: {score:.0f}. "
        f"Matched {len(matched)} of {len(job_skills) or 0} identified skills. "
        f"Title fit {title_component:.0f}/100, location fit {loc_component:.0f}/100."
    )
    if missing:
        explanation += f" Missing: {', '.join(missing[:8])}."

    return MatchResult(
        job=job,
        score=score,
        matched_skills=matched,
        missing_skills=missing,
        should_apply=score >= min_score,
        reasoning=explanation,
    )


def cache_key(job_id: str, resume_fingerprint: str) -> str:
    return f"{job_id}::{resume_fingerprint}"


def dump_match_cache(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
