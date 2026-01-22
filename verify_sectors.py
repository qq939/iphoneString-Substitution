import time
from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        print("Navigating to homepage...")
        page.goto("http://127.0.0.1:5015", wait_until="domcontentloaded")
        
        # 1. Test Pagination
        print("Testing pagination...")
        # Check if page 2 is hidden initially
        page2_element = page.locator(".page.page-2")
        if "active" in page2_element.get_attribute("class"):
            print("ERROR: Page 2 should not be active initially")
        
        # Click NEXT
        print("Clicking NEXT...")
        page.click(".page-nav-next")
        time.sleep(1)
        
        # Check if page 2 is active
        if "active" not in page2_element.get_attribute("class"):
            print("ERROR: Page 2 should be active after clicking NEXT")
        else:
            print("Pagination SUCCESS: Page 2 is active")
            
        # 2. Test Sector 17 Presence
        print("Checking Sector 17...")
        sector17 = page.locator(".item-17")
        if sector17.count() > 0:
            print("Sector 17 found.")
            # Check input and button
            input_box = sector17.locator("input#sector17Input")
            submit_btn = sector17.locator("button.action-btn")
            if input_box.count() > 0 and submit_btn.count() > 0:
                print("Sector 17 UI elements verified.")
            else:
                print("ERROR: Sector 17 UI elements missing.")
        else:
            print("ERROR: Sector 17 not found.")

        # 3. Test Sector 19 Presence
        print("Checking Sector 19...")
        sector19 = page.locator(".item-19")
        if sector19.count() > 0:
            print("Sector 19 found.")
            # Check file input and button
            file_input = sector19.locator("input[type='file']")
            submit_btn = sector19.locator("button[type='submit']")
            if file_input.count() > 0 and submit_btn.count() > 0:
                print("Sector 19 UI elements verified.")
            else:
                print("ERROR: Sector 19 UI elements missing.")
        else:
            print("ERROR: Sector 19 not found.")
            
        browser.close()

if __name__ == "__main__":
    run()
