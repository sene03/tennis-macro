from selenium.webdriver import Chrome
from selenium.webdriver.chrome.options import Options as ChromeOptions

def build_driver(headless: bool = False):
    opts = ChromeOptions()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--start-maximized")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    driver = Chrome(options=opts)
    driver.set_page_load_timeout(60)
    return driver

def hide_popups(driver):
    """페이지 공통 팝업 숨김 (#popup 등)"""
    try:
        driver.execute_script("""
            document.querySelectorAll('#popup, .pop').forEach(el => el.style.display='none');
        """)
    except Exception:
        pass
