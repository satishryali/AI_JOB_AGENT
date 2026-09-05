"""Universal ATS (Applicant Tracking System) handler with adaptive form filling."""

import re
from typing import Optional
from urllib.parse import urlparse

from playwright.async_api import Page

from src.auth.credential_store import get_credential_store
from src.config.config_loader import get_settings
from src.config.logging import get_logger

logger = get_logger(__name__)


class ATSDetector:
    """Detect which ATS/career platform a page is on."""

    # Platform detection patterns
    PLATFORMS = {
        "linkedin": {
            "domains": ["linkedin.com"],
            "selectors": ["button.jobs-apply-button", ".jobs-easy-apply-modal"],
            "apply_button_labels": ["apply", "easy apply"],
        },
        "workday": {
            "domains": ["workday.com", "wd5.myworkday.com", "myworkday.com"],
            "selectors": ["[data-automation-id*='apply']", "button[data-testid*='apply']", "[ph-tevent='job_postings_apply']"],
            "apply_button_labels": ["apply", "apply now", "apply for this job"],
        },
        "greenhouse": {
            "domains": ["greenhouse.io", "boards.greenhouse.io"],
            "selectors": ["button[data-job-id]", "a[href*='/jobs/']", "#job-postings"],
            "apply_button_labels": ["apply", "apply now", "apply for this job", "apply for job"],
        },
        "lever": {
            "domains": ["lever.co", "jobs.lever.co"],
            "selectors": ["a[href*='lever.co']", ".posting-apply", "[data-qa='posting-apply']"],
            "apply_button_labels": ["apply", "apply now", "apply for this job", "apply for job"],
        },
        "smartrecruiters": {
            "domains": ["smartrecruiters.com"],
            "selectors": [".job-apply-link", "[data-template='apply']"],
            "apply_button_labels": ["apply", "apply now"],
        },
        "bamboohr": {
            "domains": ["bamboohr.com"],
            "selectors": ["[data-automation-id*='apply']", "button[data-testid*='apply']"],
            "apply_button_labels": ["apply", "apply now"],
        },
        "icims": {
            "domains": ["icims.com"],
            "selectors": ["[data-automation-id*='apply']", "button[data-testid*='apply']"],
            "apply_button_labels": ["apply", "apply now"],
        },
        "jobvite": {
            "domains": ["jobvite.com"],
            "selectors": ["[data-jobvite-id]", ".jv-apply", "a[href*='jobvite']"],
            "apply_button_labels": ["apply", "apply now"],
        },
        "taleo": {
            "domains": ["taleo.net"],
            "selectors": ["[data-target='apply']", "button[data-testid*='apply']"],
            "apply_button_labels": ["apply", "apply now"],
        },
        "successfactors": {
            "domains": ["successfactors.com", "sapsf.com"],
            "selectors": ["[data-automation-id*='apply']", "button[data-testid*='apply']"],
            "apply_button_labels": ["apply", "apply now"],
        },
    }

    @classmethod
    def detect(cls, page: Page, url: str = "") -> str:
        """Detect the platform based on URL and page content."""
        current_url = url or (page.url if page else "")

        # Check by domain
        domain = urlparse(current_url).netloc.lower()
        for platform, config in cls.PLATFORMS.items():
            for d in config["domains"]:
                if d in domain:
                    return platform

        # Try to detect from page content/URL pattern
        if page:
            breadcrumb = (page.title() or "").lower() if hasattr(page, "title") else ""
            current_path = urlparse(current_url).path.lower()

            for platform, config in cls.PLATFORMS.items():
                for selector in config["selectors"]:
                    # We can't check CSS selectors synchronously here
                    pass

            # Check URL patterns
            if "/job/" in current_path or "/jobs/" in current_path:
                # Generic job page - check for common patterns
                if "workday" in domain or ".wd5." in current_url:
                    return "workday"
                if "greenhouse" in current_url:
                    return "greenhouse"
                if "lever" in current_url:
                    return "lever"

        return "unknown"


class AdaptiveFormFiller:
    """Smart form filler that adapts to any ATS form structure."""

    # Common field labels and selectors
    FIELD_PATTERNS = {
        "first_name": ["first name", "first_name", "fname", "given name"],
        "last_name": ["last name", "last_name", "lname", "family name", "surname"],
        "email": ["email", "e-mail", "email address", "email_address"],
        "phone": ["phone", "phone number", "phone_number", "mobile", "telephone", "contact number", "contact_number"],
        "city": ["city", "location", "current city", "current location"],
        "linkedin": ["linkedin", "linkedin url", "linkedin profile", "linkedin_profile"],
        "github": ["github", "github url", "github profile"],
        "website": ["website", "portfolio", "personal website", "portfolio url"],
        "resume": ["resume", "cv", "attachment", "upload resume", "upload your resume"],
        "cover_letter": ["cover letter", "cover_letter", "coverletter"],
        "experience": ["years of experience", "experience", "year of experience"],
        "salary": ["expected salary", "salary expectation", "current salary"],
        "notice_period": ["notice period", "notice_period", "notice"],
        "how_did_you_hear": ["how did you hear", "referral source", "how did you hear about"],
        "work_authorization": ["work authorization", "work authorization status", "authorization", "eligibility", "sponsorship"],
        "experience_level": ["experience level", "seniority", "job level"],
        "willing_to_relocate": ["willing to relocate", "relocate"],
        "availability": ["available to start", "start date", "availability", "when can you start"],
        "qualification": ["highest education", "qualification", "degree", "education"],
        "gender": ["gender"],
        "race": ["race", "ethnicity", "veteran status"],
    }

    BUTTON_PATTERNS = {
        "submit": ["submit", "submit application", "send application", "apply", "finish", "complete application"],
        "next": ["next", "continue", "proceed", "next page", "continue to next"],
        "review": ["review", "review application", "continue to review"],
        "back": ["back", "previous", "go back"],
    }

    # Field types
    TEXT_INPUT_SELECTORS = [
        "input[type='text']", "input[type='email']", "input[type='tel']", "input[type='number']",
        "input:not([type])", "textarea", "input[type='search']",
    ]

    SELECT_SELECTORS = ["select", "[data-automation-id*='select']"]

    RADIO_SELECTORS = ["input[type='radio']", "[role='radio']"]
    CHECKBOX_SELECTORS = ["input[type='checkbox']", "[role='checkbox']"]

    def __init__(self, page: Page):
        self.page = page

    async def fill_form(self, profile: dict) -> dict:
        """Intelligently fill a form based on user profile data."""
        results = {"filled": [], "skipped": [], "errors": []}

        # Find all form fields
        fields = await self._collect_form_fields()

        for field in fields:
            field_data = await self._get_field_info(field)

            if field_data["type"] == "file":
                await self._handle_file_field(field, field_data, profile, results)
            elif field_data["type"] == "select":
                await self._handle_select_field(field, field_data, profile, results)
            elif field_data["type"] == "radio":
                await self._handle_radio_field(field, field_data, profile, results)
            elif field_data["type"] == "checkbox":
                await self._handle_checkbox_field(field, field_data, profile, results)
            elif field_data["type"] == "text":
                await self._handle_text_field(field, field_data, profile, results)

        logger.info("Form filling complete", filled=len(results["filled"]), skipped=len(results["skipped"]))
        return results

    async def _collect_form_fields(self) -> list:
        """Collect all interactive form fields."""
        fields = []

        # Text inputs
        for selector in self.TEXT_INPUT_SELECTORS:
            try:
                elements = await self.page.query_selector_all(selector)
                fields.extend(elements)
            except Exception:
                pass

        # Selects
        for selector in self.SELECT_SELECTORS:
            try:
                elements = await self.page.query_selector_all(selector)
                fields.extend(elements)
            except Exception:
                pass

        # Radios (group by name)
        try:
            radios = await self.page.query_selector_all(self.RADIO_SELECTORS[0])
            # Deduplicate by name - we'll handle groups
            fields.extend(radios)
        except Exception:
            pass

        # Checkboxes
        for selector in self.CHECKBOX_SELECTORS:
            try:
                elements = await self.page.query_selector_all(selector)
                fields.extend(elements)
            except Exception:
                pass

        # File inputs
        try:
            files = await self.page.query_selector_all("input[type='file']")
            fields.extend(files)
        except Exception:
            pass

        # Deduplicate by element handle
        unique_fields = []
        seen = set()
        for field in fields:
            try:
                field_id = await field.get_attribute("id") or await field.get_attribute("name") or str(await field.get_attribute("placeholder"))
                if field_id and field_id not in seen:
                    seen.add(field_id)
                    unique_fields.append(field)
            except Exception:
                unique_fields.append(field)

        return unique_fields

    async def _get_field_info(self, field) -> dict:
        """Get metadata about a form field."""
        try:
            attrs = await field.evaluate("""el => {
                const info = {
                    tag: el.tagName.toLowerCase(),
                    type: el.type || '',
                    id: el.id || '',
                    name: el.name || '',
                    placeholder: el.placeholder || '',
                    label: '',
                    aria_label: el.getAttribute('aria-label') || '',
                    data_automation_id: el.getAttribute('data-automation-id') || '',
                    data_testid: el.getAttribute('data-testid') || '',
                    required: el.required || false,
                    disabled: el.disabled || false,
                    readonly: el.readOnly || false,
                    value: el.value || '',
                    text: '',
                };
                
                // Try to find label
                if (el.id) {
                    const label = document.querySelector(`label[for="${el.id}"]`);
                    if (label) info.label = label.textContent.trim();
                }
                
                // Check closest label
                if (!info.label) {
                    const parent = el.closest('.field, .form-group, .form-field, [class*="field"]');
                    if (parent) {
                        const lbl = parent.querySelector('label, legend');
                        if (lbl) info.label = lbl.textContent.trim();
                    }
                }
                
                // Try to get text from container
                if (!info.label) {
                    const container = el.closest('div');
                    if (container) {
                        const text = container.textContent.trim();
                        if (text.length < 100) info.text = text;
                    }
                }
                
                // Determine field type
                let fieldType = 'text';
                if (el.tagName === 'select') fieldType = 'select';
                else if (el.type === 'radio') fieldType = 'radio';
                else if (el.type === 'checkbox') fieldType = 'checkbox';
                else if (el.type === 'file') fieldType = 'file';
                else if (el.type === 'email') fieldType = 'text';
                else if (el.type === 'tel') fieldType = 'text';
                else if (el.type === 'number') fieldType = 'text';
                else if (el.tagName === 'textarea') fieldType = 'text';
                
                return {...info, fieldType};
            }""")
            return attrs
        except Exception:
            return {"fieldType": "unknown", "label": "", "placeholder": ""}

    async def _handle_text_field(self, field, field_data: dict, profile: dict, results: dict) -> None:
        """Fill a text field."""
        try:
            label_text = self._get_field_label(field_data)
            value = self._match_value(label_text, profile)

            if not value:
                results["skipped"].append(label_text or field_data.get("placeholder", "unknown"))
                return

            if field_data.get("disabled") or field_data.get("readonly"):
                results["skipped"].append(label_text)
                return

            # Clear and fill
            await field.click()
            await field.fill("")
            await field.type(value, delay=20)

            results["filled"].append(label_text or field_data.get("placeholder", "unknown"))
            logger.debug("Filled text field", field=label_text, value="***" if "password" in label_text.lower() else value)

        except Exception as e:
            results["errors"].append(str(e))

    async def _handle_select_field(self, field, field_data: dict, profile: dict, results: dict) -> None:
        """Fill a select/dropdown field."""
        try:
            label_text = self._get_field_label(field_data)
            value = self._match_value(label_text, profile)

            if not value:
                results["skipped"].append(label_text)
                return

            # Get options
            options = await field.query_selector_all("option")
            option_texts = []
            for opt in options:
                text = (await opt.inner_text()).strip()
                val = await opt.get_attribute("value") or text
                option_texts.append({"text": text, "value": val})

            # Try to find matching option
            for opt in option_texts:
                opt_lower = opt["text"].lower()
                if value.lower() in opt_lower or opt_lower in value.lower():
                    await field.select_option(label=opt["text"])
                    results["filled"].append(label_text)
                    return

            # Fallback: try to select by value
            for opt in option_texts:
                if value.lower() == opt["value"].lower():
                    await field.select_option(value=opt["value"])
                    results["filled"].append(label_text)
                    return

            # If no match, skip
            results["skipped"].append(label_text)

        except Exception as e:
            results["errors"].append(str(e))

    async def _handle_radio_field(self, field, field_data: dict, profile: dict, results: dict) -> None:
        """Fill radio button group."""
        try:
            label_text = self._get_field_label(field_data)
            value = self._match_value(label_text, profile)

            if not value:
                results["skipped"].append(label_text)
                return

            # Get all radios in the same group
            name = field_data.get("name", "")
            if name:
                radios = await self.page.query_selector_all(f"input[type='radio'][name='{name}']")
            else:
                radios = [field]

            for radio in radios:
                try:
                    radio_label = await radio.evaluate("""el => {
                        const parent = el.closest('label') || el.closest('div');
                        return parent ? parent.textContent.trim() : '';
                    }""")

                    if value.lower() in radio_label.lower():
                        await radio.check(force=True)
                        results["filled"].append(label_text)
                        return
                except Exception:
                    continue

            # Try first radio as default
            try:
                await radios[0].check(force=True)
                results["filled"].append(label_text)
            except Exception:
                pass

        except Exception as e:
            results["errors"].append(str(e))

    async def _handle_checkbox_field(self, field, field_data: dict, profile: dict, results: dict) -> None:
        """Handle checkbox field."""
        try:
            label_text = self._get_field_label(field_data)

            # Check if it's already checked
            is_checked = await field.is_checked()

            # Match against profile values - default to checking consent/agreement boxes
            lower_label = (label_text or "").lower()
            should_check = False

            # Auto-accept agreements unless the value suggests otherwise
            if any(word in lower_label for word in ["agree", "consent", "accept", "authorize", "self-identify"]):
                should_check = True

            elif any(word in lower_label for word in ["newsletter", "subscribe", "updates"]):
                # Don't subscribe to newsletters by default
                should_check = False

            else:
                value = self._match_value(label_text, profile)
                should_check = bool(value and value.lower() in ["yes", "true", "1", "y"])

            if should_check and not is_checked:
                await field.check(force=True)
                results["filled"].append(label_text)

        except Exception as e:
            results["errors"].append(str(e))

    async def _handle_file_field(self, field, field_data: dict, profile: dict, results: dict) -> None:
        """Upload a file (resume, cover letter)."""
        try:
            label_text = self._get_field_label(field_data) or ""
            lower_label = label_text.lower()

            settings = get_settings()

            if any(word in lower_label for word in ["resume", "cv", "attachment"]):
                resume_path = settings.resume.path
                if resume_path.exists():
                    await field.set_input_files(str(resume_path))
                    results["filled"].append(f"resume: {resume_path.name}")
                    logger.info("Resume uploaded", path=str(resume_path))

            elif any(word in lower_label for word in ["cover", "letter"]):
                cover_path = settings.application.cover_letter_template
                if cover_path.exists():
                    await field.set_input_files(str(cover_path))
                    results["filled"].append(f"cover_letter: {cover_path.name}")

        except Exception as e:
            results["errors"].append(str(e))

    def _get_field_label(self, field_data: dict) -> str:
        """Get the best available label for a field."""
        candidates = [
            field_data.get("label", ""),
            field_data.get("aria_label", ""),
            field_data.get("placeholder", ""),
            field_data.get("data_automation_id", ""),
            field_data.get("data_testid", ""),
            field_data.get("name", ""),
            field_data.get("text", ""),
        ]
        for c in candidates:
            if c and c.strip():
                return c.strip()
        return ""

    def _match_value(self, label: str, profile: dict) -> str:
        """Match a field label to a value from the profile."""
        if not label:
            return ""

        lower_label = label.lower()

        # Basic profile fields
        for key, patterns in self.FIELD_PATTERNS.items():
            for pattern in patterns:
                if pattern in lower_label:
                    if key in profile and profile[key]:
                        return str(profile[key])
                    # Use default from resume data
                    break

        # Korean/Chinese/Japanese fallbacks (common in global job boards)
        if "이름" in label:
            return profile.get("first_name", "")
        if "성" in label:
            return profile.get("last_name", "")
        if "電話" in label or "전화" in label:
            return profile.get("phone", "")
        if "メール" in label or "이메일" in label:
            return profile.get("email", "")
        if "履歴書" in label:
            return str(get_settings().resume.path)

        return ""


class UniversalApplicant:
    """Universal job application handler that works on any platform."""

    # Selectors to detect login/registration requirement
    LOGIN_REQUIRED_SELECTORS = [
        "button:has-text('Sign In')",
        "button:has-text('Sign in')",
        "button:has-text('Log In')",
        "button:has-text('Log in')",
        "button:has-text('Login')",
        "button:has-text('login')",
        "a:has-text('Sign In')",
        "a:has-text('Sign in')",
        "a:has-text('Log In')",
        "a:has-text('Login')",
        "[data-automation-id*='login']",
        "[data-testid*='login']",
        "#login",
        ".login-form",
        "[class*='login']",
        "[class*='signin']",
    ]

    REGISTRATION_REQUIRED_SELECTORS = [
        "button:has-text('Create Account')",
        "button:has-text('Create account')",
        "button:has-text('Register')",
        "button:has-text('register')",
        "button:has-text('Sign Up')",
        "button:has-text('Sign up')",
        "button:has-text('Signup')",
        "a:has-text('Create Account')",
        "a:has-text('Create account')",
        "a:has-text('Register')",
        "a:has-text('register')",
        "a:has-text('Sign Up')",
        "a:has-text('Sign up')",
        "[data-automation-id*='register']",
        "[data-testid*='register']",
        "#register",
        ".register-form",
        "[class*='register']",
        "[class*='signup']",
    ]

    ALREADY_APPLIED_SELECTORS = [
        "button[disabled]:has-text('Applied')",
        "button[disabled]:has-text('applied')",
        "text=Already applied",
        "text=You have already applied",
        "text=Application already submitted",
        "[data-automation-id*='applied']",
        ".already-applied",
    ]

    PASSWORD_FIELD_SELECTORS = [
        "input[type='password']",
        "input[name='password']",
        "input[placeholder*='password' i]",
    ]

    EMAIL_FIELD_SELECTORS = [
        "input[type='email']",
        "input[name='email']",
        "input[placeholder*='email' i]",
        "input[placeholder*='e-mail' i]",
        "input[name='username']",
        "#email",
        "#username",
    ]

    REGISTRATION_NAME_FIELDS = [
        "input[placeholder*='first name' i]",
        "input[placeholder*='last name' i]",
        "input[name*='first_name']",
        "input[name*='last_name']",
        "input[name*='fname']",
        "input[name*='lname']",
    ]

    def __init__(self, page: Page, credentials: Optional[dict] = None):
        self.page = page
        self.filler = AdaptiveFormFiller(page)
        self.credentials = credentials or {}
        # Initialize credential store for auto-login/registration
        try:
            self.credential_store = get_credential_store()
        except Exception as e:
            logger.warning("Credential store initialization failed", error=str(e))
            self.credential_store = None

    async def apply_to_job(
        self,
        job_url: str,
        profile: dict,
        job_title: str = "",
        company: str = "",
        submit: bool = False,
    ) -> bool:
        """Apply to a job on any platform by adapting to the page."""
        try:
            logger.info("Starting universal application", url=job_url, job=job_title, company=company)

            # Navigate to job page
            await self.page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
            await self.page.wait_for_timeout(2000)

            # Check if already applied
            if await self._check_already_applied():
                logger.info("Already applied to this job", job=job_title, company=company, url=job_url)
                return False

            # Check if login/registration is required BEFORE finding apply button
            auth_handled = await self._handle_auth_requirement(profile)
            if auth_handled == "skipped":
                logger.warning("Skipped - manual intervention required for auth", url=job_url)
                return False

            # Detect platform
            platform = ATSDetector.detect(self.page, job_url)
            logger.info("Detected platform", platform=platform)

            # Find and click apply button
            apply_found = await self._find_and_click_apply(platform)

            if not apply_found:
                logger.warning("Apply button not found", url=job_url)
                return False

            # Wait for form to appear
            await self.page.wait_for_timeout(2000)

            # Check if we need to handle auth AFTER clicking apply (some redirect to login)
            auth_handled = await self._handle_auth_requirement(profile)
            if auth_handled == "skipped":
                logger.warning("Skipped - manual intervention required for auth", url=job_url)
                return False

            # Fill the application form
            form_results = await self.filler.fill_form(profile)
            logger.info("application preparation started", filled=len(form_results.get("filled", [])))

            # Navigate through multi-step forms but do not auto-submit
            for step in range(10):  # Max 10 steps
                progress = await self._check_form_progress()
                if progress == "submitted":
                    logger.info("Application already submitted on the site", job=job_title, company=company)
                    return True
                elif progress == "error":
                    logger.error("Form submission error")
                    return False

                auth_handled = await self._handle_auth_requirement(profile)
                if auth_handled == "skipped":
                    return False

                action = await self._click_next_or_submit(allow_submit=submit)
                if not action:
                    break

                await self.page.wait_for_timeout(1500)

            await self.page.wait_for_timeout(2000)
            if submit:
                current_url = self.page.url.lower()
                if any(word in current_url for word in ["success", "confirmation", "thank", "applied", "submitted"]):
                    logger.info("Application appears successful", url=current_url)
                    return True
                logger.warning("Could not confirm application submission")
                return False

            logger.info("Stopped before submit for user review", job=job_title, company=company)
            return False

        except Exception as e:
            logger.error("Universal application failed", error=str(e))
            return False

    async def _handle_auth_requirement(self, profile: dict) -> str:
        """Detect and handle login/registration requirements.

        Returns:
            "handled" - auth was handled successfully
            "skipped" - needs manual intervention
            "not_needed" - no auth required
        """
        try:
            # Check if registration is required
            for selector in self.REGISTRATION_REQUIRED_SELECTORS:
                try:
                    el = await self.page.query_selector(selector)
                    if el and await el.is_visible():
                        logger.warning("Registration required detected", selector=selector)
                        result = await self._attempt_registration(profile)
                        return result
                except Exception:
                    continue

            # Check if login is required
            for selector in self.LOGIN_REQUIRED_SELECTORS:
                try:
                    el = await self.page.query_selector(selector)
                    if el and await el.is_visible():
                        logger.warning("Login required detected", selector=selector)
                        result = await self._attempt_login(profile)
                        return result
                except Exception:
                    continue

            # Check if there are password fields visible (indicating login form)
            password_fields = await self.page.query_selector_all("input[type='password']")
            if password_fields:
                # Check if there's also email field - it's a login form
                email_fields = await self.page.query_selector_all(self.EMAIL_FIELD_SELECTORS[0])
                if email_fields:
                    logger.warning("Login form detected (password fields present)")
                    result = await self._attempt_login(profile)
                    return result

            return "not_needed"

        except Exception as e:
            logger.debug("Auth requirement check failed", error=str(e))
            return "not_needed"

    async def _attempt_login(self, profile: dict) -> str:
        """Try to login using stored or provided credentials."""
        try:
            # Detect the current platform from the URL
            platform = ATSDetector.detect(self.page, self.page.url)
            if platform == "unknown":
                # Try to determine from URL domain
                from urllib.parse import urlparse
                domain = urlparse(self.page.url).netloc
                # Use domain as portal name for lookup
                if self.credential_store:
                    # Try domain-based lookup first
                    stored = self.credential_store.get_credentials(domain)
                    if stored:
                        username = stored["username"]
                        password = stored["password"]
                    else:
                        # Fall back to profile email
                        username = profile.get("email", "") or self.credentials.get("username", "")
                        password = self.credentials.get("password", "")
                else:
                    username = profile.get("email", "") or self.credentials.get("username", "")
                    password = self.credentials.get("password", "")
            else:
                # We know the platform - check credential store
                username = ""
                password = ""

                if self.credential_store and self.credential_store.has_credentials(platform):
                    stored = self.credential_store.get_credentials(platform)
                    if stored:
                        username = stored["username"]
                        password = stored["password"]
                        logger.info("Using stored credentials from vault", portal=platform)

                # Fall back to config/credentials
                if not username:
                    username = profile.get("email", "") or self.credentials.get("username", "")
                if not password:
                    password = self.credentials.get("password", "")

            if not password:
                # Check if email field is prefilled (may be logged in already)
                email_field = await self.page.query_selector(self.EMAIL_FIELD_SELECTORS[0])
                if email_field:
                    current_value = await email_field.input_value()
                    if current_value and not password:
                        logger.warning(
                            "Password needed but not available in vault or config - manual intervention required",
                            portal=platform,
                        )
                        return "skipped"

                logger.warning(
                    "No password provided for login - check credential store",
                    portal=platform,
                )
                return "skipped"

            # Fill login form
            email_field = await self.page.query_selector(self.EMAIL_FIELD_SELECTORS[0])
            if email_field:
                await email_field.fill(username)

            password_field = await self.page.query_selector(self.PASSWORD_FIELD_SELECTORS[0])
            if password_field:
                await password_field.fill(password)

            # Click login button
            login_clicked = False
            for selector in [
                "button[type='submit']",
                "button:has-text('Sign In')",
                "button:has-text('Sign in')",
                "button:has-text('Log In')",
                "button:has-text('Log in')",
                "button:has-text('Login')",
                "button:has-text('login')",
                "button:has-text('Sign In to Continue')",
                "button:has-text('Continue with Email')",
            ]:
                try:
                    btn = await self.page.query_selector(selector)
                    if btn and await btn.is_visible():
                        await btn.click()
                        login_clicked = True
                        break
                except Exception:
                    continue

            if not login_clicked:
                logger.warning("Login button not found")
                return "skipped"

            # Wait for login to complete
            await self.page.wait_for_load_state("domcontentloaded", timeout=15000)
            await self.page.wait_for_timeout(3000)

            # Check if CAPTCHA appeared
            if self._is_captcha_on_page():
                logger.warning("CAPTCHA detected during login - manual intervention required")
                return "skipped"

            # Save/update credentials to vault for future use
            if self.credential_store and username and password:
                try:
                    self.credential_store.save_credentials(
                        portal=platform,
                        username=username,
                        password=password,
                        extra_data={"email": profile.get("email", ""), "phone": profile.get("phone", "")},
                        notes="Auto-saved from login attempt",
                    )
                    logger.info("Credentials saved to vault", portal=platform)
                except Exception as e:
                    logger.debug("Failed to save credentials", error=str(e))

            logger.info("Login successful", portal=platform)
            return "handled"

        except Exception as e:
            logger.error("Login attempt failed", error=str(e))
            return "skipped"

    async def _attempt_registration(self, profile: dict) -> str:
        """Try to register a new account using profile data."""
        try:
            logger.info("Attempting auto-registration with profile data")

            # Find registration form fields
            # Fill email
            email_field = None
            for selector in self.EMAIL_FIELD_SELECTORS:
                email_field = await self.page.query_selector(selector)
                if email_field:
                    break

            if email_field:
                await email_field.fill(profile.get("email", ""))

            # Fill name fields
            first_name = profile.get("first_name", "")
            last_name = profile.get("last_name", "")

            # Try common name field selectors
            name_inputs = await self.page.query_selector_all(
                "input[placeholder*='first' i], input[placeholder*='last' i], input[name*='name']"
            )

            for i, input_el in enumerate(name_inputs):
                placeholder = (await input_el.get_attribute("placeholder") or "").lower()
                name = (await input_el.get_attribute("name") or "").lower()

                if "first" in placeholder or "first" in name or "fname" in name:
                    await input_el.fill(first_name)
                elif "last" in placeholder or "last" in name or "lname" in name:
                    await input_el.fill(last_name)

            # Fill password if field exists (use a generated password)
            password_field = await self.page.query_selector("input[type='password']")
            if password_field:
                # Generate a password from profile + random
                import secrets
                generated = f"{profile.get('first_name', 'User').lower()}{secrets.randbelow(10000)}!{secrets.randbelow(100)}"
                await password_field.fill(generated)
                self.credentials["password"] = generated
                logger.debug("Generated new account password")

            # Fill phone if field exists
            phone_inputs = await self.page.query_selector_all(
                "input[placeholder*='phone' i], input[name*='phone']"
            )
            for phone_input in phone_inputs:
                await phone_input.fill(profile.get("phone", ""))

            # Accept terms if checkbox present
            term_checkboxes = await self.page.query_selector_all(
                "input[type='checkbox']"
            )
            for checkbox in term_checkboxes:
                try:
                    if not await checkbox.is_checked():
                        await checkbox.check(force=True)
                except Exception:
                    continue

            # Find and click the register/submit button
            for selector in [
                "button[type='submit']",
                "button:has-text('Create Account')",
                "button:has-text('Create account')",
                "button:has-text('Register')",
                "button:has-text('Sign Up')",
                "button:has-text('Sign up')",
                "button:has-text('Continue')",
                "button:has-text('Next')",
                "input[type='submit']",
                "[data-automation-id*='register']",
                "[data-testid*='register']",
            ]:
                try:
                    btn = await self.page.query_selector(selector)
                    if btn and await btn.is_visible():
                        await btn.click()
                        logger.info("Registration form submitted", selector=selector)
                        await self.page.wait_for_timeout(3000)

                        # Check for CAPTCHA
                        if self._is_captcha_on_page():
                            logger.warning("CAPTCHA during registration - manual intervention required")
                            return "skipped"

                        # Check if we need email verification
                        email_verify = await self.page.query_selector(
                            "text=Verify your email, text=Check your email, text=Verification required"
                        )
                        if email_verify:
                            logger.warning("Email verification required - manual intervention needed")
                            return "skipped"

                        return "handled"
                except Exception:
                    continue

            # If we filled all fields but couldn't find submit, we may need to scroll
            await self.page.mouse.wheel(0, 500)
            await self.page.wait_for_timeout(1000)

            logger.warning("Could not click registration submit button")
            return "skipped"

        except Exception as e:
            logger.error("Registration attempt failed", error=str(e))
            return "skipped"

    def _is_captcha_on_page(self) -> bool:
        """Check if CAPTCHA is present on the page."""
        captcha_selectors = [
            "iframe[src*='recaptcha']",
            "iframe[src*='captcha']",
            "iframe[src*='hcaptcha']",
            "[class*='captcha']",
            "[id*='captcha']",
            "[data-sitekey]",
        ]
        for selector in captcha_selectors:
            try:
                if self.page.query_selector(selector):
                    return True
            except Exception:
                continue
        return False

    async def _check_already_applied(self) -> bool:
        """Check if we've already applied to this job."""
        for selector in self.ALREADY_APPLIED_SELECTORS:
            try:
                el = await self.page.query_selector(selector)
                if el and await el.is_visible():
                    return True
            except Exception:
                continue
        return False

    async def _find_and_click_apply(self, platform: str) -> bool:
        """Find and click apply button on any page."""
        # Platform-specific selectors first
        if platform != "unknown" and platform in ATSDetector.PLATFORMS:
            for selector in ATSDetector.PLATFORMS[platform]["selectors"]:
                try:
                    btn = await self.page.query_selector(selector)
                    if btn:
                        await btn.click()
                        logger.info("Clicked apply button", selector=selector, platform=platform)
                        return True
                except Exception:
                    continue

        # Generic selectors - search by text
        generic_selectors = [
            "button:has-text('Apply')",
            "button:has-text('apply')",
            "button:has-text('Apply Now')",
            "button:has-text('apply now')",
            "button:has-text('Apply for this job')",
            "button:has-text('apply for this job')",
            "button:has-text('APPLY')",
            "button[type='button']:has-text('Apply')",
            "a:has-text('Apply')",
            "a:has-text('apply')",
            "a:has-text('Apply Now')",
            "a:has-text('apply now')",
            "input[type='submit'][value*='Apply']",
            "input[type='submit'][value*='apply']",
            "[role='button']:has-text('Apply')",
            ".btn:has-text('Apply')",
            "[data-testid*='apply']",
            "[data-automation-id*='apply']",
            "[ph-tevent*='apply']",
        ]

        for selector in generic_selectors:
            try:
                btn = await self.page.query_selector(selector)
                if btn:
                    # Check if button is enabled
                    is_disabled = await btn.evaluate("el => el.disabled || el.getAttribute('aria-disabled') === 'true'")
                    if not is_disabled:
                        await btn.click()
                        logger.info("Clicked apply button", selector=selector)
                        return True
            except Exception:
                continue

        # Try XPath-like approach for text matching on any element
        try:
            apply_links = await self.page.query_selector_all("a, button, [role='button']")
            for element in apply_links:
                try:
                    text = (await element.inner_text()).strip()
                    if any(word in text.lower() for word in ["apply", "apply now", "submit application"]):
                        await element.click()
                        logger.info("Clicked apply element by text", text=text)
                        return True
                except Exception:
                    continue
        except Exception:
            pass

        return False

    async def _check_form_progress(self) -> str:
        """Check the current state of the application form."""
        try:
            # Check for success indicators
            success_selectors = [
                "text=Application submitted",
                "text=Thank you for applying",
                "text=Your application has been submitted",
                "text=Congratulations",
                "[data-automation-id*='success']",
                ".application-success",
                "text=We have received your application",
            ]

            for selector in success_selectors:
                try:
                    if await self.page.query_selector(selector):
                        return "submitted"
                except Exception:
                    continue

            # Check for error indicators
            error_selectors = [
                "[data-automation-id*='error']",
                ".error-message",
                ".validation-error",
                "text=Please correct the errors",
            ]

            for selector in error_selectors:
                try:
                    if await self.page.query_selector(selector):
                        logger.warning("Form has validation errors")
                        return "error"
                except Exception:
                    continue

            return "in_progress"

        except Exception:
            return "in_progress"

    async def _click_next_or_submit(self, allow_submit: bool = False) -> bool:
        """Advance a multi-step form. Final submit is skipped unless allow_submit is True."""
        next_selectors = [
            "button:has-text('Next')",
            "button:has-text('next')",
            "button:has-text('Continue')",
            "button:has-text('continue')",
            "button:has-text('Review')",
            "button:has-text('review')",
            "input[type='button'][value*='Next']",
            "[data-automation-id*='next']",
            "[data-testid*='next']",
        ]
        submit_selectors = [
            "button[type='submit']",
            "button:has-text('Submit')",
            "button:has-text('submit')",
            "button:has-text('Finish')",
            "button:has-text('finish')",
            "button:has-text('Send')",
            "button:has-text('send')",
            "input[type='submit']",
            "input[type='button'][value*='Submit']",
            "[data-automation-id*='submit']",
            "[data-testid*='submit']",
        ]
        selectors = list(next_selectors)
        if allow_submit:
            selectors = submit_selectors + next_selectors

        for selector in selectors:
            try:
                btn = await self.page.query_selector(selector)
                if btn:
                    # Check if button is visible and enabled
                    visible = await btn.is_visible()
                    if visible:
                        is_disabled = await btn.evaluate("el => el.disabled || el.getAttribute('aria-disabled') === 'true'")
                        if not is_disabled:
                            await btn.click()
                            logger.info("Clicked next/submit button", selector=selector)
                            await self.page.wait_for_timeout(1000)
                            return True
            except Exception:
                continue

        allowed_words = ["next", "continue", "review"]
        if allow_submit:
            allowed_words.extend(["submit", "finish", "send", "apply"])
        try:
            buttons = await self.page.query_selector_all("button, input[type='submit'], [role='button']")
            for btn in buttons:
                try:
                    text = (await btn.inner_text()).strip().lower()
                    if any(word in text for word in allowed_words):
                        if not allow_submit and any(w in text for w in ["submit", "finish", "send application"]):
                            continue
                        visible = await btn.is_visible()
                        if visible and not await btn.evaluate("el => el.disabled"):
                            await btn.click()
                            logger.info("Clicked button by text", text=text)
                            await self.page.wait_for_timeout(1000)
                            return True
                except Exception:
                    continue
        except Exception:
            pass

        return False