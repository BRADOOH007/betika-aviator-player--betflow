"""
Diagnose why the Login button isn't clickable
"""
from playwright.sync_api import sync_playwright
import time

print("🔍 Diagnosing Login Button Issue...")

with sync_playwright() as p:
    browser = p.firefox.launch(headless=False)
    context = browser.new_context(
        viewport={"width": 414, "height": 896},
        user_agent="Mozilla/5.0 (Android 11; Mobile; rv:120.0) Gecko/120.0 Firefox/120.0",
    )
    context.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
    page = context.new_page()
    
    print("📱 Navigating to OdiBets...")
    page.goto("https://odibets.com/aviator", wait_until="domcontentloaded")
    time.sleep(2)
    
    print("🔓 Opening login dialog...")
    try:
        page.get_by_role("button", name="Login to play").click(force=True, timeout=8000)
        print("✅ Login dialog opened")
    except Exception as e:
        print(f"❌ Failed to open dialog: {e}")
    
    time.sleep(2)
    
    print("\n📋 Filling credentials...")
    page.locator("input[type='tel']").first.fill("0706719388")
    print("✅ Phone entered")
    
    page.locator("input[type='password']").first.fill("test123")
    print("✅ Password entered")
    
    time.sleep(1)
    
    print("\n🔍 Analyzing Login Button...")
    
    # Get detailed button info
    button_info = page.evaluate("""() => {
        const buttons = Array.from(document.querySelectorAll('button'));
        const loginBtn = buttons.find(b => b.textContent.includes('Login to Odibets'));
        
        if (!loginBtn) {
            return {error: 'Button not found'};
        }
        
        const rect = loginBtn.getBoundingClientRect();
        const style = window.getComputedStyle(loginBtn);
        
        // Check what's on top of the button
        const elementAtCenter = document.elementFromPoint(
            rect.left + rect.width / 2,
            rect.top + rect.height / 2
        );
        
        return {
            text: loginBtn.textContent.trim(),
            visible: loginBtn.offsetParent !== null,
            disabled: loginBtn.disabled,
            className: loginBtn.className,
            id: loginBtn.id,
            position: {
                x: Math.round(rect.x),
                y: Math.round(rect.y),
                width: Math.round(rect.width),
                height: Math.round(rect.height)
            },
            style: {
                display: style.display,
                visibility: style.visibility,
                opacity: style.opacity,
                pointerEvents: style.pointerEvents,
                zIndex: style.zIndex,
                position: style.position
            },
            elementOnTop: elementAtCenter ? {
                tag: elementAtCenter.tagName,
                className: elementAtCenter.className,
                id: elementAtCenter.id,
                text: elementAtCenter.textContent.substring(0, 50)
            } : null,
            isButtonOnTop: elementAtCenter === loginBtn
        };
    }""")
    
    print("\n📊 Button Analysis:")
    print(f"  Text: {button_info.get('text')}")
    print(f"  Visible: {button_info.get('visible')}")
    print(f"  Disabled: {button_info.get('disabled')}")
    print(f"  Position: {button_info.get('position')}")
    print(f"  Style: {button_info.get('style')}")
    print(f"  Is button on top: {button_info.get('isButtonOnTop')}")
    
    if not button_info.get('isButtonOnTop'):
        print(f"\n⚠️ PROBLEM: Something is covering the button!")
        print(f"  Element on top: {button_info.get('elementOnTop')}")
    
    print("\n🖱️ Attempting different click methods...")
    
    # Method 1: Playwright click
    try:
        page.locator("button:has-text('Login to Odibets')").first.click(timeout=3000)
        print("✅ Method 1 (Playwright) - SUCCESS")
    except Exception as e:
        print(f"❌ Method 1 (Playwright) - FAILED: {str(e)[:100]}")
    
    time.sleep(1)
    
    # Method 2: Force click
    try:
        page.locator("button:has-text('Login to Odibets')").first.click(force=True, timeout=3000)
        print("✅ Method 2 (Force) - SUCCESS")
    except Exception as e:
        print(f"❌ Method 2 (Force) - FAILED: {str(e)[:100]}")
    
    time.sleep(1)
    
    # Method 3: Coordinate click
    try:
        pos = button_info.get('position')
        x = pos['x'] + pos['width'] / 2
        y = pos['y'] + pos['height'] / 2
        page.mouse.click(x, y)
        print(f"✅ Method 3 (Coordinates {x},{y}) - SUCCESS")
    except Exception as e:
        print(f"❌ Method 3 (Coordinates) - FAILED: {str(e)[:100]}")
    
    time.sleep(1)
    
    # Method 4: JavaScript click
    try:
        result = page.evaluate("""() => {
            const buttons = Array.from(document.querySelectorAll('button'));
            const loginBtn = buttons.find(b => b.textContent.trim() === 'Login to Odibets');
            if (loginBtn) {
                loginBtn.click();
                return 'clicked';
            }
            return 'not found';
        }""")
        print(f"✅ Method 4 (JavaScript) - {result}")
    except Exception as e:
        print(f"❌ Method 4 (JavaScript) - FAILED: {str(e)[:100]}")
    
    print("\n⏳ Waiting 5 seconds to see if dialog closes...")
    time.sleep(5)
    
    # Check if dialog closed
    phone_count = page.locator("input[type='tel']").count()
    if phone_count == 0:
        print("✅ SUCCESS: Login dialog closed!")
    else:
        print(f"❌ FAILED: Dialog still open (phone inputs: {phone_count})")
        print("\n📸 Taking screenshot...")
        page.screenshot(path="debug_screenshots/login_button_diagnosis.png")
        print("Screenshot saved: debug_screenshots/login_button_diagnosis.png")
    
    print("\n⏸️ Keeping browser open for 30 seconds for manual inspection...")
    time.sleep(30)
    
    browser.close()
    print("\n✅ Diagnosis complete!")
