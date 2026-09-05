"""Set up a separate Chrome automation profile for LinkedIn automation.

This creates a clean Chrome profile that we can use for automation
without touching your main Chrome profile with all your bookmarks.
"""

import asyncio
import subprocess
import os
import random
import time
from pathlib import Path

# Chrome path
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

# Automation profile directory (separate from your main profile)
AUTOMATION_PROFILE = r"C:\GIT\AI_JOB_AGENT\chrome_automation_profile"
DEBUG_PORT = 9333

async def main():
    print("=" * 60)
    print("SETUP AUTOMATION CHROME PROFILE")
    print("=" * 60)
    print()
    
    # Create automation profile directory
    print(f"Creating automation profile at: {AUTOMATION_PROFILE}")
    os.makedirs(AUTOMATION_PROFILE, exist_ok=True)
    print("[OK] Automation profile directory created")
    print()
    
    # Check if Chrome is already running with this profile
    import urllib.request
    import json
    try:
        response = urllib.request.urlopen(f"http://127.0.0.1:{DEBUG_PORT}/json/version", timeout=3)
        data = json.loads(response.read())
        print(f"[OK] Automation Chrome already running on port {DEBUG_PORT}")
        print(f"     Browser: {data.get('Browser', 'unknown')}")
        print()
        print("LinkedIn automation Chrome is already running.")
        return
    except Exception:
        pass
    
    # Launch Chrome with the automation profile and debugging
    print(f"Launching Chrome with automation profile...")
    print(f"  Profile: {AUTOMATION_PROFILE}")
    print(f"  Debug port: {DEBUG_PORT}")
    
    subprocess.Popen([
        CHROME_PATH,
        f"--remote-debugging-port={DEBUG_PORT}",
        "--remote-debugging-address=127.0.0.1",
        f"--user-data-dir={AUTOMATION_PROFILE}",
        "--no-first-run",
        "--no-default-browser-check",
        "https://www.linkedin.com/login",  # Open LinkedIn login
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    print("\nChrome launched with automation profile!")
    print("=" * 60)
    print("NEXT STEPS:")
    print("=" * 60)
    print("1. A new Chrome window has opened with LinkedIn login page")
    print("2. Please LOG IN to LinkedIn in this window")
    print("3. Your main Chrome profile is NOT affected")
    print("   - All your bookmarks and sessions remain intact")
    print("   - This is a fresh, separate profile just for automation")
    print("4. Once you're logged in, run the apply script:")
    print("   python chrome_profile_apply.py")
    print("=" * 60)
    
    # Keep running to let user log in
    print("\nWaiting for you to log in...")
    print("(Press Ctrl+C when done)")
    
    # Wait for user to log in (up to 5 minutes)
    max_wait = 300  # 5 minutes
    waited = 0
    
    while waited < max_wait:
        await asyncio.sleep(5)
        waited += 5
        
        # Check if user logged in by checking the URL
        try:
            import urllib.request
            import json
            response = urllib.request.urlopen(f"http://127.0.0.1:{DEBUG_PORT}/json", timeout=3)
            tabs = json.loads(response.read())
            for tab in tabs:
                url = tab.get('url', '')
                if 'linkedin.com/feed' in url or 'linkedin.com/jobs' in url:
                    print("[OK] LinkedIn login detected! You're all set!")
                    print("\nNow run: python chrome_profile_apply.py")
                    return
        except Exception:
            pass
        
        if waited % 30 == 0:
            print(f"... waiting for login ({waited}/{max_wait}s)...")


if __name__ == "__main__":
    asyncio.run(main())