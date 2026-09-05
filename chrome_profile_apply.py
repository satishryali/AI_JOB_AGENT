"""Apply to LinkedIn job using existing Chrome profile (no login needed).

This script:
1. Launches Chrome with the user's profile using remote debugging
2. Connects via CDP
3. Navigates to LinkedIn jobs
4. Finds and applies to a job using the already-logged-in session
"""

import asyncio
import json
import random
import subprocess
import time
import os
from pathlib import Path

from playwright.async_api import async_playwright

# Configuration
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
# Use the actual Satish Ryali profile from user's Chrome
USER_DATA_DIR = r"C:\Users\ganes\AppData\Local\Google\Chrome\User Data"
PROFILE_DIRECTORY = "Default"
DEBUG_PORT = 9222
DEBUG_HOST = "127.0.0.1"

# Screenshot directory
SCREENSHOT_DIR = Path("data/screenshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


async def human_delay(min_seconds: float = 0.8, max_seconds: float = 2.5):
    """Simulate human delay between actions."""
    delay = random.uniform(min_seconds, max_seconds)
    await asyncio.sleep(delay)


async def human_type(page, element, text: str):
    """Type text into an input like a human."""
    await element.click()
    await human_delay(0.3, 0.8)
    
    # Clear existing text
    await element.fill("")
    
    # Type with variable speed
    for char in text:
        await element.type(char)
        delay = random.uniform(0.03, 0.08)
        if char in ".,@_+-":
            delay = random.uniform(0.08, 0.15)
        await asyncio.sleep(delay)
    
    return True


async def human_scroll(page, pixels: int):
    """Scroll the page like a human."""
    steps = max(2, pixels // 200)
    for _ in range(steps):
        await page.mouse.wheel(0, random.randint(100, 300))
        await human_delay(0.2, 0.6)


async def take_screenshot(page, name: str):
    """Take a screenshot for debugging."""
    path = SCREENSHOT_DIR / f"{name}_{int(time.time())}.png"
    try:
        await page.screenshot(path=str(path))
        print(f"[SCREENSHOT] Saved: {path}")
    except Exception as e:
        print(f"[WARN] Failed to take screenshot: {e}")


async def is_chrome_debug_accessible() -> bool:
    """Check if Chrome debugging port is already accessible."""
    import urllib.request
    try:
        response = urllib.request.urlopen(f"http://{DEBUG_HOST}:{DEBUG_PORT}/json/version", timeout=3)
        data = json.loads(response.read())
        print(f"Chrome debugging already accessible. Version: {data.get('Browser', 'unknown')}")
        return True
    except Exception:
        return False


async def start_chrome_with_debugging():
    """Start Chrome with remote debugging enabled using automation profile."""
    # First check if Chrome is already running with debug port
    if await is_chrome_debug_accessible():
        print("Chrome already running with debugging enabled. Continuing...")
        return True
    
    # Start Chrome with automation profile (DO NOT kill existing Chrome)
    print("Starting Chrome with automation profile...")
    subprocess.Popen([
        CHROME_PATH,
        f"--remote-debugging-port={DEBUG_PORT}",
        f"--remote-debugging-address={DEBUG_HOST}",
        f"--user-data-dir={USER_DATA_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Wait for Chrome to start
    await asyncio.sleep(5)
    
    # Check if debugging port is accessible
    import urllib.request
    try:
        response = urllib.request.urlopen(f"http://{DEBUG_HOST}:{DEBUG_PORT}/json/version", timeout=5)
        data = json.loads(response.read())
        print(f"Chrome started successfully. Version: {data.get('Browser', 'unknown')}")
        return True
    except Exception as e:
        print(f"Failed to connect to Chrome debugging port: {e}")
        print("Please run setup_automation_profile.py first to set up the automation profile")
        return False


async def main():
    print("=" * 60)
    print("AI JOB AGENT - USING EXISTING CHROME PROFILE")
    print("=" * 60)
    print()
    
    # Start Chrome with debugging
    if not await start_chrome_with_debugging():
        print("!! Failed to start Chrome with debugging enabled")
        return
    
    print()
    print("Connecting to Chrome via CDP...")
    
    # Connect via Playwright CDP
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(f"http://{DEBUG_HOST}:{DEBUG_PORT}")
            print("[OK] Connected to Chrome!")
            
            # Get existing context (this will have all the cookies/sessions)
            contexts = browser.contexts
            if not contexts:
                print("No browser contexts found")
                await browser.close()
                return
            
            # Use the first context (default)
            context = contexts[0]
            print(f"[OK] Using existing browser context with {len(context.pages)} pages")
            
            # Create a new page for our job application
            page = await context.new_page()
            
            # Step 1: Navigate to LinkedIn
            print("\n" + "=" * 40)
            print("STEP 1: Navigating to LinkedIn")
            print("=" * 40)
            
            await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
            await human_delay(3, 5)
            
            # Check if we're logged in
            current_url = page.url
            page_title = await page.title()
            print(f"Current URL: {current_url}")
            print(f"Page title: {page_title}")
            
            await take_screenshot(page, "linkedin_home")
            
            if "login" in current_url or "authwall" in current_url:
                print("!! Not logged in - LinkedIn login page shown")
                await browser.close()
                return
            
            print("[OK] LinkedIn session is active!")
            
            # Step 2: Navigate to Jobs search
            print("\n" + "=" * 40)
            print("STEP 2: Searching for jobs")
            print("=" * 40)
            
            await page.goto(
                "https://www.linkedin.com/jobs/search/?keywords=Python%20Developer&location=India&f_TPR=r604800&f_E=2",
                wait_until="domcontentloaded"
            )
            await human_delay(4, 6)
            
            await take_screenshot(page, "jobs_search")
            
            # Wait for job listings
            try:
                await page.wait_for_selector(".jobs-search__results-list, .scaffold-layout__list, [data-job-id], .job-card-container", timeout=15000)
                print("[OK] Job results loaded!")
            except Exception as e:
                print(f"[WARN] Job results may not have loaded: {e}")
                # Let's see what's on the page
                content = await page.content()
                # Check if there are any job results at all
                job_elements = await page.query_selector_all("[data-job-id], .job-card-container, .job-card-list")
                print(f"Found {len(job_elements)} job elements on page")
                
                # Print some page content for debugging
                try:
                    body_text = await page.inner_text("body")
                    print(f"Page content (first 300 chars): {body_text[:300]}")
                except Exception:
                    pass
                
                await take_screenshot(page, "jobs_search_debug")
                if len(job_elements) == 0:
                    print("!! No jobs found on page")
                    await browser.close()
                    return
            
            # Step 3: Browse and select a job
            print("\n" + "=" * 40)
            print("STEP 3: Browsing job listings")
            print("=" * 40)
            
            # Get job cards
            job_cards = await page.query_selector_all(".job-card-container, [data-job-id], .job-card-list")
            print(f"Found {len(job_cards)} job cards")
            
            if not job_cards:
                print("!! No job cards found")
                await browser.close()
                return
            
            # Print first few job titles
            for i in range(min(3, len(job_cards))):
                try:
                    title_el = await job_cards[i].query_selector("a strong, a[href*='/jobs/view/'] strong, .job-card-list__title")
                    if not title_el:
                        title_el = await job_cards[i].query_selector("a")
                    if title_el:
                        title = (await title_el.inner_text()).strip()
                        print(f"  Job {i+1}: {title}")
                except Exception:
                    pass
            
            # Click on first job with Easy Apply
            print("\nSelecting a job to apply to...")
            job_url = None
            
            for idx in range(min(len(job_cards), 10)):
                try:
                    # Click on the card
                    await job_cards[idx].click()
                    await human_delay(2, 4)
                    
                    # Get the job URL
                    link = await job_cards[idx].query_selector("a[href*='/jobs/view/']")
                    if link:
                        href = await link.get_attribute("href")
                        if href:
                            if href.startswith("/"):
                                job_url = f"https://www.linkedin.com{href}"
                            else:
                                job_url = href
                    
                    # Check if the job has Easy Apply button
                    easy_apply = await page.query_selector("button[aria-label*='Easy Apply'], button:has-text('Easy Apply')")
                    if easy_apply:
                        print(f"[OK] Job {idx+1} has Easy Apply option!")
                        print(f"     URL: {job_url}")
                        break
                    
                    # Check for apply button
                    apply_btn = await page.query_selector("button[aria-label*='Apply'], button:has-text('Apply'), button.jobs-apply-button")
                    if apply_btn:
                        print(f"[OK] Job {idx+1} has Apply button!")
                        print(f"     URL: {job_url}")
                        break
                        
                except Exception as e:
                    print(f"[WARN] Failed to select job {idx+1}: {e}")
                    continue
            
            if not job_url:
                print("!! Could not find a suitable job with apply button")
                await browser.close()
                return
            
            print(f"\nSelected job URL: {job_url}")
            await take_screenshot(page, "selected_job")
            
            # Step 4: Apply to the job
            print("\n" + "=" * 40)
            print("STEP 4: Applying to job")
            print("=" * 40)
            
            # Stay on the search results page and click Apply button directly
            # (This is more human-like and avoids page structure issues)
            print("   Using the Apply button from the search results page...")
            
            # We already have the reference to the apply button from step 3
            # Let's find it again on the search results page
            apply_button = None
            
            for selector in [
                "button[aria-label*='Easy Apply']",
                "button[aria-label*='Apply']",
                "button:has-text('Easy Apply')",
                "button:has-text('Apply')",
                "button.jobs-apply-button",
                "[data-control-name*='apply']",
                ".jobs-apply-button",
                "[data-test-job-apply-btn]",
            ]:
                try:
                    btn = await page.query_selector(selector)
                    if btn:
                        # Scroll into view if needed
                        await btn.scroll_into_view_if_needed()
                        is_visible = await btn.is_visible()
                        if is_visible:
                            apply_button = btn
                            text = await btn.inner_text()
                            print(f"   Found apply button: {selector} -> '{text.strip()}'")
                            break
                except Exception:
                    continue
            
            # If not found on search results, try to find on the job panel
            if not apply_button:
                print("   Apply button not found on search result list, trying job details panel...")
                
                # The job details panel may show the apply button
                for selector in [
                    ".jobs-details__main-content button[aria-label*='Apply']",
                    ".jobs-details__main-content button:has-text('Apply')",
                    "button[data-control-name='jobdetails_topcard_inapply']",
                    ".job-details-jobs-unified-top-card__button-container button",
                    "[data-control-name*='apply']",
                    "button:has-text('Easy Apply')",
                    "button:has-text('Apply')",
                ]:
                    try:
                        btn = await page.query_selector(selector)
                        if btn:
                            await btn.scroll_into_view_if_needed()
                            is_visible = await btn.is_visible()
                            if is_visible:
                                apply_button = btn
                                text = await btn.inner_text()
                                print(f"   Found apply button in details: {selector} -> '{text.strip()}'")
                                break
                    except Exception:
                        continue
            
            if not apply_button:
                print("!! Could not find apply button")
                await take_screenshot(page, "no_apply_button")
                # Debug: print all buttons on page
                try:
                    all_btns = await page.query_selector_all("button")
                    print(f"   Found {len(all_btns)} buttons on page")
                    for btn in all_btns[:10]:
                        try:
                            text = (await btn.inner_text()).strip()
                            aria = await btn.get_attribute("aria-label") or ""
                            print(f"   Button: '{text}' aria='{aria}'")
                        except:
                            pass
                except:
                    pass
                await browser.close()
                return
            
            # Human-like pause before clicking apply
            print("   Reviewing the job before applying...")
            await human_delay(3, 6)
            
            # Read job description briefly
            try:
                desc = await page.query_selector(".jobs-description__content, .jobs-box__html-content")
                if desc:
                    text = await desc.inner_text()
                    print(f"   Job description preview: {text[:100]}...")
            except Exception:
                pass
            
            print("   Clicking Apply button...")
            await apply_button.click()
            await human_delay(3, 5)
            
            await take_screenshot(page, "after_apply_click")
            
            # Check if application form opened
            modal = await page.query_selector(".jobs-easy-apply-modal, div[role='dialog'], form[data-easy-apply-form]")
            
            if not modal:
                # Check if redirected to external site
                current_url = page.url
                if "linkedin.com" not in current_url:
                    print(f"   Redirected to external site: {current_url}")
                    print("   Please complete the application manually in the browser.")
                    # Keep browser open
                    print("\nBrowser will stay open for 120 seconds for manual completion...")
                    await asyncio.sleep(120)
                    await browser.close()
                    return
                
                print("   No Easy Apply modal found - job may use external application")
                print("   Please complete the application manually if needed.")
                await asyncio.sleep(120)
                await browser.close()
                return
            
            # Step 5: Fill the application form
            print("\n" + "=" * 40)
            print("STEP 5: Filling application form")
            print("=" * 40)
            
            # Application form handling
            next_buttons = [
                "button[aria-label*='Continue to next step']",
                "button[aria-label*='Next']",
                "button:has-text('Next')",
                "button[aria-label*='Review']",
                "button[aria-label*='Submit']",
                "button:has-text('Review')",
                "button:has-text('Submit')",
                "button:has-text('Continue')",
                ".artdeco-button--primary",
                "button[type='submit']",
            ]
            
            max_steps = 10
            for step in range(max_steps):
                print(f"\n--- Application step {step + 1} ---")
                await take_screenshot(page, f"form_step_{step + 1}")
                
                # Fill text inputs
                text_inputs = await page.query_selector_all("input[type='text'], input[type='email'], input[type='tel'], textarea")
                for input_el in text_inputs:
                    try:
                        # Check if already filled
                        current_value = await input_el.input_value()
                        if current_value:
                            continue
                        
                        # Get field info
                        info = await input_el.evaluate("""el => {
                            let label = '';
                            let placeholder = el.placeholder || '';
                            let name = el.name || '';
                            let id = el.id || '';
                            
                            if (el.id) {
                                const lbl = document.querySelector(`label[for="${el.id}"]`);
                                if (lbl) label = lbl.textContent.trim();
                            }
                            
                            const parent = el.closest('.fb-dash-form-element, .jobs-easy-apply-form-element');
                            if (parent) {
                                const lbl = parent.querySelector('label');
                                if (lbl) label = lbl.textContent.trim();
                            }
                            
                            return {label, placeholder, name, id};
                        }""")
                        
                        label_text = f"{info['label']} {info['placeholder']} {info['name']}".lower()
                        
                        if "phone" in label_text:
                            await human_type(page, input_el, "+919182595928")
                        elif "email" in label_text:
                            await human_type(page, input_el, "satishryali252@gmail.com")
                        elif "first" in label_text:
                            await human_type(page, input_el, "Satyanarayana")
                        elif "last" in label_text:
                            await human_type(page, input_el, "Ryali")
                        elif "city" in label_text:
                            await human_type(page, input_el, "Hyderabad")
                        
                        await human_delay(0.3, 0.7)
                    except Exception:
                        continue
                
                # Handle select dropdowns
                selects = await page.query_selector_all("select")
                for select_el in selects:
                    try:
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
                            
                            const options = Array.from(el.options).map(o => ({text: o.text, value: o.value}));
                            return {label, name, options};
                        }""")
                        
                        label_text = f"{info['label']} {info['name']}".lower()
                        options = info['options']
                        
                        if "experience" in label_text:
                            for opt in options:
                                if "4" in opt['text'] or "4" in opt['value']:
                                    await select_el.select_option(value=opt['value'])
                                    break
                        elif "country" in label_text:
                            for opt in options:
                                if "india" in opt['text'].lower():
                                    await select_el.select_option(value=opt['value'])
                                    break
                        elif "state" in label_text or "province" in label_text:
                            for opt in options:
                                if "telangana" in opt['text'].lower() or "andhra" in opt['text'].lower():
                                    await select_el.select_option(value=opt['value'])
                                    break
                    except Exception:
                        continue
                
                # Handle radio buttons
                radios = await page.query_selector_all("input[type='radio']")
                for radio in radios:
                    try:
                        radio_info = await radio.evaluate("""el => ({
                            value: el.value || '',
                            name: el.name || '',
                            label: el.closest('label') ? el.closest('label').textContent.trim() : ''
                        })""")
                        
                        label_text = f"{radio_info['label']} {radio_info['value']}".lower()
                        checked = await radio.is_checked()
                        
                        if not checked and "yes" in label_text:
                            await radio.check(force=True)
                            await human_delay(0.2, 0.5)
                    except Exception:
                        continue
                
                # Handle checkboxes
                checkboxes = await page.query_selector_all("input[type='checkbox']")
                for checkbox in checkboxes:
                    try:
                        label = await checkbox.evaluate("el => el.closest('label') ? el.closest('label').textContent.trim() : ''")
                        checked = await checkbox.is_checked()
                        label_lower = label.lower()
                        
                        if not checked and "subscri" not in label_lower and "newsletter" not in label_lower:
                            await checkbox.check(force=True)
                            await human_delay(0.2, 0.5)
                    except Exception:
                        continue
                
                # Human pause before clicking next
                await human_delay(1, 3)
                
                # Click Next/Submit button
                clicked = False
                for selector in next_buttons:
                    try:
                        btn = await page.query_selector(selector)
                        if btn:
                            await btn.scroll_into_view_if_needed()
                            if await btn.is_visible():
                                await human_delay(0.5, 1.5)
                                await btn.click()
                                print(f"   Clicked button: {selector}")
                                clicked = True
                                await human_delay(2, 4)
                                break
                    except Exception:
                        continue
                
                if not clicked:
                    # Try any button with action words
                    all_buttons = await page.query_selector_all("button")
                    for btn in all_buttons:
                        try:
                            text = (await btn.inner_text()).strip().lower()
                            if any(word in text for word in ["next", "continue", "submit", "review", "finish"]):
                                await btn.scroll_into_view_if_needed()
                                if await btn.is_visible() and not await btn.evaluate("el => el.disabled"):
                                    await human_delay(0.5, 1.5)
                                    await btn.click()
                                    print(f"   Clicked button by text: {text}")
                                    clicked = True
                                    await human_delay(2, 4)
                                    break
                        except Exception:
                            continue
                
                if not clicked:
                    # Check if submitted
                    try:
                        body_text = await page.inner_text("body")
                        if any(word in body_text.lower() for word in ["application submitted", "thank you for applying", "congratulations"]):
                            print("[SUCCESS] Application submitted!")
                            await take_screenshot(page, "application_submitted")
                            await browser.close()
                            return
                    except Exception:
                        pass
                    
                    print("   No more next/submit buttons found")
                    break
            
            # Final check
            await human_delay(3, 5)
            try:
                body_text = await page.inner_text("body")
                if any(word in body_text.lower() for word in ["application submitted", "thank you for applying", "your application"]):
                    print("\n" + "=" * 60)
                    print("[SUCCESS] APPLICATION SUBMITTED SUCCESSFULLY!")
                    print("=" * 60)
                else:
                    print("\n" + "=" * 60)
                    print("[WARNING] Could not confirm submission.")
                    print("Please check the browser window to complete manually.")
                    print("=" * 60)
            except Exception:
                pass
            
            # Keep browser open for review
            print("\nBrowser will stay open for 120 seconds for review...")
            await asyncio.sleep(120)
            
            await browser.close()
            print("\n[OK] Done!")
            
        except Exception as e:
            print(f"!! Error: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())