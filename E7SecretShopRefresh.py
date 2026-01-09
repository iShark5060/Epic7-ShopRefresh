import tkinter as tk
from tkinter import ttk
from PIL import ImageTk, Image
import csv
import os
import sys
import time
import threading
from datetime import datetime
import re
import argparse
import pyautogui
import pygetwindow as gw
import cv2
import numpy as np
import keyboard
from PIL import ImageGrab
import random

def get_asset_path(relative_path):
    """Get the correct path for assets, works for both dev and PyInstaller bundle"""
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

class ShopItem:
    def __init__(self, path='', image=None, price=0, count=0):
        self.path=path
        self.image=image
        self.scaled_image=image
        self.price=price
        self.count=count

    def __repr__(self):
        return f'ShopItem(path={self.path}, image={self.image}, price={self.price}, count={self.count})'

class RefreshStatistic:
    def __init__(self):
        self.refresh_count = 0
        self.items = {}
        self.start_time = datetime.now()

    def updateTime(self):
        self.start_time = datetime.now()

    def addShopItem(self, path: str, name='', price=0, count=0):
        image = cv2.imread(get_asset_path(os.path.join('assets', path)))
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        newItem = ShopItem(path, image, price, count)
        self.items[name] = newItem

    def getInventory(self):
        return self.items

    def getName(self):
        return list(self.items.keys())

    def getPath(self):
        return [shop_item.path for shop_item in self.items.values()]

    def getItemCount(self):
        return [shop_item.count for shop_item in self.items.values()]

    def getTotalCost(self):
        total = 0
        for shop_item in self.items.values():
            total += shop_item.price * shop_item.count
        return total

    def incrementRefreshCount(self):
        self.refresh_count += 1

    def writeToCSV(self):
        res_folder = 'ShopRefreshHistory'
        if not os.path.exists(res_folder):
            os.makedirs(res_folder)

        gen_path = 'refreshAttempt'
        for name in self.getName():
            gen_path += name[:4]
        gen_path += '.csv'

        path = os.path.join(res_folder, gen_path)

        if not os.path.isfile(path):
            with open(path, 'w', newline='') as file:
                writer = csv.writer(file)
                column_name = ['Time', 'Duration', 'Refresh count', 'Skystone spent', 'Gold spent']
                column_name.extend(self.getName())
                writer.writerow(column_name)
        with open(path, 'a', newline='') as file:
            writer = csv.writer(file)
            data = [self.start_time, datetime.now()-self.start_time, self.refresh_count, self.refresh_count*3, self.getTotalCost()]
            data.extend(self.getItemCount())
            writer.writerow(data)

class SecretShopRefresh:
    REFERENCE_WIDTH = 3840
    REFERENCE_HEIGHT = 1600

    MOUSE_SLEEP = 0.15
    SCREENSHOT_SLEEP = 0.15

    RANDOM_DELAY_MIN = 0.0
    RANDOM_DELAY_MAX = 0.1
    CLICK_OFFSET_MAX = 10
    DOUBLE_CLICK_CHANCE = 0.3
    SCROLL_RANDOM_EXTRA_MIN = 0.0
    SCROLL_RANDOM_EXTRA_MAX = 0.15

    SCROLL_RATIO = 0.277
    ITEM_MATCH_THRESHOLD = 0.8
    BUTTON_MATCH_THRESHOLD = 0.75
    SHOP_CHECK_THRESHOLD = 0.7
    BUY_BUTTON_THRESHOLD = 0.7
    SOLD_INDICATOR_THRESHOLD = 0.7

    def __init__(self, title_name: str, callback = None, tk_instance: tk = None, budget: int = None, allow_move: bool = False, debug: bool = False, join_thread: bool = False, custom_size: tuple = None):
        self.debug = debug
        self.debug_log_file = None
        if self.debug:
            # Open debug log file in append mode
            log_path = os.path.join(os.getcwd(), 'debug.log')
            self.debug_log_file = open(log_path, 'a', encoding='utf-8')
            self.debug_log(f'\n{"="*60}\nDebug session started at {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n{"="*60}')
        self.loop_active = False
        self.loop_finish = True

        if custom_size:
            self.REFERENCE_WIDTH = custom_size[0]
            self.REFERENCE_HEIGHT = custom_size[1]
        self.callback = callback if callback else self.refreshFinishCallback
        self.budget = budget
        self.allow_move = allow_move
        self.join_thread = join_thread
        self.scale_factor = 1.0
        self.refresh_btn_original = self._loadGrayAsset('button_refresh.png')
        self.refresh_btn = self.refresh_btn_original
        self.confirm_btn_original = self._loadGrayAsset('button_refresh_confirm.png')
        self.confirm_btn = self.confirm_btn_original
        self.confirm_buy_btn_original = self._loadGrayAsset('button_buy_confirm.png')
        self.confirm_buy_btn = self.confirm_buy_btn_original
        self.buy_btn_original = self._loadGrayAsset('button_buy.png')
        self.buy_btn = self.buy_btn_original
        self.sold_indicator_original = self._loadGrayAsset('button_buy_sold.png')
        self.sold_indicator = self.sold_indicator_original
        self.title_name = title_name
        windows = gw.getWindowsWithTitle(self.title_name)
        self.window = next((w for w in windows if w.title == self.title_name), None)

        self.tk_instance = tk_instance
        self.rs_instance = RefreshStatistic()

    def debug_log(self, message):
        """Write debug message to both console and debug.log file"""
        if self.debug:
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_message = f'[{timestamp}] {message}'
            print(log_message)
            if self.debug_log_file:
                self.debug_log_file.write(log_message + '\n')
                self.debug_log_file.flush()  # Ensure immediate write

    def __del__(self):
        """Cleanup: close debug log file if open"""
        self._closeDebugLog()

    def randomDelay(self):
        """Add a random delay for anti-detection"""
        delay = random.uniform(self.RANDOM_DELAY_MIN, self.RANDOM_DELAY_MAX)
        if self.debug and delay > 0.05:
            self.debug_log(f'[DEBUG] Random delay: {delay*1000:.0f}ms')
        time.sleep(delay)

    def randomClickOffset(self):
        """Get random x,y offset for anti-detection click variation"""
        offset_x = random.randint(-self.CLICK_OFFSET_MAX, self.CLICK_OFFSET_MAX)
        offset_y = random.randint(-self.CLICK_OFFSET_MAX, self.CLICK_OFFSET_MAX)
        if self.debug:
            self.debug_log(f'[DEBUG] Click offset: ({offset_x:+d}, {offset_y:+d}) pixels')
        return offset_x, offset_y

    def randomClick(self):
        """Perform a click with random single/double for anti-detection"""
        is_double = random.random() < self.DOUBLE_CLICK_CHANCE
        if self.debug:
            click_type = "double-click" if is_double else "single-click"
            self.debug_log(f'[DEBUG] Click type: {click_type}')
        if is_double:
            pyautogui.click(clicks=2, interval=self.MOUSE_SLEEP)
        else:
            pyautogui.click()

    def isInShop(self):
        """Check if we're still in the secret shop by looking for the refresh button"""
        try:
            screenshot = self.takeScreenshot()
            if screenshot is None:
                return False
            process_screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)

            if self.refresh_btn is not None:
                refresh_region = self.getSearchRegions()['refresh_btn']
                pos = self.findButtonPosition(process_screenshot, self.refresh_btn, threshold=self.SHOP_CHECK_THRESHOLD, search_region=refresh_region)
                return pos is not None
            return False
        except Exception as e:
            if self.debug:
                self.debug_log(f'[DEBUG] Error checking shop status: {e}')
            return False

    def waitForShop(self, max_wait_seconds=30):
        """Wait until we're back in the shop, or timeout"""
        wait_interval = 1.0
        total_waited = 0

        while total_waited < max_wait_seconds and self.loop_active:
            if self.isInShop():
                if self.debug:
                    self.debug_log('[DEBUG] Shop detected - resuming')
                return True

            print(f'[WAITING] Not in shop - waiting... ({int(total_waited)}s)')
            time.sleep(wait_interval)
            total_waited += wait_interval

        if total_waited >= max_wait_seconds:
            print('[WARNING] Timeout waiting for shop - stopping')
            return False
        return True

    def _loadGrayAsset(self, filename):
        """Load an asset image and convert to grayscale"""
        path = get_asset_path(os.path.join('assets', filename))
        if not os.path.exists(path):
            print(f'Warning: Asset {filename} not found')
            return None
        image = cv2.imread(path)
        if image is None:
            return None
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    def getSearchRegions(self):
        """Calculate optimized search regions based on reference window size (3840x1600).

        Returns:
            Dict with region definitions for each UI element:
            - refresh_btn: bottom-left region
            - confirm_btn: bottom-middle region (also catches out-of-gold popup)
            - items_search: left-anchored vertical strip
            - buy_btn: relative to found item (handled separately)
            - confirm_buy_btn: bottom-middle region
        """
        # Scale factors for current window vs reference
        width_scale = self.window.width / self.REFERENCE_WIDTH
        height_scale = self.window.height / self.REFERENCE_HEIGHT

        regions = {}

        # Refresh button: anchor bottom-left, margin: 0, size: 1442 x 273
        # (Originally 1000 x 200 at 2663x1173, scaled to 3840x1600: 1000*1.442, 200*1.364)
        refresh_w = int(1442 * width_scale)
        refresh_h = int(273 * height_scale)
        regions['refresh_btn'] = (0, self.window.height - refresh_h, refresh_w, refresh_h)

        # Refresh confirm button: anchor bottom-middle, margin-bottom: 273, size: 433 x 477
        # (Originally 300 x 350, margin-bottom: 200 at 2663x1173, scaled to 3840x1600)
        confirm_w = int(433 * width_scale)
        confirm_h = int(477 * height_scale)
        confirm_x = (self.window.width - confirm_w) // 2
        confirm_y = self.window.height - int(273 * height_scale) - confirm_h
        regions['confirm_btn'] = (confirm_x, confirm_y, confirm_w, confirm_h)

        # Items search area: anchor left, margin-left: 1687, size: 288 x 100%
        # (Originally 1170, width: 200 at 2663x1173, scaled to 3840x1600)
        items_x = int(1687 * width_scale)
        items_w = int(288 * width_scale)
        items_h = self.window.height  # 100% height
        regions['items_search'] = (items_x, 0, items_w, items_h)

        # Buy button: anchor top-left of found image, margin-left: 1082, size: 505 x 239
        # (Originally 750, size: 350 x 175 at 2663x1173, scaled to 3840x1600)
        # This is relative to found item position, so we'll return the margin and size for calculation
        # The ROI is calculated in findItemPosition() after finding the item
        buy_margin_x = int(1082 * width_scale)
        buy_w = int(505 * width_scale)
        buy_h = int(239 * height_scale)
        regions['buy_btn'] = {'margin_x': buy_margin_x, 'width': buy_w, 'height': buy_h,
                             'note': 'Relative to found item - calculated dynamically in findItemPosition()'}

        # Buy confirmation button: anchor bottom-center, go up by margin-bottom, then right and up by size
        # (Originally 450 x 120, margin-bottom: 275 at 2663x1173, scaled to 3840x1600)
        # Measurement method: from bottom center, measure up (margin-bottom), then right and up (width x height)
        # Reference values at 3840x1600: width=649, height=164, margin-bottom=375
        confirm_buy_w = int(649 * width_scale)
        confirm_buy_h = int(164 * height_scale)
        confirm_buy_margin_bottom = int(375 * height_scale)
        confirm_buy_x = self.window.width // 2  # Start from center, extend to the right
        confirm_buy_y = self.window.height - confirm_buy_margin_bottom - confirm_buy_h
        regions['confirm_buy_btn'] = (confirm_buy_x, confirm_buy_y, confirm_buy_w, confirm_buy_h)

        return regions

    def updateScaleFactor(self):
        """Calculate scale factor based on current window size vs reference resolution"""
        width_scale = self.window.width / self.REFERENCE_WIDTH
        height_scale = self.window.height / self.REFERENCE_HEIGHT
        self.scale_factor = (width_scale + height_scale) / 2
        print(f'Window size: {self.window.width}x{self.window.height}')
        print(f'Scale factor: {self.scale_factor:.3f}')

    def scaleAllAssets(self):
        """Scale all loaded assets to match current window resolution"""
        if abs(self.scale_factor - 1.0) < 0.01:
            return

        if self.refresh_btn_original is not None:
            self.refresh_btn = self.scaleImage(self.refresh_btn_original)
        if self.confirm_btn_original is not None:
            self.confirm_btn = self.scaleImage(self.confirm_btn_original)
        if self.confirm_buy_btn_original is not None:
            self.confirm_buy_btn = self.scaleImage(self.confirm_buy_btn_original)
        if self.buy_btn_original is not None:
            self.buy_btn = self.scaleImage(self.buy_btn_original)
        if self.sold_indicator_original is not None:
            self.sold_indicator = self.scaleImage(self.sold_indicator_original)

        for shop_item in self.rs_instance.getInventory().values():
            if shop_item.image is not None:
                shop_item.scaled_image = self.scaleImage(shop_item.image)

    def scaleImage(self, image):
        """Scale an image by the current scale factor"""
        if image is None:
            return None
        new_width = int(image.shape[1] * self.scale_factor)
        new_height = int(image.shape[0] * self.scale_factor)
        if new_width < 1 or new_height < 1:
            return image
        return cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_LINEAR)

    def start(self):
        if self.loop_active or not self.loop_finish:
            return

        self.loop_active = True
        self.loop_finish = False
        keyboard_thread = threading.Thread(target=self.checkKeyPress)
        refresh_thread = threading.Thread(target=self.shopRefreshLoop)
        keyboard_thread.daemon = True
        refresh_thread.daemon = True
        keyboard_thread.start()
        refresh_thread.start()
        if self.join_thread:
            keyboard_thread.join()
            refresh_thread.join()

    def checkKeyPress(self):
        while self.loop_active and not self.loop_finish:
            self.loop_active = not keyboard.is_pressed('esc')
        self.loop_active = False
        print('Terminating shop refresh ...')

    def refreshFinishCallback(self):
        print('Terminated!')
        self._closeDebugLog()

    def _closeDebugLog(self):
        """Close the debug log file if open"""
        if hasattr(self, 'debug_log_file') and self.debug_log_file:
            if self.debug:
                self.debug_log(f'\n{"="*60}\nDebug session ended at {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n{"="*60}\n')
            self.debug_log_file.close()
            self.debug_log_file = None

    def shopRefreshLoop(self):
        try:
            if self.window.isMaximized or self.window.isMinimized:
                self.window.restore()
            if not self.allow_move: self.window.moveTo(0, 0)
            self.updateScaleFactor()
            self.scaleAllAssets()
        except Exception as e:
            print(e)
            self.loop_active = False
            self.loop_finish = True
            self.callback()
            return

        mini_images = []
        hint, mini_labels, refresh_label = None, None, None
        if self.tk_instance:
            selected_path = self.rs_instance.getPath()
            for path in selected_path:
                img = Image.open(get_asset_path(os.path.join('assets', path)))
                img = img.resize((45,45))
                img = ImageTk.PhotoImage(img)
                mini_images.append(img)
            hint, mini_labels, refresh_label = self.showMiniDisplays(mini_images)

        def updateMiniDisplay():
            for label, count in zip(mini_labels, self.rs_instance.getItemCount()):
                label.config(text=count)

        def updateRefreshCounter():
            if refresh_label is None:
                return
            current = self.rs_instance.refresh_count
            if self.budget:
                max_refreshes = self.budget // 3
                remaining = max_refreshes - current
                refresh_label.config(text=f'Refreshes: {current} / {max_refreshes}\n({remaining} left)')
            else:
                refresh_label.config(text=f'Refreshes: {current}')

        time.sleep(self.MOUSE_SLEEP)

        if not self.loop_active:
            if hint: hint.destroy()
            self.loop_finish = True
            self.callback()
            return
        try:
            try:
                self.window.activate()
            except Exception as e:
                print(e)

            self.rs_instance.updateTime()
            sliding_time = max(0.7+self.SCREENSHOT_SLEEP, 1)
            loop_count = 0
            while self.loop_active:
                loop_start_time = time.time()
                loop_count += 1

                if self.debug:
                    self.debug_log(f'\n[DEBUG] ══════ Loop #{loop_count} started ══════')

                if not self.isInShop():
                    if not self.waitForShop():
                        break
                    continue

                bought = set()
                if not self.loop_active: break

                time.sleep(sliding_time)
                screenshot = self.takeScreenshot()
                process_screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)

                process_screenshot = self._buyAvailableItems(process_screenshot, bought)
                if hint: updateMiniDisplay()
                if not self.loop_active: break

                self.scrollShop()
                time.sleep(max(0.3, self.SCREENSHOT_SLEEP))
                if not self.loop_active: break

                screenshot = self.takeScreenshot()
                process_screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)

                self._buyAvailableItems(process_screenshot, bought, ' (after scroll)')
                if hint: updateMiniDisplay()
                if not self.loop_active: break

                if self.budget:
                    if self.rs_instance.refresh_count >= self.budget // 3:
                        break

                refresh_success = self.clickRefresh()
                if not refresh_success:
                    if hint:
                        refresh_label.config(text='Out of skystones!', fg='#FF6666')
                    break

                self.rs_instance.incrementRefreshCount()
                if hint: updateRefreshCounter()

                if self.debug:
                    loop_duration = time.time() - loop_start_time
                    self.debug_log(f'[DEBUG] ══════ Loop #{loop_count} completed in {loop_duration:.2f}s ══════')

                time.sleep(self.MOUSE_SLEEP)
                if self.window.title != self.title_name: break

        except Exception as e:
            print(e)
            if hint: hint.destroy()
            self.rs_instance.writeToCSV()
            self.loop_active = False
            self.loop_finish = True
            self._closeDebugLog()
            self.callback()
            return
        if hint: hint.destroy()
        self.rs_instance.writeToCSV()
        self.loop_active = False
        self.loop_finish = True
        self._closeDebugLog()
        self.callback()

        if hint: hint.destroy()
        self.rs_instance.writeToCSV()
        self.loop_active = False
        self.loop_finish = True
        self.callback()

    def showMiniDisplays(self, mini_images):
        bg_color = '#171717'
        fg_color = '#dddddd'

        if self.tk_instance is None:
            return None, None, None
        hint = tk.Toplevel(self.tk_instance)
        hint.geometry(r'220x250+%d+%d' % (self.window.left, self.window.top+self.window.height))
        hint.title('Shopping')
        hint.iconbitmap(get_asset_path(os.path.join('assets', 'icon.ico')))
        tk.Label(master=hint, text='Press ESC to stop!', bg=bg_color, fg=fg_color, font=('Helvetica', 10)).pack(pady=(5,10))
        hint.config(bg=bg_color)

        mini_stats = tk.Frame(master=hint, bg=bg_color)
        mini_labels = []

        for img in mini_images:
            frame = tk.Frame(mini_stats, bg=bg_color)
            tk.Label(master=frame, image=img, bg=bg_color).pack(side=tk.LEFT)
            count = tk.Label(master=frame, text='0', bg=bg_color, fg='#FFBF00', font=('Helvetica', 12, 'bold'))
            count.pack(side=tk.RIGHT, padx=10)
            mini_labels.append(count)
            frame.pack(pady=2)
        mini_stats.pack()

        tk.Frame(master=hint, bg=bg_color, height=10).pack()
        refresh_label = tk.Label(
            master=hint,
            text='Refreshes: 0',
            bg=bg_color,
            fg='#88FF88',
            font=('Helvetica', 11, 'bold')
        )
        refresh_label.pack(pady=10)

        return hint, mini_labels, refresh_label

    def addShopItem(self, path: str, name='', price=0, count=0):
        self.rs_instance.addShopItem(path, name, price, count)

    def takeScreenshot(self):
        try:
            try:
                self.window.activate()
            except Exception as e:
                print(e)

            region=[self.window.left, self.window.top, self.window.width, self.window.height]
            screenshot = ImageGrab.grab(bbox=(region[0], region[1], region[2] + region[0], region[3] + region[1]), all_screens=True)
            screenshot = np.array(screenshot)
            return screenshot

        except Exception as e:
            print(e)
            return None

    def _buyAvailableItems(self, process_screenshot, bought, debug_suffix=''):
        """Find and buy all available items in the current screenshot.

        Args:
            process_screenshot: Grayscale screenshot to search in
            bought: Set of already-bought item keys (modified in place)
            debug_suffix: Optional suffix for debug messages (e.g., ' (after scroll)')

        Returns:
            Updated process_screenshot after any purchases
        """
        # Get cropped search region for items
        items_region = self.getSearchRegions()['items_search']
        found_any = True
        while found_any and self.loop_active:
            found_any = False
            for key, shop_item in self.rs_instance.getInventory().items():
                if key in bought:
                    continue
                pos = self.findItemPosition(process_screenshot, shop_item.scaled_image, item_name=key, search_region=items_region)
                if pos is not None:
                    if self.debug:
                        self.debug_log(f'[DEBUG] Found "{key}"{debug_suffix} - clicking buy button')
                    self.clickBuy(pos)
                    shop_item.count += 1
                    bought.add(key)
                    found_any = True
                    time.sleep(0.3)
                    screenshot = self.takeScreenshot()
                    if screenshot is None:
                        return process_screenshot
                    process_screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
                    break
        return process_screenshot

    def findItemPosition(self, process_screenshot, process_item, item_name='unknown', search_region=None):
        """Find an item in the screenshot and return the buy button position.

        Args:
            process_screenshot: Grayscale screenshot to search in
            process_item: Template image of the item to find
            item_name: Name of the item for debugging
            search_region: Optional tuple (x, y, width, height) to limit search area

        Returns:
            Tuple (x, y) of buy button center in screen coordinates, or None
        """
        search_start_time = time.time()

        # Keep reference to full screenshot for buy button ROI extraction
        full_screenshot = process_screenshot.copy()

        # Crop to search region if specified
        region_offset = (0, 0)
        if search_region is not None:
            x, y, w, h = search_region
            item_h, item_w = process_item.shape[:2]

            # Check if search region is large enough for the template
            if w < item_w or h < item_h:
                if self.debug:
                    self.debug_log(f'[ITEM_SEARCH] Search region too small ({w}x{h}) for template ({item_w}x{item_h}), using full screenshot')
                search_region = None  # Fall back to full screenshot
                region_offset = (0, 0)
            else:
                region_offset = (x, y)
                process_screenshot = process_screenshot[y:y+h, x:x+w]
                if self.debug:
                    self.debug_log(f'[ITEM_SEARCH] Limited search to region: x={x}, y={y}, w={w}, h={h}')

        process_screenshot = cv2.GaussianBlur(process_screenshot, (3, 3), 0)
        process_item = cv2.GaussianBlur(process_item, (3, 3), 0)

        result = cv2.matchTemplate(process_screenshot, process_item, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        loc = np.where(result >= self.ITEM_MATCH_THRESHOLD)

        item_search_time = (time.time() - search_start_time) * 1000

        if self.debug:
            status = "FOUND" if loc[0].size > 0 else "not found"
            self.debug_log(f'[ITEM_SEARCH] Searching for "{item_name}" - confidence: {max_val:.3f}, {status}')
            self.debug_log(f'[ITEM_SEARCH] Search time: {item_search_time:.2f}ms')
            if loc[0].size > 0:
                self.debug_log(f'[ITEM_SEARCH] Top-left corner (in search area): x={max_loc[0]}, y={max_loc[1]}')

        if loc[0].size > 0:
            item_x = loc[1][0] + region_offset[0]  # Adjust for region offset
            item_y = loc[0][0] + region_offset[1]
            item_h, item_w = process_item.shape[:2]

            if self.debug:
                self.debug_log(f'[ITEM_SEARCH] Item found at (screen): ({self.window.left + item_x}, {self.window.top + item_y})')
                self.debug_log(f'[ITEM_SEARCH] Item size: {item_w}x{item_h}')

            # Buy button position: anchor is top-left of item, margin-left from getSearchRegions
            buy_info = self.getSearchRegions()['buy_btn']
            roi_x_start = item_x + buy_info['margin_x']  # From item's left edge (in screen coordinates)
            roi_y_start = item_y  # Same Y as item (in screen coordinates)
            roi_y_end = item_y + buy_info['height']  # Fixed height

            # Use full screenshot for ROI extraction (buy button is outside items search region)
            screenshot_h, screenshot_w = full_screenshot.shape[:2]
            roi_y_end = min(screenshot_h, roi_y_end)
            roi_y_start = max(0, roi_y_start)
            roi_x_start = max(0, roi_x_start)
            roi_x_end = min(screenshot_w, roi_x_start + buy_info['width'])

            # Extract ROI from full screenshot
            if roi_y_end > roi_y_start and roi_x_end > roi_x_start:
                roi = full_screenshot[roi_y_start:roi_y_end, roi_x_start:roi_x_end]
            else:
                if self.debug:
                    self.debug_log(f'[ITEM_SEARCH] Invalid ROI bounds: x={roi_x_start}-{roi_x_end}, y={roi_y_start}-{roi_y_end}, screenshot={screenshot_w}x{screenshot_h}')
                return None

            if roi.size > 0:
                if self.debug:
                    self.debug_log(f'[ITEM_SEARCH] ROI size: {roi.shape[1]}x{roi.shape[0]} (x: {roi_x_start}, y: {roi_y_start}-{roi_y_end})')

                roi_blurred = cv2.GaussianBlur(roi, (3, 3), 0)

                if self.buy_btn is not None:
                    buy_btn_h, buy_btn_w = self.buy_btn.shape[:2]
                    roi_h, roi_w = roi.shape[:2]

                    # Check if ROI is large enough for buy button template
                    if roi_w < buy_btn_w or roi_h < buy_btn_h:
                        if self.debug:
                            self.debug_log(f'[BUY_BUTTON] ROI too small ({roi_w}x{roi_h}) for buy button template ({buy_btn_w}x{buy_btn_h}), skipping')
                        return None

                    buy_search_start = time.time()
                    buy_btn_blurred = cv2.GaussianBlur(self.buy_btn, (3, 3), 0)
                    buy_result = cv2.matchTemplate(roi_blurred, buy_btn_blurred, cv2.TM_CCOEFF_NORMED)
                    _, buy_max_val, _, buy_max_loc = cv2.minMaxLoc(buy_result)
                    buy_search_time = (time.time() - buy_search_start) * 1000

                    if self.debug:
                        self.debug_log(f'[BUY_BUTTON] Search time: {buy_search_time:.2f}ms, confidence: {buy_max_val:.3f}')

                    if buy_max_val >= self.BUY_BUTTON_THRESHOLD:
                        btn_h, btn_w = self.buy_btn.shape[:2]
                        buy_top_left_x = roi_x_start + buy_max_loc[0]
                        buy_top_left_y = roi_y_start + buy_max_loc[1]
                        x = self.window.left + buy_top_left_x + btn_w // 2
                        y = self.window.top + buy_top_left_y + btn_h // 2

                        if self.debug:
                            self.debug_log(f'[BUY_BUTTON] Found! Top-left (screen): ({self.window.left + buy_top_left_x}, {self.window.top + buy_top_left_y})')
                            self.debug_log(f'[BUY_BUTTON] Center (screen): ({x}, {y})')

                        return (x, y)
                    elif self.debug:
                        self.debug_log(f'[BUY_BUTTON] Not found (confidence {buy_max_val:.3f} < threshold {self.BUY_BUTTON_THRESHOLD:.3f})')

                if self.sold_indicator is not None:
                    sold_blurred = cv2.GaussianBlur(self.sold_indicator, (3, 3), 0)
                    sold_result = cv2.matchTemplate(roi_blurred, sold_blurred, cv2.TM_CCOEFF_NORMED)
                    _, sold_max_val, _, _ = cv2.minMaxLoc(sold_result)
                    if sold_max_val >= self.SOLD_INDICATOR_THRESHOLD:
                        if self.debug:
                            self.debug_log(f'[SOLD] Item already sold (confidence: {sold_max_val:.3f})')
                        return None

            return None
        return None

    def findButtonPosition(self, process_screenshot, button_image, threshold=0.8, search_region=None, region_offset=(0, 0)):
        """Find a button in the screenshot and return its center position.

        Args:
            process_screenshot: Grayscale screenshot to search in
            button_image: Template image to find
            threshold: Minimum match confidence (0.0-1.0)
            search_region: Optional tuple (x, y, width, height) to limit search area
            region_offset: Offset to add to coordinates if searching in a cropped region

        Returns:
            Tuple (center_x, center_y) in screen coordinates, or None if not found
        """
        if button_image is None:
            return None

        search_start_time = time.time()

        # Crop to search region if specified
        if search_region is not None:
            x, y, w, h = search_region
            btn_h, btn_w = button_image.shape[:2]

            # Check if search region is large enough for the template
            if w < btn_w or h < btn_h:
                if self.debug:
                    self.debug_log(f'[MATCH] Search region too small ({w}x{h}) for template ({btn_w}x{btn_h}), using full screenshot')
                search_region = None  # Fall back to full screenshot
                region_offset = (0, 0)
            else:
                region_offset = (x, y)
                process_screenshot = process_screenshot[y:y+h, x:x+w]
                if self.debug:
                    self.debug_log(f'[MATCH] Limited search to region: x={x}, y={y}, w={w}, h={h}')

        process_screenshot = cv2.GaussianBlur(process_screenshot, (3, 3), 0)
        button_image = cv2.GaussianBlur(button_image, (3, 3), 0)

        result = cv2.matchTemplate(process_screenshot, button_image, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        search_time = (time.time() - search_start_time) * 1000  # Convert to ms

        if self.debug:
            self.debug_log(f'[MATCH] Template match result: confidence={max_val:.3f}, threshold={threshold:.3f}')
            self.debug_log(f'[MATCH] Top-left corner (in search area): x={max_loc[0]}, y={max_loc[1]}')
            self.debug_log(f'[MATCH] Search time: {search_time:.2f}ms')

        if max_val >= threshold:
            btn_h, btn_w = button_image.shape[:2]

            # Top-left corner in the search area
            top_left_x = max_loc[0] + region_offset[0]
            top_left_y = max_loc[1] + region_offset[1]

            # Center of the button in the search area
            center_x_in_area = top_left_x + btn_w // 2
            center_y_in_area = top_left_y + btn_h // 2

            # Convert to screen coordinates
            center_x = self.window.left + center_x_in_area
            center_y = self.window.top + center_y_in_area

            if self.debug:
                self.debug_log(f'[MATCH] Button size: {btn_w}x{btn_h}')
                self.debug_log(f'[MATCH] Top-left (screen): ({self.window.left + top_left_x}, {self.window.top + top_left_y})')
                self.debug_log(f'[MATCH] Center (screen): ({center_x}, {center_y})')
                self.debug_log(f'[MATCH] ✓ Match found! Returning center coordinates.')

            return (center_x, center_y)

        if self.debug:
            self.debug_log(f'[MATCH] ✗ No match found (confidence {max_val:.3f} < threshold {threshold:.3f})')

        return None

    def clickButtonByImage(self, button_image, fallback_x_ratio=None, fallback_y_ratio=None, threshold=0.8, max_retries=3, search_region=None):
        """Find and click a button using image detection, with optional fallback to fixed coordinates"""
        for attempt in range(max_retries):
            screenshot = self.takeScreenshot()
            if screenshot is None:
                continue
            process_screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)

            pos = self.findButtonPosition(process_screenshot, button_image, threshold, search_region=search_region)
            if pos is not None:
                x, y = pos
                offset_x, offset_y = self.randomClickOffset()
                x += offset_x
                y += offset_y
                pyautogui.moveTo(x, y)
                self.randomClick()
                return True

            time.sleep(0.1)

        if fallback_x_ratio is not None and fallback_y_ratio is not None:
            x = self.window.left + self.window.width * fallback_x_ratio
            y = self.window.top + self.window.height * fallback_y_ratio
            offset_x, offset_y = self.randomClickOffset()
            x += offset_x
            y += offset_y
            pyautogui.moveTo(x, y)
            self.randomClick()
            return True

        return False

    def clickBuy(self, pos):
        """Click the buy button at the given position.

        Note: We use position-based clicking here because all buy buttons look identical.
        The position is calculated by findItemPosition() to be at the buy button
        (right side of the row where the item was found).
        """
        if pos is None:
            return False

        self.randomDelay()
        x, y = pos
        offset_x, offset_y = self.randomClickOffset()
        x += offset_x
        y += offset_y
        pyautogui.moveTo(x, y)
        self.randomClick()
        time.sleep(self.MOUSE_SLEEP)
        self.clickConfirmBuy()
        return True

    def clickConfirmBuy(self):
        if self.debug:
            self.debug_log('[DEBUG] Clicking confirm buy button')
        self.randomDelay()
        confirm_buy_region = self.getSearchRegions()['confirm_buy_btn']
        if self.debug:
            x, y, w, h = confirm_buy_region
            self.debug_log(f'[DEBUG] Confirm buy search region: x={x}, y={y}, w={w}, h={h} (window: {self.window.width}x{self.window.height})')
        self.clickButtonByImage(
            self.confirm_buy_btn,
            fallback_x_ratio=0.55,
            fallback_y_ratio=0.70,
            threshold=self.BUTTON_MATCH_THRESHOLD,
            search_region=confirm_buy_region
        )
        time.sleep(self.MOUSE_SLEEP)
        time.sleep(self.SCREENSHOT_SLEEP)

    def clickRefresh(self):
        """Click refresh and handle the confirmation flow.

        Returns:
            True if refresh succeeded, False if user is out of gold
        """
        if self.debug:
            self.debug_log('[DEBUG] Clicking refresh button')
        self.randomDelay()
        refresh_region = self.getSearchRegions()['refresh_btn']
        self.clickButtonByImage(
            self.refresh_btn,
            fallback_x_ratio=0.20,
            fallback_y_ratio=0.90,
            threshold=self.BUTTON_MATCH_THRESHOLD,
            search_region=refresh_region
        )
        time.sleep(self.MOUSE_SLEEP)
        return self.clickConfirmRefresh()

    def clickConfirmRefresh(self):
        """Click confirm button and check for out-of-gold scenario.

        Returns:
            True if refresh succeeded, False if user is out of gold
        """
        if self.debug:
            self.debug_log('[DEBUG] Clicking confirm refresh button')
        self.randomDelay()
        confirm_region = self.getSearchRegions()['confirm_btn']
        self.clickButtonByImage(
            self.confirm_btn,
            fallback_x_ratio=0.58,
            fallback_y_ratio=0.65,
            threshold=self.BUTTON_MATCH_THRESHOLD,
            search_region=confirm_region
        )
        time.sleep(self.SCREENSHOT_SLEEP)

        if not self._checkOutOfSkystones():
            return False

        return True

    def _checkOutOfSkystones(self):
        """Check if another confirm button appeared (out of skystones).

        Returns:
            True if we're good to continue, False if user is out of skystones
        """
        screenshot = self.takeScreenshot()
        if screenshot is None:
            return True

        process_screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)

        confirm_region = self.getSearchRegions()['confirm_btn']
        confirm_pos = self.findButtonPosition(process_screenshot, self.confirm_btn, self.BUTTON_MATCH_THRESHOLD, search_region=confirm_region)

        if confirm_pos is not None:
            if self.debug:
                self.debug_log('[DEBUG] Detected another confirm button - possible out of skystones popup')

            x, y = confirm_pos
            offset_x, offset_y = self.randomClickOffset()
            pyautogui.moveTo(x + offset_x, y + offset_y)
            self.randomClick()
            time.sleep(0.5)

            screenshot = self.takeScreenshot()
            if screenshot is None:
                return True

            process_screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
            refresh_region = self.getSearchRegions()['refresh_btn']
            refresh_pos = self.findButtonPosition(process_screenshot, self.refresh_btn, self.BUTTON_MATCH_THRESHOLD, search_region=refresh_region)

            if refresh_pos is None:
                print('[INFO] Out of skystones! User has been redirected to shop. Stopping script.')
                return False
            else:
                if self.debug:
                    self.debug_log('[DEBUG] Refresh button still visible - was just a missed click')

        return True

    def scrollShop(self):
        x = self.window.left + self.window.width * 0.58
        y = self.window.top + self.window.height * 0.65

        base_scroll = self.SCROLL_RATIO
        extra_scroll = random.uniform(self.SCROLL_RANDOM_EXTRA_MIN, self.SCROLL_RANDOM_EXTRA_MAX)
        total_scroll = base_scroll + (base_scroll * extra_scroll)

        if self.debug:
            self.debug_log(f'[DEBUG] Scrolling shop (base: {base_scroll:.3f}, extra: {extra_scroll*100:.1f}%)')

        self.randomDelay()
        pyautogui.moveTo(x, y)
        time.sleep(0.1)
        pyautogui.mouseDown(button='left')
        time.sleep(0.1)
        pyautogui.moveTo(x, y - self.window.height * total_scroll)
        pyautogui.mouseUp(button='left')
        self.randomDelay()

class AppConfig():
    def __init__(self):
        self.RECOGNIZE_TITLES = {'Epic Seven',
                                 'BlueStacks App Player',
                                 'LDPlayer',
                                 'MuMu Player 12',
                                 '에픽세븐',
                                 'Google Play Games on PC Emulator'}
        self.ALL_ITEMS = [['item_covenant.png', 'Covenant bookmark', 184000],
                          ['item_mystic.png', 'Mystic medal', 280000],
                          ['item_friendship.png', 'Friendship bookmark', 18000]]
        self.MANDATORY_PATH = {'item_covenant.png', 'item_mystic.png'}
        self.DEBUG = False

class AutoRefreshGUI:
    def __init__(self, debug_mode=False, custom_size=None):
        self.app_config = AppConfig()
        self.app_config.DEBUG = debug_mode
        self.custom_size = custom_size
        self.root = tk.Tk()
        self.unite_bg_color = '#171717'
        self.unite_text_color = '#dddddd'
        self.root.config(bg=self.unite_bg_color)
        self.root.title('Epic7 Shopper')
        self.root.geometry('420x590')
        self.root.minsize(420, 540)

        icon_path = get_asset_path(os.path.join('assets', 'icon.ico'))
        self.root.iconbitmap(icon_path)
        self.title_name = ''
        self.ignore_path = {'item_friendship.png'}
        self.keep_image_open = []
        self.lock_start_button = False
        self.budget = ''

        app_title = tk.Label(self.root, text='Epic Seven shop refresh',
                             font=('Helvetica',24),
                             bg=self.unite_bg_color,
                             fg=self.unite_text_color)

        def onSelect(event):
            t_name = titles_combo_box.get()
            if t_name not in gw.getAllTitles():
                self.start_button.config(state=tk.DISABLED)
                return

            self.title_name = titles_combo_box.get()
            if not self.lock_start_button:
                self.start_button.config(state=tk.NORMAL)

        def onEnter(event):
            title = titles_combo_box.get()
            if title == '' or title not in gw.getAllTitles():
                self.start_button.config(state=tk.DISABLED)
                return
            self.title_name = titles_combo_box.get()
            if not self.lock_start_button:
                self.start_button.config(state=tk.NORMAL)

        titles = [title for title in self.app_config.RECOGNIZE_TITLES]
        titles.sort()

        titles_combo_box = ttk.Combobox(master=self.root,
                                    values=titles)
        titles_combo_box.config()
        titles_combo_box.bind('<<ComboboxSelected>>', onSelect)
        titles_combo_box.bind('<KeyRelease>', onEnter)

        special_frame = tk.Frame(self.root, bg=self.unite_bg_color)
        self.move_zerozero_cbv = tk.BooleanVar(value=True)
        self.debug_cbv = tk.BooleanVar(value=self.app_config.DEBUG)

        def setupSpecialSetting(label, value):
            frame = tk.Frame(special_frame, bg=self.unite_bg_color)
            special_label = tk.Label(master=frame,
                             text=label,
                             bg=self.unite_bg_color,
                             fg=self.unite_text_color,
                             font=('Helvetica',12))
            special_cb = tk.Checkbutton(master=frame,
                                font=('Helvetica',14),
                                variable=value,
                                bg=self.unite_bg_color)
            # Checkbutton automatically reflects BooleanVar value, but ensure it's synced
            if value.get():
                special_cb.select()
            special_label.pack(side=tk.LEFT)
            special_cb.pack(side=tk.RIGHT)
            frame.pack()

        setupSpecialSetting('Auto move emulator window to top left:', self.move_zerozero_cbv)
        setupSpecialSetting('Enable debug mode (writes to debug.log):', self.debug_cbv)

        setting_frame = tk.Frame(self.root)
        setting_frame.config(bg=self.unite_bg_color)
        def packSettingEntry(text, default = None):
            frame = tk.Frame(setting_frame, bg=self.unite_bg_color, pady=4)
            label = tk.Label(master=frame,
                             text=text,
                             bg=self.unite_bg_color,
                             fg=self.unite_text_color,
                             font=('Helvetica',12))
            entry = tk.Entry(master=frame,
                             bg='#333333',
                             fg=self.unite_text_color,
                             font=('Helvetica',12),
                             width=10)
            label.pack(side=tk.LEFT)
            if default or default == 0:
                entry.insert(0, default)

            entry.pack(side=tk.RIGHT)
            frame.pack()
            return entry

        self.start_button = tk.Button(master=self.root,
                                text='Start refresh',
                                font=('Helvetica',14),
                                state=tk.DISABLED,
                                command=self.startShopRefresh)
        if titles:
            for t in titles:
                if t in gw.getAllTitles():
                    self.title_name = t
                    titles_combo_box.set(self.title_name)
                    if not self.lock_start_button:
                        self.start_button.config(state=tk.NORMAL)
                    break
        if not self.title_name:
            google_play_title_pattern = re.compile(r"^(Epic Seven|에픽세븐) - \w+$", re.UNICODE)
            for t in gw.getAllTitles():
                if google_play_title_pattern.fullmatch(t):
                    self.title_name = t
                    titles_combo_box.set(self.title_name)
                    if not self.lock_start_button:
                        self.start_button.config(state=tk.NORMAL)
                    break

        app_title.pack(pady=(15,0))
        self.packMessage('Select emulator or type emulator\'s window title:')
        titles_combo_box.pack()
        self.packMessage('Select item that you are looking for:')
        GUI_ITEM_SIZE = (80, 80)
        items_frame = tk.Frame(self.root, bg=self.unite_bg_color)
        self.item_checkboxes = []

        for index, item in enumerate(self.app_config.ALL_ITEMS):
            img = Image.open(get_asset_path(os.path.join('assets', item[0])))
            img = img.resize(GUI_ITEM_SIZE, Image.Resampling.LANCZOS)
            self.keep_image_open.append(ImageTk.PhotoImage(img))
            self.packItemHorizontal(items_frame, index, item[0])

        items_frame.pack(pady=10)
        self.packMessage('Setting:', 18, (10,0))

        def validateInt(value):
            try:
                if value == '':
                    return True
                int_value = int(value)
                if int_value > 100000000:
                    return False
                else:
                    return value.isdigit()
            except:
                return False

        valid_int_reg = self.root.register(validateInt)
        self.limit_spend_entry = packSettingEntry('Skystone budget (leave empty for unlimited):', None)
        self.limit_spend_entry.config(validate='key', validatecommand=(valid_int_reg, '%P'))

        special_frame.pack(pady=(0,5))
        setting_frame.pack()

        self.start_button.pack(pady=(30,0))
        self.root.mainloop()

    def packItemHorizontal(self, parent_frame, index, path):
        """Pack item with icon on top and large toggle button below, arranged horizontally"""

        is_mandatory = path in self.app_config.MANDATORY_PATH
        is_checked = is_mandatory or path not in self.ignore_path
        item_frame = tk.Frame(parent_frame, bg=self.unite_bg_color, padx=15)
        image_label = tk.Label(master=item_frame, image=self.keep_image_open[index], bg='#FFBF00')
        image_label.pack(side=tk.TOP, pady=(0, 5))
        btn_text = tk.StringVar(value='✓' if is_checked else '✗')
        btn_color = '#4CAF50' if is_checked else '#666666'

        def toggle():
            if is_mandatory:
                return
            current = btn_text.get()
            if current == '✓':
                btn_text.set('✗')
                toggle_btn.config(bg='#666666', activebackground='#888888')
                self.ignore_path.add(path)
            else:
                btn_text.set('✓')
                toggle_btn.config(bg='#4CAF50', activebackground='#66BB6A')
                self.ignore_path.discard(path)

        toggle_btn = tk.Button(
            master=item_frame,
            textvariable=btn_text,
            command=toggle,
            font=('Helvetica', 24, 'bold'),
            width=2,
            height=1,
            bg=btn_color,
            fg='white',
            activebackground='#66BB6A' if is_checked else '#888888',
            activeforeground='white',
            relief=tk.FLAT,
            cursor='hand2'
        )
        toggle_btn.pack(side=tk.TOP, pady=5)

        if is_mandatory:
            toggle_btn.config(state=tk.DISABLED, cursor='arrow')

        item_frame.pack(side=tk.LEFT, padx=10)

    def packMessage(self, message, text_size=14, pady=10):
        new_label = tk.Label(self.root, text=message, font=('Helvetica',text_size), bg=self.unite_bg_color, fg=self.unite_text_color)
        new_label.pack(pady=pady)
        return new_label

    def refreshComplete(self):
        print('Terminated!')
        self.root.title('Epic7 Shopper')
        self.start_button.config(state=tk.NORMAL)
        self.lock_start_button = False

    def startShopRefresh(self):
        self.root.title('Press ESC to stop!')
        self.lock_start_button = True
        self.start_button.config(state=tk.DISABLED)
        # Update debug mode from checkbox
        self.app_config.DEBUG = self.debug_cbv.get()
        self.ssr = SecretShopRefresh(
            title_name=self.title_name,
            callback=self.refreshComplete,
            debug=self.app_config.DEBUG,
            custom_size=self.custom_size
        )

        self.ssr.tk_instance = self.root

        if not self.move_zerozero_cbv.get():
            self.ssr.allow_move = True

        for item in self.app_config.ALL_ITEMS:
            if item[0] not in self.ignore_path:
                self.ssr.addShopItem(path=item[0], name=item[1], price=item[2])

        if self.limit_spend_entry.get() != '':
            self.ssr.budget = int(self.limit_spend_entry.get())

        print('refresh shop start!')
        print('Budget:', self.ssr.budget if self.ssr.budget else 'Unlimited')
        if self.ssr.budget and self.ssr.budget >= 1000:
            ev_cost = 1691.04536 * int(self.ssr.budget) * 2
            ev_cov = 0.006602509 * int(self.ssr.budget) * 2
            ev_mys = 0.001700646 * int(self.ssr.budget) * 2
            print('Approximation based on budget:')
            print(f'Cost: {int(ev_cost):,}')
            print(f'Cov: {ev_cov}')
            print(f'mys: {ev_mys}')
        print()

        self.ssr.start()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Epic Seven Secret Shop Auto Refresh')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode with detailed output')
    parser.add_argument('--size', type=str, help='Custom reference size for assets (e.g., --size=1920x1080)')
    parser.add_argument('--info', action='store_true', help='Show window size and scaling info, then exit')
    args = parser.parse_args()

    custom_width, custom_height = None, None
    if args.size:
        try:
            parts = args.size.lower().split('x')
            custom_width = int(parts[0])
            custom_height = int(parts[1])
            print(f'[CONFIG] Custom reference size: {custom_width}x{custom_height}')
        except:
            print(f'[ERROR] Invalid size format: {args.size}. Use format: --size=WIDTHxHEIGHT')
            exit(1)

    if args.info:
        print('\n=== Epic7 Shopper - Window Info ===\n')
        print('Available windows:')
        for title in gw.getAllTitles():
            if title.strip():
                print(f'  - {title}')

        print(f'\nDefault reference size (for included assets): {SecretShopRefresh.REFERENCE_WIDTH}x{SecretShopRefresh.REFERENCE_HEIGHT}')

        if custom_width and custom_height:
            print(f'Custom reference size (your assets): {custom_width}x{custom_height}')

        print('\nTo check scaling for a specific window, run the app normally.')
        print('The scale factor will be printed when you start refreshing.')
        exit(0)

    if args.debug:
        print('[DEBUG MODE ENABLED]')

    gui = AutoRefreshGUI(debug_mode=args.debug, custom_size=(custom_width, custom_height) if args.size else None)