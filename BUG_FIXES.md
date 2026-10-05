# Reported bug fixes

| # | Reported issue | Resolution |
| --- | --- | --- |
| 1 | DeepSeek reasoner fails on JSON mode | Kept the existing `deepseek-chat` environment setting; legacy reasoner requests omit unsupported JSON-mode/sampling options and still validate JSON objects and schemas. |
| 2 | LinkedIn automatically submits | Application entry points return manual-review results without browser interactions; legacy Easy Apply completion follows the same contract. |
| 3 | Inconsistent configuration | Aligned database defaults to `data/applications.db`, minimum score to 70, and experience to 5. Environment overrides take precedence without exporting YAML defaults into process state. |
| 4 | Document routes return JSON for existing applications | Resume and cover letter actions redirect to the job page. Documents for jobs marked applied are preserved. |
| 5 | Only text document downloads | Added PDF and DOCX export and download links alongside text for both resumes and cover letters. |
| 6 | URL import never fetches details | Fetches public HTML, follows validated redirects, reads structured JobPosting data or page elements, and accepts manual details when fetching fails. |
| 7 | No interactive job controls | Added search, source/status/minimum-score filters, sortable columns, and result counts. All saved jobs are available for filtering. |
| 8 | Remotive logs once per listing | Summary logging now runs once after collection. |
| 9 | Overview loads complete tables | Counts use two aggregate SQL queries without loading ORM records. |
| 10 | Matching opens a transaction per job | Scores are computed first, then persisted in one transaction for the batch. Individual scoring failures remain isolated. |
| 11 | Latest application depends on unordered list | Relationship ordering and explicit maximum application ID select the latest record consistently. |
| 12 | Windows test temporary directory permissions | Pytest uses the workspace's `data/pytest-tmp/` directory. |
| 13 | Relative posting dates rejected | Added relative minute/hour/day/week/month/year parsing, including today and yesterday. Month/year offsets use 30/365 days. |
| 14 | Salary cadence ignored | Added annualization and Indian salary units. Uses 2,080 hours or 260 working days per year; ambiguous periods and known currency mismatches are neutral. |
| 15 | Human intervention waits forever without stdin | Non-interactive or closed stdin raises `HumanInterventionRequired` immediately; interactive terminal input remains supported. |

## Verification

- `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider`: **60 passed** on Windows, including the manual workflow and Chromium search/filter/sort checks.
- `pip check`: no broken requirements. `git diff --check`: no whitespace errors.
- PDF/DOCX/text downloads and repeated/applied document redirects covered by regression tests. A three-page sample PDF was rendered and visually inspected.
- Dashboard restarted; `/health`, `/jobs`, `/static/jobs.js`, and `/api/overview` verified against the running application. Existing job records retained.

## Verification limits

External job-site and paid LLM calls were mocked in the regression suite. Sites requiring login or blocking requests still need manually pasted job details; collection does not guarantee access to every platform. DOCX files were structurally checked, but visual DOCX rendering was unavailable because renderer dependencies and LibreOffice are not installed. PDF output was visually checked.
