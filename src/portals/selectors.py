"""Centralized selector registry for all portals and ATS platforms."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PortalSelectors:
    """Contains all CSS selectors needed for a portal/ATS."""

    # Login selectors
    login_url: str = ""
    username_field: str = ""
    password_field: str = ""
    login_button: str = ""
    login_error: str = ""

    # Search selectors
    search_url_template: str = ""
    search_input: str = ""
    location_input: str = ""
    search_button: str = ""
    job_card_container: str = ""
    job_card: str = ""
    job_title: str = ""
    job_company: str = ""
    job_location: str = ""
    job_link: str = ""

    # Job detail selectors
    job_detail_container: str = ""
    job_description: str = ""
    job_salary: str = ""
    job_experience: str = ""
    job_employment_type: str = ""
    job_posted_date: str = ""
    job_skills: str = ""

    # Apply selectors
    apply_button: str = ""
    easy_apply_button: str = ""
    not_easy_apply_indicator: str = ""
    external_apply_indicator: str = ""

    # Form selectors
    form_container: str = ""
    next_button: str = ""
    submit_button: str = ""
    review_button: str = ""
    success_message: str = ""
    error_message: str = ""

    # Misc
    captcha_indicator: str = ""
    logout_button: str = ""
    logged_in_indicator: str = ""

    # Additional custom selectors
    custom: dict[str, Any] = field(default_factory=dict)


# ==============================================================================
# JOB PORTAL SELECTORS
# ==============================================================================

LINKEDIN_SELECTORS = PortalSelectors(
    login_url="https://www.linkedin.com/login",
    username_field="#username",
    password_field="#password",
    login_button="button[type='submit']",
    login_error=".error, .alert-error",
    logged_in_indicator=".global-nav__me, .nav-item, [data-control-name='identity_welcome_message']",
    search_url_template="https://www.linkedin.com/jobs/search?keywords={keyword}&location={location}&f_TPR=r{days}",
    job_card_container=".jobs-search-results-list",
    job_card=".job-card-container",
    job_title=".job-card-list__title",
    job_company=".job-card-container__company-name",
    job_location=".job-card-container__metadata-item",
    job_detail_container=".jobs-search__job-details--container",
    job_description=".jobs-description__content",
    apply_button="button.jobs-apply-button, button[aria-label*='Apply']",
    easy_apply_button=".jobs-apply-button",
    not_easy_apply_indicator="[class*='external'], [class*='redirect'], a[href*='http']",
    form_container=".jobs-easy-apply-modal",
    next_button="button[aria-label*='Next'], button[aria-label*='Continue']",
    submit_button="button[aria-label*='Submit']",
    success_message="text=Congratulations, text=Application submitted",
    captcha_indicator="iframe[src*='captcha'], [class*='captcha']",
)

NAUKRI_SELECTORS = PortalSelectors(
    login_url="https://www.naukri.com/nlogin/login",
    username_field="input[name='usernameField']",
    password_field="input[name='passwordField']",
    login_button="button[type='submit']",
    login_error=".error-msg, .notification-error, [data-walkout='errorMessage']",
    logged_in_indicator=".ni-gnb-icn, [data-test-id='gnb-profile']",
    search_url_template="https://www.naukri.com/{keyword}-jobs-in-{location}?days={days}",
    search_input="input[placeholder*='Enter skills'], .suggestor-input",
    location_input="input[placeholder*='Enter location'], .suggestor-input + input",
    search_button="button[type='submit'], .qsbSubmit",
    job_card_container=".listContainer, .results",
    job_card=".jobTuple, .cust-job-tuple, article.jobTuple",
    job_title=".title, .job-title-heading, a.title",
    job_company=".sub-title, .company-name, a.sub-title",
    job_location=".location, .loc, [class*='location']",
    job_link="a.title, a[href*='/job-listings']",
    job_detail_container=".details, .job-details",
    job_description=".job-description, .jd, [class*='description']",
    job_salary=".salary, [class*='salary']",
    job_experience=".experience, [class*='exp']",
    job_employment_type=".job-type, [class*='type']",
    apply_button="button.apply-button, button[data-qa='applyButton'], button[type='button']:has-text('Apply')",
    easy_apply_button="button:has-text('Apply')",
    not_easy_apply_indicator=".external, [class*='redirect']",
    form_container=".form, .apply-form",
    next_button="button:has-text('Next'), button:has-text('Continue')",
    submit_button="button[type='submit'], button:has-text('Submit')",
    success_message="text=Application submitted, text=Successfully applied",
    captcha_indicator="iframe[src*='captcha'], [class*='captcha']",
)

INDEED_SELECTORS = PortalSelectors(
    login_url="https://secure.indeed.com/auth",
    username_field="input[name='email'], input[name='username']",
    password_field="input[name='password']",
    login_button="button[type='submit'], button:has-text('Sign in')",
    login_error=".error, .invalid-input",
    logged_in_indicator=".desktop-header-account, [data-gnav-element-name='Account']",
    search_url_template="https://{domain}/jobs?q={keyword}&l={location}&fromage={days}",
    search_input="input[name='q'], input[aria-label*='search']",
    location_input="input[name='l'], input[aria-label*='location']",
    search_button="button[type='submit'], .yosegi-InlineWhatWhere-primaryButton",
    job_card_container=".jobsearch-ResultsList, #mosaic-provider-jobcards",
    job_card=".jobsearch-ResultsList li, .result, .job_seen_beacon",
    job_title=".jcs-JobTitle, .jobTitle, h2 > a",
    job_company=".companyName, .company, [data-testid='company-name']",
    job_location=".companyLocation, .location",
    job_link=".jcs-JobTitle, a[href*='/rc/clk'], h2 > a",
    job_detail_container="#jobsearch-ViewjobPaneWrapper, .jobsearch-JobComponent",
    job_description="#jobDescriptionText, .jobsearch-jobDescriptionText",
    job_salary=".salary-snippet-container, [data-testid='attribute_snippet_testid']",
    job_experience="[data-testid*='experience'], .jobsearch-JobMetadataHeader-item",
    apply_button="#applyButtonLink, button#apply-button, a[data-testid*='Apply']",
    easy_apply_button="button#apply-button",
    not_easy_apply_indicator="#applyButtonLink[href*='http'], [class*='external']",
    form_container=".jobsearch-ApplyForm, form",
    next_button="button:has-text('Next'), button:has-text('Continue')",
    submit_button="button[type='submit'], button:has-text('Submit')",
    success_message="text=Application submitted, text=Your application",
    captcha_indicator="iframe[src*='captcha'], [class*='captcha']",
)

FOUNDIT_SELECTORS = PortalSelectors(
    login_url="https://www.foundit.in/login",
    username_field="input[name='email'], input[name='username'], input[type='email']",
    password_field="input[name='password'], input[type='password']",
    login_button="button[type='submit'], button:has-text('Login')",
    login_error=".error, .error-message",
    logged_in_indicator=".user-profile, [class*='profile']",
    search_url_template="https://www.foundit.in/srp/results?query={keyword}&locations={location}",
    search_input="input[placeholder*='job'], input[name='query']",
    location_input="input[placeholder*='location'], input[name='locations']",
    search_button="button[type='submit'], .search-btn",
    job_card_container=".job-list, .srp-card, .jobs",
    job_card=".srp-card, article.job-card, .job-card",
    job_title=".job-title, h3, .title",
    job_company=".company-name, .company, [class*='company']",
    job_location=".location, .loc, [class*='location']",
    job_link=".job-title a, a[href*='/job/'], h3 a",
    job_detail_container=".job-details, .job-description",
    job_description=".job-description, [class*='description']",
    job_salary=".salary, [class*='salary']",
    job_experience=".experience, [class*='exp']",
    apply_button="button:has-text('Apply'), button[data-qa='apply']",
    easy_apply_button="button:has-text('Easy Apply'), button:has-text('Quick Apply')",
    not_easy_apply_indicator="[class*='external'], [class*='redirect']",
    form_container="form, .application-form",
    next_button="button:has-text('Next'), button:has-text('Continue')",
    submit_button="button[type='submit'], button:has-text('Submit')",
    success_message="text=Application submitted, text=Applied successfully",
    captcha_indicator="iframe[src*='captcha'], [class*='captcha']",
)

WELLFOUND_SELECTORS = PortalSelectors(
    login_url="https://wellfound.com/login",
    username_field="input[name='email'], input[type='email']",
    password_field="input[name='password'], input[type='password']",
    login_button="button[type='submit'], button:has-text('Log in')",
    login_error=".error, [class*='error']",
    logged_in_indicator="[data-testid*='profile'], .profile-menu",
    search_url_template="https://wellfound.com/role/{keyword}/{location}",
    search_input="input[placeholder*='search'], input[name='query']",
    location_input="input[placeholder*='location'], [data-testid*='location']",
    search_button="button[type='submit'], .search-button",
    job_card_container=".section_jobs, [data-testid='job-cards']",
    job_card="[data-testid='job-card'], .job-card, article",
    job_title="[data-testid='job-title'], .job-title, h3",
    job_company="[data-testid='company-name'], .company-name",
    job_location="[data-testid='job-location'], .location",
    job_link="a[href^='/jobs/'], [data-testid*='job'] a",
    job_detail_container="[data-testid='job-posting'], .job-posting",
    job_description="[data-testid='job-description'], .job-description",
    job_salary="[data-testid*='salary'], .salary",
    apply_button="button:has-text('Apply'), .apply-button",
    easy_apply_button=".apply-now, button:has-text('Quick Apply')",
    not_easy_apply_indicator="[href*='http://'], [href*='https://'], [class*='external']",
    form_container="form, .application-form",
    next_button="button:has-text('Next'), button:has-text('Continue')",
    submit_button="button[type='submit'], button:has-text('Submit')",
    success_message="text=Applied, text=Application sent",
    captcha_indicator="iframe[src*='captcha'], [class*='captcha']",
)

GLASSDOOR_SELECTORS = PortalSelectors(
    login_url="https://www.glassdoor.com/auth/login",
    username_field="#email, input[name='email'], input[type='email']",
    password_field="#password, input[name='password'], input[type='password']",
    login_button="button[type='submit'], button:has-text('Sign In')",
    login_error=".error, .alert-error",
    logged_in_indicator="[data-testid='profile-menu'], .ProfileMenuButton",
    search_url_template="https://www.glassdoor.com/Job/{keyword}-jobs-{location}-SRCH_IL.0,{location_length}_KO0,{keyword_length}.htm?fromAge={days}",
    search_input="input[data-testid*='search'], input[placeholder*='job']",
    location_input="input[data-testid*='location'], input[placeholder*='location']",
    search_button="button[data-testid*='submit'], button[type='submit']",
    job_card_container="ul[data-testid='job-list'], .react-job-listing",
    job_card="li[data-testid='job-list-item'], .JobCard, article",
    job_title="a[data-testid*='job-title'], .job-title",
    job_company="[data-testid*='employer-name'], .employer-name",
    job_location="[data-testid*='location'], .location",
    job_link="a[data-testid*='job-title'], a[href*='/job-listing/']",
    job_detail_container="[data-testid*='job-detail'], .job-detail",
    job_description="[data-testid*='job-description'], .job-description",
    job_salary="[data-testid*='salary'], [class*='salary']",
    apply_button="button:has-text('Apply'), [data-testid*='apply']",
    easy_apply_button="button:has-text('Easy Apply')",
    not_easy_apply_indicator="[class*='external'], a[href^='http']:not([href*='glassdoor'])",
    form_container="form, .application-form",
    next_button="button:has-text('Next'), button:has-text('Continue')",
    submit_button="button[type='submit'], button:has-text('Submit')",
    success_message="text=Application sent, text=Applied successfully",
    captcha_indicator="iframe[src*='captcha'], [class*='captcha']",
)


# ==============================================================================
# ATS PLATFORM SELECTORS
# ==============================================================================

WORKDAY_SELECTORS = PortalSelectors(
    login_url="",
    search_url_template="",
    apply_button="[data-automation-id='applyButton'], button[data-testid*='apply'], [ph-tevent='job_postings_apply'], button:has-text('Apply')",
    job_title="[data-automation-id='jobPostingTitle'], h1, .css-113dhar",
    job_company="[data-automation-id='jobPostingCompany'], [data-automation-id*='company']",
    job_location="[data-automation-id='jobPostingLocation'], [data-automation-id*='location']",
    job_description="[data-automation-id='jobPostingDescription'], .css-1sxcgyk, [class*='job-description']",
    job_salary="[data-automation-id*='salary'], [class*='salary']",
    job_experience="[data-automation-id*='experience'], [class*='experience']",
    form_container="[data-automation-id='applicationForm'], form, .css-1sxcgyk",
    next_button="[data-automation-id='bottom-navigation-next-button'], button:has-text('Next'), button:has-text('Continue')",
    submit_button="[data-automation-id='submitApplicationBtn'], button[type='submit'], button:has-text('Submit')",
    review_button="[data-automation-id='bottom-navigation-review-button'], button:has-text('Review')",
    success_message="[data-automation-id='applicationSuccess'], text=Thank you for applying",
    error_message="[data-automation-id*='error'], .error, [class*='error']",
)

GREENHOUSE_SELECTORS = PortalSelectors(
    login_url="",
    search_url_template="",
    apply_button="button[data-job-id], a[href*='/jobs/'], a:has-text('Apply'), button:has-text('Apply')",
    job_title="[data-testid='job-title'], h1, .app-title",
    job_company=".company-name, [class*='company']",
    job_location="[data-testid='job-location'], .location, [class*='location']",
    job_description="[data-testid='job-description'], .job-description, #job-description",
    job_salary="[data-testid*='salary'], [class*='salary']",
    form_container="#application_form, form.application",
    next_button="button:has-text('Next'), button:has-text('Continue')",
    submit_button="button[type='submit'], button:has-text('Submit')",
    review_button="button:has-text('Review')",
    success_message="text=Your application has been submitted, .application-success",
    error_message="[class*='error'], .field-error, .error-message",
)

LEVER_SELECTORS = PortalSelectors(
    login_url="",
    search_url_template="",
    apply_button="a[href*='lever.co'], .posting-apply, [data-qa='posting-apply'], a:has-text('Apply')",
    job_title=".posting-headline, h1, .posting-title",
    job_company=".posting-company, [class*='company']",
    job_location=".posting-categories, .location, [class*='location']",
    job_description=".posting-description, [class*='description']",
    job_salary="[class*='salary'], .compensation",
    form_container="#application, form, .application-form",
    next_button="button:has-text('Next'), button:has-text('Continue')",
    submit_button="button[type='submit'], button:has-text('Submit')",
    review_button="button:has-text('Review')",
    success_message="text=Your application has been submitted, .confirmation",
    error_message="[class*='error'], .field-error",
)

ASHBY_SELECTORS = PortalSelectors(
    login_url="",
    search_url_template="",
    apply_button="a[href*='ashbyhq.com'], button:has-text('Apply'), a:has-text('Apply')",
    job_title="h1, .job-title, [data-testid*='title']",
    job_company="[class*='company'], .company",
    job_location="[class*='location'], .location",
    job_description="[class*='description'], #job-description",
    job_salary="[class*='salary'], .compensation",
    form_container="form, #application-form",
    next_button="button:has-text('Next'), button:has-text('Continue')",
    submit_button="button[type='submit'], button:has-text('Submit')",
    review_button="button:has-text('Review')",
    success_message="text=Application submitted, text=Thanks for applying",
    error_message="[class*='error'], .field-error",
)

SMARTRECRUITERS_SELECTORS = PortalSelectors(
    login_url="",
    search_url_template="",
    apply_button="[data-template='apply'], .job-apply-link, button:has-text('Apply'), a:has-text('Apply')",
    job_title=".job-title, h1, [class*='title']",
    job_company=".company-name, [class*='company']",
    job_location=".job-location, [class*='location']",
    job_description=".job-description, [class*='description']",
    job_salary="[class*='salary'], .compensation",
    form_container="form, .application-form",
    next_button="button:has-text('Next'), button:has-text('Continue')",
    submit_button="button[type='submit'], button:has-text('Submit')",
    review_button="button:has-text('Review')",
    success_message="text=Application submitted, text=Your application",
    error_message="[class*='error'], .field-error",
)

ICIMS_SELECTORS = PortalSelectors(
    login_url="",
    search_url_template="",
    apply_button="[data-automation-id*='apply'], button:has-text('Apply'), a:has-text('Apply')",
    job_title="[data-automation-id*='jobTitle'], h1",
    job_company="[data-automation-id*='company'], [class*='company']",
    job_location="[data-automation-id*='location'], [class*='location']",
    job_description="[data-automation-id*='description'], [class*='description']",
    job_salary="[data-automation-id*='salary'], [class*='salary']",
    form_container="form, [data-automation-id*='applicationForm']",
    next_button="[data-automation-id*='next'], button:has-text('Next')",
    submit_button="[data-automation-id*='submit'], button[type='submit']",
    review_button="[data-automation-id*='review'], button:has-text('Review')",
    success_message="text=Thank you for applying, text=Application submitted",
    error_message="[data-automation-id*='error'], [class*='error']",
)

TALEO_SELECTORS = PortalSelectors(
    login_url="",
    search_url_template="",
    apply_button="[data-target='apply'], button:has-text('Apply'), a:has-text('Apply')",
    job_title=".job-title, h1, [class*='title']",
    job_company="[class*='company'], .company",
    job_location="[class*='location'], .location",
    job_description=".job-description, [class*='description']",
    job_salary="[class*='salary'], .compensation",
    form_container="form, #application-form",
    next_button="button:has-text('Next'), button:has-text('Continue')",
    submit_button="button[type='submit'], button:has-text('Submit')",
    review_button="button:has-text('Review')",
    success_message="text=Thank you for applying, text=Application submitted",
    error_message="[class*='error'], .field-error",
)

SUCCESSFACTORS_SELECTORS = PortalSelectors(
    login_url="",
    search_url_template="",
    apply_button="[data-automation-id*='apply'], button:has-text('Apply'), a:has-text('Apply')",
    job_title="[data-automation-id*='title'], h1, .job-title",
    job_company="[data-automation-id*='company'], [class*='company']",
    job_location="[data-automation-id*='location'], [class*='location']",
    job_description="[data-automation-id*='description'], [class*='description']",
    job_salary="[data-automation-id*='salary'], [class*='salary']",
    form_container="form, [data-automation-id*='applicationForm']",
    next_button="[data-automation-id*='next'], button:has-text('Next')",
    submit_button="[data-automation-id*='submit'], button[type='submit']",
    review_button="[data-automation-id*='review'], button:has-text('Review')",
    success_message="text=Thank you for applying, text=Application submitted",
    error_message="[data-automation-id*='error'], [class*='error']",
)

BAMBOO_SELECTORS = PortalSelectors(
    login_url="",
    search_url_template="",
    apply_button="[data-automation-id*='apply'], button:has-text('Apply'), a:has-text('Apply')",
    job_title="[class*='job-title'], h1, [data-automation-id*='title']",
    job_company="[class*='company'], [data-automation-id*='company']",
    job_location="[class*='location'], [data-automation-id*='location']",
    job_description="[class*='description'], [data-automation-id*='description']",
    job_salary="[class*='salary'], .compensation",
    form_container="form, [data-automation-id*='applicationForm']",
    next_button="[data-automation-id*='next'], button:has-text('Next')",
    submit_button="[data-automation-id*='submit'], button[type='submit']",
    review_button="[data-automation-id*='review'], button:has-text('Review')",
    success_message="text=Thank you for applying, text=Application submitted",
    error_message="[data-automation-id*='error'], [class*='error']",
)

JOBVITE_SELECTORS = PortalSelectors(
    login_url="",
    search_url_template="",
    apply_button="[data-jobvite-id], button:has-text('Apply'), a:has-text('Apply')",
    job_title=".job-title, h1, [class*='title']",
    job_company="[class*='company'], .company",
    job_location="[class*='location'], .location",
    job_description=".job-description, [class*='description']",
    job_salary="[class*='salary'], .compensation",
    form_container="form, .application-form, #application",
    next_button="button:has-text('Next'), button:has-text('Continue')",
    submit_button="button[type='submit'], button:has-text('Submit')",
    review_button="button:has-text('Review')",
    success_message="text=Thank you for applying, text=Application submitted",
    error_message="[class*='error'], .field-error",
)


# ==============================================================================
# REGISTRY
# ==============================================================================

PORTAL_SELECTORS: dict[str, PortalSelectors] = {
    "linkedin": LINKEDIN_SELECTORS,
    "naukri": NAUKRI_SELECTORS,
    "indeed": INDEED_SELECTORS,
    "foundit": FOUNDIT_SELECTORS,
    "wellfound": WELLFOUND_SELECTORS,
    "glassdoor": GLASSDOOR_SELECTORS,
    "workday": WORKDAY_SELECTORS,
    "greenhouse": GREENHOUSE_SELECTORS,
    "lever": LEVER_SELECTORS,
    "ashby": ASHBY_SELECTORS,
    "smartrecruiters": SMARTRECRUITERS_SELECTORS,
    "icims": ICIMS_SELECTORS,
    "taleo": TALEO_SELECTORS,
    "successfactors": SUCCESSFACTORS_SELECTORS,
    "bamboohr": BAMBOO_SELECTORS,
    "jobvite": JOBVITE_SELECTORS,
}


def get_selectors(platform: str) -> PortalSelectors:
    """Get selectors for a platform."""
    return PORTAL_SELECTORS.get(platform.lower(), PortalSelectors())