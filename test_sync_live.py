import time
from playwright.sync_api import sync_playwright
import requests

def test_sync():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        # Context 1: User A
        context1 = browser.new_context()
        page1 = context1.new_page()
        page1.on("console", lambda msg: print(f"User A Console: {msg.text}"))
        page1.goto("http://127.0.0.1:5015")
        
        print("User A: Typing in Sector 7 (Audio)...")
        # Sector 7 input is on Page 1, so it should be visible
        page1.locator('#audioUploadForm input[name="text"]').fill("Hello Sync World")
        
        # Verify sync to backend
        time.sleep(1) # Wait for debounce
        response = requests.get("http://127.0.0.1:5015/api/sync_state")
        state = response.json()
        print(f"Backend State: {state.get('sector7')}")
        assert state['sector7']['text'] == "Hello Sync World"

        # Simulate a task submission (Inject state directly)
        fake_task_id = "fake-task-123"
        print("Injecting fake task ID for Sector 7...")
        requests.post("http://127.0.0.1:5015/api/sync_state", json={
            "sector": "sector7",
            "updates": {"latest_task_id": fake_task_id}
        })
        
        # Verify injection
        response = requests.get("http://127.0.0.1:5015/api/sync_state")
        state = response.json()
        print(f"Backend State After Injection: {state.get('sector7')}")
        assert state['sector7']['latest_task_id'] == fake_task_id

        # Context 2: User B (New Session)
        print("User B: Opening page...")
        context2 = browser.new_context()
        page2 = context2.new_page()
        
        # Listen for console logs
        page2.on("console", lambda msg: print(f"User B Console: {msg.text}"))
        page2.on("pageerror", lambda exc: print(f"User B Page Error: {exc}"))
        
        page2.goto("http://127.0.0.1:5015")
        
        # Verify Input Restoration
        print("User B: Verifying input restoration...")
        page2.wait_for_selector('#audioUploadForm input[name="text"]')
        restored_text = page2.input_value('#audioUploadForm input[name="text"]')
        print(f"User B saw text: {restored_text}")
        assert restored_text == "Hello Sync World"

        # Manually trigger restoreState to ensure it runs and we see logs
        print("User B: Manually triggering restoreState()...")
        page2.evaluate("restoreState()")
        
        # Check if pollSector7 is defined
        is_defined = page2.evaluate("typeof pollSector7 === 'function'")
        print(f"User B: pollSector7 is function? {is_defined}")

        # Verify Log/Status Restoration
        print("User B: Verifying status restoration (Log retention)...")
        status_locator = page2.locator('#audioStatus')
        
        # Wait for status to change
        try:
            # We expect "RESTORING SESSION..." initially or "PROCESSING"
            for i in range(20): # 10 seconds
                text = status_locator.inner_text()
                print(f"User B Status ({i}): '{text}'")
                if "RESTORING" in text or "FAILED" in text or "PROCESSING" in text:
                    break
                time.sleep(0.5)
            
            final_text = status_locator.inner_text()
            print(f"Final User B Status: '{final_text}'")
            assert "RESTORING" in final_text or "FAILED" in final_text or "PROCESSING" in final_text
        except Exception as e:
            print(f"Status check failed: {e}")
            raise

        print("Sync Test Passed for Sector 7!")

        # Test Sector 17 (Page 2)
        print("\n--- Testing Sector 17 (Page 2) ---")
        
        # User A navigates to Page 2
        print("User A: Navigating to Page 2...")
        page1.click('.page-nav-next')
        time.sleep(1) # Wait for animation
        
        # User A types in Sector 17
        print("User A: Typing in Sector 17...")
        page1.locator('#sector17Input').fill("Sync Test Sector 17")
        
        # Verify backend state
        time.sleep(1)
        response = requests.get("http://127.0.0.1:5015/api/sync_state")
        state = response.json()
        print(f"Backend State (Sector 17): {state.get('sector17')}")
        assert state['sector17']['text'] == "Sync Test Sector 17"
        
        # User B navigates to Page 2
        print("User B: Navigating to Page 2...")
        page2.click('.page-nav-next')
        time.sleep(1)
        
        # Verify Input Restoration for User B
        print("User B: Verifying Sector 17 input restoration...")
        
        # Retry loop for sync (since it polls every 2s)
        found_text = False
        for i in range(10): # 5 seconds max
            restored_text_17 = page2.input_value('#sector17Input')
            print(f"User B saw Sector 17 text ({i}): {restored_text_17}")
            if restored_text_17 == "Sync Test Sector 17":
                found_text = True
                break
            time.sleep(0.5)
        
        assert found_text, f"Expected 'Sync Test Sector 17', got '{restored_text_17}'"
        
        print("Sync Test Passed for Sector 17!")

        browser.close()

if __name__ == "__main__":
    test_sync()
