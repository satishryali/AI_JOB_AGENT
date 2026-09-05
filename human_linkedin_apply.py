"""Human-like LinkedIn job application script.

This script mimics a real human applying to a LinkedIn job by:
1. Opening a visible browser (not headless)
2. Navigating to LinkedIn, searching for a job
3. Browsing results naturally with realistic pauses
4. Applying to a job with human-like interactions
"""

import asyncio
import random
import time
from pathlib import Path

from src.config.config_loader import get_settings
from src.config.logging import setup_logging, get_logger
from src.browser.manager import get_browser_manager
from src.config.settings import Settings

logger = get_logger(__name__)

# Track for debugging
SCREENSHOT_DIR = Path("data/screenshots")


async def take_screenshot(page, name: str) -> None:
    """Take a screenshot for debugging."""
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOT_DIR / f"{name}_{int(time.time())}.png"
    try:
        await page.screenshot(path=str(path), full_page=True)
        logger.info(f"Screenshot saved: {path}")
    except Exception as e:
        logger.warning(f"Failed to take screenshot: {e}")


async def human_delay(min_seconds: float = 0.8, max_seconds: float = 2.5):
    """Simulate human delay between actions."""
    delay = random.uniform(min_seconds, max_seconds)
    await asyncio.sleep(delay)


async def human_type(page, selector: str, text: str):
    """Type text into an input like a human (with realistic typing speed)."""
    element = await page.query_selector(selector)
    if not element:
        return False
    
    await element.click()
    await human_delay(0.3, 0.8)
    
    # Clear existing text
    await element.fill("")
    
    # Type character by character with variable speed
    for char in text:
        await element.type(char)
        # Variable typing speed (30-80ms per character, slower on punctuation)
        delay = random.uniform(0.03, 0.08)
        if char in ".,@_+-":
            delay = random.uniform(0.08, 0.15)
        await asyncio.sleep(delay)
    
    return True


async def human_scroll(page, pixels: int):
    """Scroll the page like a human (multiple small scrolls)."""
    steps = max(2, pixels // 200)
    for _ in range(steps):
        await page.mouse.wheel(0, random.randint(100, 300))
        await human_delay(0.2, 0.6)


async def login_to_linkedin(page, settings: Settings):
    """Log in to LinkedIn with human-like behavior."""
    logger.info("Navigating to LinkedIn login page...")
    await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
    await human_delay(2, 4)
    
    # Take screenshot at login page
    await take_screenshot(page, "login_page")
    
    # Check current URL to see where we ended up
    current_url = page.url
    logger.info(f"Current URL after navigation: {current_url}")
    
    # Check if we're on a page that requires login
    if "login" in current_url:
        # We're on the login page
        logger.info("On LinkedIn login page")
        
        # Get credentials from settings
        username = settings.linkedin.username
        password = settings.linkedin.password
        
        if not username or not password:
            logger.error("LinkedIn credentials not set in .env file (LINKEDIN_USERNAME, LINKEDIN_PASSWORD)")
            return False
        
        logger.info("Typing username...")
        await human_type(page, "#username", username)
        await human_delay(0.5, 1.2)
        
        logger.info("Typing password...")
        await human_type(page, "#password", password)
        await human_delay(0.5, 1.0)
        
        logger.info("Clicking Sign In button...")
        # Try to find and click the visible sign-in button
        sign_in_btn = await page.query_selector("button[type='submit']")
        if sign_in_btn:
            try:
                is_visible = await sign_in_btn.is_visible()
                if is_visible:
                    await sign_in_btn.click()
                    logger.info("Clicked sign-in button")
                else:
                    logger.info("Sign-in button not visible, pressing Enter key")
                    await page.keyboard.press("Enter")
            except Exception:
                await page.keyboard.press("Enter")
        else:
            # Try to find button by text
            buttons = await page.query_selector_all("button")
            clicked = False
            for btn in buttons:
                try:
                    text = (await btn.inner_text()).strip().lower()
                    await btn.scroll_into_view_if_needed()
                    if "sign" in text and "in" in text:
                        is_visible = await btn.is_visible()
                        if is_visible:
                            await btn.click()
                            clicked = True
                            logger.info("Clicked sign-in button by text")
                            break
                except Exception:
                    continue
            if not clicked:
                logger.info("No visible sign-in button, pressing Enter key")
                await page.keyboard.press("Enter")
        
        # Wait for page to load after login
        logger.info("Waiting for login to process...")
        await page.wait_for_timeout(5000)
        await human_delay(3, 6)
        
        # Take screenshot after login attempt
        await take_screenshot(page, "after_login_attempt")
        
        # Check if we hit a security checkpoint
        if "checkpoint" in page.url:
            logger.warning("!! LinkedIn security checkpoint detected !!")
            logger.warning("You may need to solve the CAPTCHA manually in the browser window.")
            logger.warning("Waiting 60 seconds for manual verification...")
            await page.wait_for_timeout(60000)
            
            # Check again
            await human_delay(2, 3)
            if "checkpoint" in page.url:
                logger.error("Security checkpoint not resolved automatically")
                return False
        
        logger.info("Login successful!")
    elif "checkpoint" in current_url:
        logger.warning("Security checkpoint encountered")
        # Wait for manual resolution
        logger.warning("Please resolve the CAPTCHA in the browser window within 60 seconds...")
        await page.wait_for_timeout(60000)
    else:
        logger.info(f"Already logged in or session active (URL: {current_url})")
    
    return True


async def search_for_jobs(page):
    """Search for jobs on LinkedIn with human-like behavior."""
    logger.info("Navigating to LinkedIn Jobs Search...")
    
    # Go directly to search URL with Python Developer jobs
    search_url = "https://www.linkedin.com/jobs/search/?keywords=Python%20Developer&location=India&f_TPR=r604800&f_E=2&f_JT=F"
    await page.goto(search_url, wait_until="domcontentloaded")
    await human_delay(3, 5)
    
    # Take screenshot of search results
    await take_screenshot(page, "job_search_results")
    
    # Wait for job cards to load
    try:
        await page.wait_for_selector(".job-card-container", timeout=15000)
        logger.info("Job cards loaded successfully")
    except Exception as e:
        logger.warning(f"Standard job card selector not found: {e}")
        # Try alternative selectors
        try:
            await page.wait_for_selector(".scaffold-layout__list-item", timeout=10000)
            logger.info("Alternative job card selector found")
        except Exception as e2:
            logger.error(f"No job cards found at all: {e2}")
            await take_screenshot(page, "no_jobs_found")
            return False
    
    # Scroll through results like a human browsing
    logger.info("Browsing job results...")
    await human_scroll(page, 800)
    await human_delay(2, 4)
    await human_scroll(page, 400)
    
    logger.info("Search completed")
    return True


async def browse_and_select_job(page) -> str | None:
    """Browse through jobs and select one to apply to."""
    logger.info("Looking at job results...")
    
    # Get all job cards
    job_cards = await page.query_selector_all(".job-card-container, .scaffold-layout__list-item")
    
    if not job_cards:
        logger.info("No job cards found with standard selectors, trying alternatives...")
        job_cards = await page.query_selector_all("[data-entity-urn*='jobPosting']")
    
    if not job_cards:
        logger.warning("No job results found")
        await take_screenshot(page, "no_job_cards")
        return None
    
    logger.info(f"Found {len(job_cards)} job listings")
    
    # Print some job info for debugging
    for i in range(min(3, len(job_cards))):
        try:
            title_el = await job_cards[i].query_selector(".job-card-list__title, .job-card-container__link")
            if title_el:
                title = (await title_el.inner_text()).strip()
                logger.info(f"Job {i+1}: {title}")
        except Exception:
            pass
    
    # Pick a job to click on (let's pick the first one that has visible content)
    job_index = 0
    selected_url = None
    
    for idx in range(min(len(job_cards), 5)):
        try:
            await job_cards[idx].click()
            await human_delay(2, 3)
            
            # Check if we can get the URL
            job_link = await job_cards[idx].query_selector("a")
            if job_link:
                href = await job_link.get_attribute("href")
                if href:
                    if href.startswith("/"):
                        selected_url = f"https://www.linkedin.com{href}"
                    else:
                        selected_url = href
                    
                    # Verify the job detail panel loaded
                    detail_panel = await page.query_selector(".jobs-search__job-details--container")
                    if detail_panel:
                        logger.info(f"Selected job #{idx + 1}: {selected_url}")
                        return selected_url
        except Exception as e:
            logger.warning(f"Failed to select job {idx+1}: {e}")
            continue
    
    if selected_url:
        logger.info(f"Selected job: {selected_url}")
        return selected_url
    
    logger.warning("Could not find a job with detailed panel")
    return page.url


async def apply_to_job(page, job_url: str):
    """Apply to a job on LinkedIn with human-like behavior."""
    logger.info(f"Opening job: {job_url}")
    
    # Navigate to job if not already there
    if job_url and job_url != page.url:
        await page.goto(job_url, wait_until="domcontentloaded")
        await human_delay(3, 5)
    
    # Take screenshot of the job page
    await take_screenshot(page, "job_page")
    
    # Scroll to see the job details
    await human_scroll(page, 500)
    await human_delay(1, 2)
    
    # Look for the apply button with many different selectors
    logger.info("Looking for apply button...")
    apply_button = None
    
    # Try multiple selectors - expanded list
    selectors = [
        # LinkedIn specific
        "button.jobs-apply-button",
        "button[aria-label*='Apply']",
        "button[aria-label*='Easy Apply']",
        "button[data-control-name*='apply']",
        "button[data-tracking-control-name*='apply']",
        ".jobs-apply-button",
        ".jobs-apply-button--primary",
        # Generic text-based
        "button:has-text('Apply')",
        "button:has-text('Easy Apply')",
        "button:has-text('apply')",
        "button:has-text('easy apply')",
        # Ancestor-based
        ".jobs-apply-button__wrapper > button",
        "[data-test-job-apply-btn]",
        "[data-easy-apply-button]",
        # By role
        "[role='button']:has-text('Apply')",
        "[role='button']:has-text('Easy Apply')",
        # Other possibilities
        "button[id*='apply']",
        "button[class*='apply']",
        "a[class*='apply']",
        "button[data-control-name='jobdetails_topcard_inapply']",
        "button[data-control-name='jobdetails_topcard_inapply']",
    ]
    
    for selector in selectors:
        try:
            btn = await page.query_selector(selector)
            if btn:
                # Check if visible
                is_visible = await btn.is_visible()
                if is_visible:
                    apply_button = btn
                    logger.info(f"Found apply button with selector: {selector}")
                    break
        except Exception:
            continue
    
    if not apply_button:
        # Take a screenshot and analyze
        await take_screenshot(page, "no_apply_button")
        
        # Check if already applied
        applied_check = await page.query_selector(
            "button[disabled*='Applied'], span[aria-label='Applied'], button:has-text('Applied')"
        )
        if applied_check:
            logger.info("Already applied to this job!")
            return False
        
        # Check what's on the page
        try:
            body_text = await page.inner_text("body")
            if "Applied" in body_text[:1000]:
                logger.info("Page shows 'Applied' - already applied to this job")
                return False
            if "Sign in" in body_text[:500] or "login" in body_text[:500]:
                logger.info("Page requires login - session may have expired")
        except Exception:
            pass
        
        # Try clicking on the job details area first if the apply button is below fold
        logger.info("Apply button not found in initial search, trying to scroll to top of page...")
        await page.evaluate("window.scrollTo(0, 0)")
        await human_delay(1, 2)
        
        # Try again with more selectors
        for selector in [
            "button:has-text('Apply')",
            "button:has-text('Easy Apply')",
            ".jobs-details__main-content button[type='button']",
            ".job-details-jobs-unified-top-card__button-container button",
            "[data-control-name='jobdetails_topcard_inapply']",
        ]:
            try:
                btns = await page.query_selector_all(selector)
                for btn in btns:
                    if await btn.is_visible():
                        text = await btn.inner_text()
                        if "appl" in text.lower():
                            apply_button = btn
                            logger.info(f"Found apply button (2nd attempt): {selector} -> {text.strip()}")
                            break
                if apply_button:
                    break
            except Exception:
                continue
        
        if not apply_button:
            logger.warning("Could not find apply button - job may not be accepting applications")
            return False
    
    # Human behavior - pause and think before clicking apply
    logger.info("Pausing before clicking apply (like a human reviewing the job)...")
    await human_delay(3, 6)
    
    # Read job description briefly
    desc_element = await page.query_selector(".jobs-description__content, .jobs-box__html-content")
    if desc_element:
        desc_text = await desc_element.inner_text()
        if desc_text:
            # Just look at first bit like a human skimming
            first_100 = desc_text[:100].strip()
            logger.info(f"Job description preview: {first_100}...")
    
    logger.info("Clicking Apply button...")
    await apply_button.click()
    await human_delay(3, 5)
    
    # Check if a form opened or we were redirected
    await take_screenshot(page, "after_apply_click")
    
    return True


async def handle_application_form(page):
    """Handle the LinkedIn Easy Apply form with human-like behavior."""
    logger.info("Checking if application form opened...")
    await human_delay(2, 3)
    
    # Take screenshot of form
    await take_screenshot(page, "application_form")
    
    # Check for Easy Apply modal or form
    modal = await page.query_selector(
        ".jobs-easy-apply-modal, div[role='dialog'], form[data-easy-apply-form]"
    )
    
    if not modal:
        # Check if we have a form at all
        forms = await page.query_selector_all("form")
        if forms:
            logger.info("Found forms on page")
            modal = forms[0] if len(forms) > 0 else None
        
        # Check if we got redirected
        await human_delay(2, 3)
        if "linkedin.com" not in page.url:
            logger.info(f"Redirected to external site: {page.url}")
            await take_screenshot(page, "external_site")
            logger.info("External application - will need manual handling")
            return "external"
    
    if not modal:
        logger.info("No application form found - may need manual handling")
        return "no_form"
    
    logger.info("Application form opened! Filling details with human-like behavior...")
    
    # Go through the application form pages
    max_steps = 10
    
    # List of likely selectors for form navigations
    next_buttons = [
        "button:has-text('Next')",
        "button:has-text('next')",
        "button[aria-label*='Continue']",
        "button[aria-label*='Next']",
        "button[aria-label*='Submit']",
        "button:has-text('Continue')",
        "button:has-text('Review')",
        "button:has-text('Submit')",
        "button[data-control-name*='continue']",
        "button[data-control-name*='next']",
        "button[data-control-name*='submit']",
        "button:has-text('Review your application')",
        "button:has-text('Submit application')",
        "button:has-text('Done')",
        ".artdeco-button--primary:has-text('Next')",
        ".artdeco-button--primary:has-text('Continue')",
        ".artdeco-button--primary:has-text('Submit')",
        ".artdeco-button--primary:has-text('Review')",
    ]
    
    for step in range(max_steps):
        logger.info(f"--- Application step {step + 1} ---")
        
        # Take screenshot at each step
        await take_screenshot(page, f"form_step_{step + 1}")
        
        # Fill text inputs with adaptive approach
        text_inputs = await page.query_selector_all("input[type='text'], input[type='email'], input[type='tel'], textarea")
        if text_inputs:
            for input_el in text_inputs:
                try:
                    # Get label/name/placeholder info
                    info = await input_el.evaluate("""el => {
                        let label = '';
                        let placeholder = el.placeholder || '';
                        let name = el.name || '';
                        let id = el.id || '';
                        
                        // Find associated label
                        if (el.id) {
                            const lbl = document.querySelector(`label[for="${el.id}"]`);
                            if (lbl) label = lbl.textContent.trim();
                        }
                        
                        // Check closest label element
                        if (!label) {
                            const parent = el.closest('.fb-dash-form-element, .jobs-easy-apply-form-element');
                            if (parent) {
                                const lbl = parent.querySelector('label');
                                if (lbl) label = lbl.textContent.trim();
                            }
                        }
                        
                        return {label, placeholder, name, id};
                    }""")
                    
                    label_text = f"{info['label']} {info['placeholder']} {info['name']}".lower()
                    
                    # Skip if field is already filled
                    current_value = await input_el.input_value()
                    if current_value:
                        continue
                    
                    # Determine what to fill
                    if "phone" in label_text:
                        await human_type(page, f"#{info['id']}" if info['id'] else f"input[name='{info['name']}']", "+919182595928")
                        await human_delay(0.3, 0.7)
                    elif "email" in label_text:
                        await human_type(page, f"#{info['id']}" if info['id'] else f"input[name='{info['name']}']", "satishryali252@gmail.com")
                        await human_delay(0.3, 0.7)
                    elif "first" in label_text:
                        await human_type(page, f"#{info['id']}" if info['id'] else f"input[name='{info['name']}']", "Satyanarayana")
                        await human_delay(0.3, 0.7)
                    elif "last" in label_text:
                        await human_type(page, f"#{info['id']}" if info['id'] else f"input[name='{info['name']}']", "Ryali")
                        await human_delay(0.3, 0.7)
                    elif "city" in label_text:
                        await human_type(page, f"#{info['id']}" if info['id'] else f"input[name='{info['name']}']", "Hyderabad")
                        await human_delay(0.3, 0.7)
                    elif "experience" in label_text and "years" in label_text:
                        await human_type(page, f"#{info['id']}" if info['id'] else f"input[name='{info['name']}']", "4 years")
                        await human_delay(0.3, 0.7)
                except Exception as e:
                    logger.debug(f"Failed to fill text input: {e}")
                    continue
        
        # Handle select dropdowns
        selects = await page.query_selector_all("select")
        if selects:
            for select_el in selects:
                try:
                    # Get select info
                    info = await select_el.evaluate("""el => {
                        let label = '';
                        let name = el.name || '';
                        
                        if (el.id) {
                            const lbl = document.querySelector(`label[for="${el.id}"]`);
                            if (lbl) label = lbl.textContent.trim();
                        }
                        
                        const parent = el.closest('.fb-dash-form-element');
                        if (parent) {
                            const lbl = parent.querySelector('label');
                            if (lbl) label = lbl.textContent.trim();
                        }
                        
                        // Get options
                        const options = Array.from(el.options).map(o => ({text: o.text, value: o.value}));
                        return {label, name, options};
                    }""")
                    
                    label_text = f"{info['label']} {info['name']}".lower()
                    options = info['options']
                    
                    # Try to select based on label
                    selected = False
                    if "experience" in label_text:
                        for opt in options:
                            if "4" in opt['text'] or "4" in opt['value']:
                                await select_el.select_option(value=opt['value'])
                                selected = True
                                break
                    elif "country" in label_text:
                        for opt in options:
                            if "india" in opt['text'].lower() or "in" in opt['value'].lower():
                                await select_el.select_option(value=opt['value'])
                                selected = True
                                break
                    elif "state" in label_text or "province" in label_text:
                        # Try Telangana or Andhra Pradesh
                        for opt in options:
                            if "telangana" in opt['text'].lower() or "andhra" in opt['text'].lower():
                                await select_el.select_option(value=opt['value'])
                                selected = True
                                break
                    elif "authorization" in label_text or "sponsorship" in label_text:
                        for opt in options:
                            text_lower = opt['text'].lower()
                            if "yes" in text_lower or "authorized" in text_lower or "eligible" in text_lower:
                                await select_el.select_option(value=opt['value'])
                                selected = True
                                break
                    elif "degree" in label_text or "education" in label_text:
                        for opt in options:
                            if "bachelor" in opt['text'].lower() or "b.tech" in opt['text'].lower() or "master" in opt['text'].lower():
                                await select_el.select_option(value=opt['value'])
                                selected = True
                                break
                    
                    if selected:
                        await human_delay(0.2, 0.5)
                except Exception as e:
                    logger.debug(f"Failed to handle select: {e}")
                    continue
        
        # Handle radio buttons
        radios = await page.query_selector_all("input[type='radio']")
        if radios:
            for radio in radios:
                try:
                    radio_info = await radio.evaluate("""el => {
                        return {
                            value: el.value || '',
                            name: el.name || '',
                            id: el.id || '',
                            label: el.closest('label') ? el.closest('label').textContent.trim() : ''
                        };
                    }""")
                    
                    label_text = f"{radio_info['label']} {radio_info['value']}".lower()
                    currently_checked = await radio.is_checked()
                    
                    # Select "Yes" for most questions
                    if not currently_checked:
                        if "yes" in label_text or "true" in label_text or "1" in label_text:
                            # Check if it's a sensible "Yes" to select
                            if "authorized" in label_text or "right to work" in label_text or \
                               "sponsor" in label_text or "experience" in label_text or \
                               "relocate" in label_text or "willing" in label_text or \
                               "work" in label_text:
                                await radio.check(force=True)
                                await human_delay(0.2, 0.5)
                except Exception:
                    continue
        
        # Handle checkboxes
        checkboxes = await page.query_selector_all("input[type='checkbox']")
        if checkboxes:
            for checkbox in checkboxes:
                try:
                    label = await checkbox.evaluate("el => el.closest('label') ? el.closest('label').textContent.trim() : ''")
                    checked = await checkbox.is_checked()
                    label_lower = label.lower()
                    
                    # Check consent/agreement boxes but not newsletter subscriptions
                    if not checked:
                        if "agree" in label_lower or "consent" in label_lower or "authorize" in label_lower:
                            await checkbox.check(force=True)
                            await human_delay(0.2, 0.5)
                        elif "subscri" not in label_lower and "newsletter" not in label_lower and "update" not in label_lower:
                            # Check other boxes by default
                            await checkbox.check(force=True)
                            await human_delay(0.2, 0.5)
                except Exception:
                    continue
        
        # Human pause before clicking next
        await human_delay(1, 3)
        
        # Look for Next / Review / Submit buttons
        next_clicked = False
        for selector in next_buttons:
            try:
                btn = await page.query_selector(selector)
                if btn:
                    is_visible = await btn.is_visible()
                    if is_visible:
                        # Human pause before clicking
                        await human_delay(0.5, 1.5)
                        await btn.click()
                        logger.info(f"Clicked button: {selector}")
                        next_clicked = True
                        # Wait for the form to update
                        await human_delay(2, 4)
                        break
            except Exception:
                continue
        
        if not next_clicked:
            # Try to find any button with common action words
            all_buttons = await page.query_selector_all("button")
            for btn in all_buttons:
                try:
                    text = (await btn.inner_text()).strip().lower()
                    if any(word in text for word in ["next", "continue", "submit", "review", "finish", "apply"]):
                        if await btn.is_visible() and not await btn.evaluate("el => el.disabled"):
                            await human_delay(0.5, 1.5)
                            await btn.click()
                            logger.info(f"Clicked button by text: {text}")
                            next_clicked = True
                            await human_delay(2, 4)
                            break
                except Exception:
                    continue
        
        if next_clicked:
            # Check if we're on the final step now
            continue
        
        # Check if we're done (submitted)
        success_msg = await page.query_selector(
            "text=Application submitted, text=Thank you, text=Your application has been"
        )
        if success_msg:
            logger.info("Application submitted successfully!")
            await take_screenshot(page, "application_submitted")
            return "submitted"
        
        # Check current step state
        try:
            step_text = await page.query_selector(".jobs-easy-apply-modal")
            if step_text:
                level_text = await page.inner_text(".jobs-easy-apply-modal")
                if "congratulations" in level_text.lower() or "submitted" in level_text.lower():
                    logger.info("Application submitted!")
                    return "submitted"
        except Exception:
            pass
        
        # No more buttons - either done or stuck
        logger.info(f"No more buttons found at step {step + 1}")
        break
    
    # After all steps, check for submission confirmation
    await human_delay(2, 4)
    
    # Final check
    try:
        body_text = await page.inner_text("body")
        if any(word in body_text.lower() for word in ["application submitted", "thank you for applying", "your application has been"]):
            logger.info("Application submitted successfully!")
            return "submitted"
    except Exception:
        pass
    
    # Take screenshot of final state
    await take_screenshot(page, "final_state")
    
    return "in_progress"


async def main():
    """Main execution flow."""
    print("=" * 60)
    print("AI JOB AGENT - HUMAN-LIKE LINKEDIN APPLICATION")
    print("=" * 60)
    print()
    
    # Load settings
    settings = get_settings()
    setup_logging(settings.logging)
    
    # Verify resume exists
    resume_path = settings.resume.path
    if not resume_path.exists():
        print(f"!! Resume not found at: {resume_path}")
        print("Please ensure your resume is at the correct location.")
        return
    
    print(f"[OK] Resume found at: {resume_path}")
    print()
    
    # Verify LinkedIn credentials are set
    if not settings.linkedin.username or not settings.linkedin.password:
        print("!! LinkedIn credentials not found in .env file.")
        print("   Please set LINKEDIN_USERNAME and LINKEDIN_PASSWORD in .env")
        return
    
    print(f"[OK] LinkedIn account configured for: {settings.linkedin.username}")
    print()
    
    # Get browser manager - with headless=False for visible browser
    print("Launching browser (visible mode - you'll see the browsing)...")
    browser = await get_browser_manager()
    
    await browser.launch()
    context = await browser.new_context()
    page = await context.new_page()
    
    # Step 1: Login
    print("\n" + "=" * 40)
    print("STEP 1: Logging in to LinkedIn")
    print("=" * 40)
    login_success = await login_to_linkedin(page, settings)
    if not login_success:
        print("!! Login failed - check credentials and try again")
        await browser.close()
        return
    print("[OK] Login completed")
    
    # Step 2: Search for jobs
    print("\n" + "=" * 40)
    print("STEP 2: Searching for jobs")
    print("=" * 40)
    search_ok = await search_for_jobs(page)
    if not search_ok:
        print("!! Could not load job search results")
        await browser.close()
        return
    print("[OK] Search completed")
    
    # Step 3: Browse and select a job
    print("\n" + "=" * 40)
    print("STEP 3: Browsing job listings")
    print("=" * 40)
    job_url = await browse_and_select_job(page)
    if not job_url:
        print("!! Could not find jobs to apply to")
        await browser.close()
        return
    print(f"[OK] Selected job: {job_url}")
    
    # Step 4: Apply to the job
    print("\n" + "=" * 40)
    print("STEP 4: Applying to job")
    print("=" * 40)
    can_apply = await apply_to_job(page, job_url)
    
    if not can_apply:
        print("!! Could not apply (already applied or no apply button)")
        await browser.close()
        return
    
    # Step 5: Fill application form
    print("\n" + "=" * 40)
    print("STEP 5: Filling application form")
    print("=" * 40)
    result = await handle_application_form(page)
    
    print()
    print("=" * 60)
    if result == "submitted":
        print("[SUCCESS] APPLICATION SUBMITTED SUCCESSFULLY!")
    elif result == "external":
        print("[WARNING] Redirected to external application site.")
        print("   The browser window is open - please complete manually.")
    elif result == "in_progress":
        print("[WARNING] Application form partially filled.")
        print("   Please check the browser window and complete manually if needed.")
    else:
        print("[INFO] No application form found to fill.")
    print("=" * 60)
    
    # Keep browser open so user can see/interact if needed
    print()
    print("The browser will stay open for 180 seconds so you can review.")
    print("Press Ctrl+C to close it earlier if needed.")
    
    try:
        # Keep browser open for review
        await asyncio.sleep(180)
    except KeyboardInterrupt:
        logger.info("Session interrupted by user")
    finally:
        await browser.close()
        print("\n[OK] Browser closed")
        print("Done!")


if __name__ == "__main__":
    asyncio.run(main())