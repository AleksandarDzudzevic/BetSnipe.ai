import undetected_chromedriver as uc
import time

class BrowserManager:
    _instance = None
    _browser = None

    @classmethod
    def get_browser(cls):
        if cls._browser is None:
            options = uc.ChromeOptions()
            options.add_argument("--headless")
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-extensions")
            options.add_argument("--disable-logging")
            
            cls._browser = uc.Chrome(options=options, version_main=131)
            cls._browser.get("https://www.mozzartbet.com/sr/kladjenje")
            time.sleep(2)
        return cls._browser

    @classmethod
    def cleanup(cls):
        if cls._browser:
            try:
                cls._browser.quit()
            except:
                pass
            cls._browser = None 