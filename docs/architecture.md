"# AI Job Agent - Multi-Portal Architecture

## Overview

The pipeline now supports multiple job portals and ATS (Applicant Tracking System) platforms. It can search for jobs, extract job information, and automatically apply whenever possible, handling redirects to external career pages seamlessly.

## Architecture

```
src/
├── portals/
│   ├── base.py                      # Base interfaces (BasePortal, BaseATS)
│   ├── selectors.py                 # Centralized selector registry
│   ├── registry.py                  # Portal/ATS registry with factory pattern
│   ├── linkedin.py                  # LinkedIn portal (existing)
│   ├── naukri.py                    # Naukri portal
│   ├── indeed.py                    # Indeed portal
│   ├── foundit.py                   # Foundit (Monster) portal
│   ├── ats_handler.py               # Universal ATS handler + AdaptiveFormFiller
│   ├── ats_implementations.py       # Concrete ATS implementations
│   └── __init__.py
├── utils/
│   └── profile_builder.py           # Builds user profile for form filling
└── jobs/
    └── tracker.py                   # Application tracker with extended schema
```

## Supported Platforms

### Job Portals (search + apply)
| Portal | Class | Login Required | Easy Apply |
|--------|-------|---------------|------------|
| LinkedIn | `LinkedInClient` | ✅ | ✅ |
| Naukri | `NaukriPortal` | ✅ | ✅ |
| Indeed | `IndeedPortal` | ✅ | ✅ |
| Foundit | `FounditPortal` | ✅ | ✅ |

### ATS Platforms (redirect targets)
| ATS | Class | Detection |
|-----|-------|-----------|
| Workday | `WorkdayATS` | URL/domain |
| Greenhouse | `GreenhouseATS` | URL/domain |
| Lever | `LeverATS` | URL/domain |
| Ashby | `AshbyATS` | URL/domain |
| SmartRecruiters | `SmartRecruitersATS` | URL/domain |
| iCIMS | `ICIMSATS` | URL/domain |
| Oracle Taleo | `TaleoATS` | URL/domain |
| SAP SuccessFactors | `SuccessFactorsATS` | URL/domain |
| BambooHR | `BambooHRATS` | URL/domain |
| Jobvite | `JobviteATS` | URL/domain |

## Key Design Patterns

### Common Interface (BasePortal)
Every portal implements:
- `login()` → `LoginStatus`
- `search_jobs(params: SearchParams)` → `list[Job]`
- `extract_job(job_url)` → `Optional[Job]`
- `apply(job, resume_path, cover_letter_path, profile)` → `ApplicationResult`

### Universal Applicant
The `UniversalApplicant` class in `ats_handler.py` handles any form on any platform:
1. Detects the platform via `ATSDetector`
2. Finds and clicks the Apply button
3. Uses `AdaptiveFormFiller` to fill the form intelligently
4. Navigates multi-step forms
5. Confirms successful submission

### Form Filling (AdaptiveFormFiller)
- **Detects field types**: text, select, radio, checkbox, file
- **Matches labels** to profile data (first_name, email, phone, etc.)
- **Handles multi-page forms** by clicking Next/Continue/Submit
- **Uploads resume/cover letter** when file inputs are found
- **Auto-accepts** consent/agreement checkboxes

### Portal Registration (Registry)
```python
PortalRegistry.register_portal(\"naukri\", NaukriPortal)
PortalRegistry.register_ats(\"workday\", WorkdayATS)
```
New platforms just need a class that implements `BasePortal` or `BaseATS`.

## Auto-Detection Flow

When applying to a job:
1. Navigate to the job URL
2. Detect if we landed on LinkedIn, Naukri, Indeed, etc.
3. If redirected to an **external ATS** (Workday, Greenhouse, etc.):
   - Detect the ATS type from URL domain
   - Use `UniversalApplicant` to handle the application
   - Fill the form with `AdaptiveFormFiller`
4. If it's a known portal:
   - Use portal-specific selectors
   - Try Easy Apply / Quick Apply first
   - Fallback to **external redirect** handling if redirected

## Common Interface for Adding New Portals

To add a new portal (e.g., Glassdoor):
```python
from src.portals.base import BasePortal, BaseATS
from src.portals.selectors import PortalSelectors

class GlassdoorPortal(BasePortal):
    portal_name = \"glassdoor\"
    portal_source = JobSource.GLASSDOOR
    
    def __init__(self, context, page, credentials=None):
        super().__init__(context, page, credentials)
        self.selectors = GLASSDOOR_SELECTORS  # From selectors.py
    
    async def login(self): ...
    async def search_jobs(self, params): ...
    async def extract_job(self, job_url): ...
    async def apply(self, job, resume_path, cover_letter_path, profile): ...

# Register it
PortalRegistry.register_portal(\"glassdoor\", GlassdoorPortal)
```

## Configuration

### .env
```
# DeepSeek API
LLM_API_KEY=

# LinkedIn
LINKEDIN_USERNAME=your_email
LINKEDIN_PASSWORD=your_password

# Optional credentials for other portals
NAUKRI_USERNAME=...
NAUKRI_PASSWORD=...
INDEED_USERNAME=...
INDEED_PASSWORD=...
```

### Profile Builder
The `ProfileBuilder` extracts information from:
1. **Resume filename** → Name extraction
2. **Resume content** → Email, phone, LinkedIn, GitHub
3. **Settings** → LinkedIn email, resume path
4. **Defaults** → Work authorization, availability

## Logging
Structured logging for:
- Login success/failure
- Application started/completed
- Skipped (no apply button, external redirect)
- CAPTCHA detected
- Duplicate detected
- Timeout
- Upload success/failure

## Error Handling
- Expired sessions → re-login
- Network failures → retry with backoff
- Invalid selectors → fallback to universal handler
- Popup interruptions → dismiss handlers
- Multi-page forms → intelligent Next/Continue navigation
- CAPTCHA detection → log and skip
- Unexpected dialogs → auto-dismiss

## Performance
- Reuse browser sessions across portals
- Minimize page reloads
- Cache authentication where possible
- Concurrent searches where safe

## Security
- No hardcoded credentials
- Read secrets from environment variables
- Never log passwords or API keys
- Screenshots saved for error debugging"