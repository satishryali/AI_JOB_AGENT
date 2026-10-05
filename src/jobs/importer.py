"""Fetch job details from public HTML and JobPosting structured data."""

import asyncio
import ipaddress
import json
import socket
from urllib.parse import urlsplit, urljoin

import httpx
from bs4 import BeautifulSoup

from src.jobs.normalize import to_normalized


class JobImportError(ValueError):
    pass


async def validate_public_url(url: str) -> None:
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise JobImportError("Use a public HTTP or HTTPS job link")
        addresses = await asyncio.to_thread(socket.getaddrinfo, parsed.hostname, parsed.port or 443,
                                             type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
            raise JobImportError("Job links must point to a public website")
    except (ValueError, OSError) as e:
        raise JobImportError("Invalid or unreachable public job link") from e


def _job_postings(value):
    if isinstance(value, list):
        for item in value:
            yield from _job_postings(item)
    elif isinstance(value, dict):
        types = value.get("@type", [])
        if types == "JobPosting" or isinstance(types, list) and "JobPosting" in types:
            yield value
        for item in value.values():
            if isinstance(item, (dict, list)):
                yield from _job_postings(item)


def parse_job_page(html: str, url: str):
    soup = BeautifulSoup(html, "html.parser")
    posting = None
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            posting = next(_job_postings(json.loads(script.get_text())), None)
        except (ValueError, TypeError):
            continue
        if posting:
            break
    if posting:
        org = posting.get("hiringOrganization") or {}
        org = org if isinstance(org, dict) else {"name": str(org)}
        locations = posting.get("jobLocation") or []
        if isinstance(locations, dict):
            locations = [locations]
        places = []
        for location in locations:
            address = location.get("address", {}) if isinstance(location, dict) else {}
            if isinstance(address, str):
                places.append(address)
            elif isinstance(address, dict):
                places.append(", ".join(str(address[k]) for k in ["addressLocality", "addressRegion", "addressCountry"] if address.get(k)))
        if posting.get("jobLocationType") == "TELECOMMUTE":
            places.append("Remote")
        salary = posting.get("baseSalary") or {}
        salary = salary if isinstance(salary, dict) else {}
        value = salary.get("value") or {}
        if isinstance(value, (int, float)):
            value = {"value": value}
        value = value if isinstance(value, dict) else {}
        amounts = [value[k] for k in ("minValue", "maxValue") if value.get(k) is not None]
        if not amounts and value.get("value") is not None:
            amounts = [value["value"]]
        pay = " ".join(filter(None, [str(salary.get("currency") or ""),
                                    " - ".join(map(str, amounts)), str(value.get("unitText") or "")]))
        data = dict(title=posting.get("title"), company=org.get("name"),
                    location="; ".join(places), description=BeautifulSoup(str(posting.get("description") or ""), "html.parser").get_text("\n", strip=True),
                    salary=pay, posted_date=posting.get("datePosted"),
                    job_url=url, source=urlsplit(url).hostname.removeprefix("www."))
    else:
        title = soup.select_one('h1, meta[property="og:title"]')
        company = soup.select_one('[itemprop="hiringOrganization"], .topcard__org-name-link, .job-company')
        desc = soup.select_one('[itemprop="description"], .jobs-description__content, .show-more-less-html__markup, #jobDescriptionText, #job-details, .job-description')
        location = soup.select_one('[itemprop="jobLocation"], .topcard__flavor--bullet, .job-location')
        data = dict(title=(title.get("content") or title.get_text(" ", strip=True)) if title else "",
                    company=company.get_text(" ", strip=True) if company else "",
                    location=location.get_text(" ", strip=True) if location else "",
                    description=desc.get_text("\n", strip=True) if desc else "",
                    job_url=url, source=urlsplit(url).hostname.removeprefix("www."))
    if not data.get("title") or not data.get("description"):
        raise JobImportError("Could not extract a job description. The site may require login or block fetching; paste the details manually.")
    return to_normalized(data)


async def fetch_job_details(url: str):
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            for _ in range(4):
                await validate_public_url(url)
                async with client.stream("GET", url, headers={"User-Agent": "AIJobHunter/1.0"}) as response:
                    if response.is_redirect:
                        url = urljoin(url, response.headers.get("location", ""))
                        continue
                    response.raise_for_status()
                    if "html" not in response.headers.get("content-type", "").lower():
                        raise JobImportError("Job link must return an HTML page")
                    chunks, size = [], 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > 2_000_000:
                            raise JobImportError("Job page is too large to import")
                        chunks.append(chunk)
                    return parse_job_page(b"".join(chunks).decode(response.encoding or "utf-8", errors="replace"), url)
        raise JobImportError("Job link redirected too many times")
    except httpx.HTTPError as e:
        raise JobImportError("Could not fetch this job page; paste its details manually") from e
