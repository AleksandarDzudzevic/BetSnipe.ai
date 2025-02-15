import undetected_chromedriver as uc
import atexit
import time
import os
import shutil
from threading import Lock
import tempfile

class BrowserManager:
    _instance = None
    _lock = Lock()
    _browser = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BrowserManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._browser:
            self._init_browser()

    def _init_browser(self):
        try:
            # Create a unique temporary directory for Chrome data
            temp_dir = tempfile.mkdtemp()
            
            options = uc.ChromeOptions()
            options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument(f'--user-data-dir={temp_dir}')
            options.add_argument('--disable-extensions')
            
            # Delete existing chromedriver if it exists
            chromedriver_path = os.path.join(os.path.expanduser('~'), 'appdata', 'roaming', 'undetected_chromedriver')
            if os.path.exists(chromedriver_path):
                try:
                    shutil.rmtree(chromedriver_path)
                except:
                    pass
            
            self._browser = uc.Chrome(
                options=options,
                version_main=132,
                driver_executable_path=None  # Let it download fresh copy
            )
            
        except Exception as e:
            print(f"Error initializing browser: {e}")
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            raise

    def create_tab(self):
        """Create a new tab and return its handle"""
        with self._lock:
            try:
                # Create new tab
                self._browser.execute_script("window.open('about:blank', '_blank');")
                # Switch to the new tab (it's always the last one)
                handles = self._browser.window_handles
                new_handle = handles[-1]
                self._browser.switch_to.window(new_handle)
                return new_handle
            except Exception as e:
                print(f"Error creating tab: {e}")
                return None

    def switch_to_tab(self, handle):
        """Switch to a specific tab"""
        with self._lock:
            try:
                self._browser.switch_to.window(handle)
            except Exception as e:
                print(f"Error switching to tab: {e}")

    def close_tab(self, handle):
        """Close a specific tab"""
        with self._lock:
            try:
                self._browser.switch_to.window(handle)
                self._browser.close()
                # Switch to the first tab if available
                if self._browser.window_handles:
                    self._browser.switch_to.window(self._browser.window_handles[0])
            except Exception as e:
                print(f"Error closing tab: {e}")

    def execute_script(self, script, handle=None):
        """Execute JavaScript in a specific tab"""
        with self._lock:
            try:
                if handle:
                    self.switch_to_tab(handle)
                return self._browser.execute_script(script)
            except Exception as e:
                print(f"Error executing script: {e}")
                return None

    def cleanup(self):
        """Clean up the browser instance"""
        if self._browser:
            try:
                self._browser.quit()
            except:
                pass
            finally:
                self._browser = None
                # Clean up Chrome user data directory
                chrome_dir = os.path.join(os.path.expanduser('~'), 'appdata', 'roaming', 'undetected_chromedriver')
                if os.path.exists(chrome_dir):
                    try:
                        shutil.rmtree(chrome_dir)
                    except:
                        pass

# Create singleton instance
browser_manager = BrowserManager()
# Register cleanup
atexit.register(browser_manager.cleanup) 