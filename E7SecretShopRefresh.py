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
from pygetwindow import PyGetWindowException
import cv2
import numpy as np
import keyboard
import mss
import random
import logging

from config import get_config, get_search_regions_for_aspect, save_default_config

logger = logging.getLogger(__name__)
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
        return sum(item.price * item.count for item in self.items.values())

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

    CLICK_OFFSET_MAX = 10
    DOUBLE_CLICK_CHANCE = 0.3
    SCROLL_RANDOM_EXTRA_MIN = 0.0
    SCROLL_RANDOM_EXTRA_MAX = 0.15

    SCROLL_RATIO = 0.277
    SCROLL_START_X_RATIO = 0.58
    SCROLL_START_Y_RATIO = 0.65
    ITEM_MATCH_THRESHOLD = 0.75
    BUTTON_MATCH_THRESHOLD = 0.75
    SHOP_CHECK_THRESHOLD = 0.7
    BUY_BUTTON_THRESHOLD = 0.7
    SOLD_INDICATOR_THRESHOLD = 0.7

    def __init__(self, title_name: str, callback = None, tk_instance: tk = None, budget: int = None, allow_move: bool = False, debug: bool = False, join_thread: bool = False, custom_size: tuple = None, save_screenshots: bool = False):
        self._config = get_config()
        self._apply_config()

        self.debug = debug
        self.save_screenshots = save_screenshots
        self.debug_log_file = None
        self._debug_log_counter = 0
        if self.debug:
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

        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0
        self._cached_search_regions = None
        self._cached_aspect_ratio = None
        self._cached_aspect_window_size = None
        self._cached_search_regions_window_size = None
        self._cached_window_size = None
        self._cached_blurred_buttons = {}
        self._cached_blurred_items = {}
        self._cached_window_props = None
        self._cached_screenshot_region = None
        self._mss_instance = None

    def _getWindowProps(self):
        """Get cached window properties (left, top, width, height)"""
        current_pos_size = (self.window.left, self.window.top, self.window.width, self.window.height)
        if self._cached_window_props and self._cached_window_props == current_pos_size:
            return self._cached_window_props
        self._cached_window_props = current_pos_size
        return (self.window.left, self.window.top, self.window.width, self.window.height)
    def _apply_config(self):
        """Apply configuration values from config.json (if exists) to instance variables"""
        cfg = self._config

        timing = cfg.get('timing', {})
        self.MOUSE_SLEEP = timing.get('mouse_sleep', self.MOUSE_SLEEP)
        self.SCREENSHOT_SLEEP = timing.get('screenshot_sleep', self.SCREENSHOT_SLEEP)

        anti_det = cfg.get('anti_detection', {})
        self.CLICK_OFFSET_MAX = anti_det.get('click_offset_max', self.CLICK_OFFSET_MAX)
        self.DOUBLE_CLICK_CHANCE = anti_det.get('double_click_chance', self.DOUBLE_CLICK_CHANCE)
        self.SCROLL_RANDOM_EXTRA_MIN = anti_det.get('scroll_random_extra_min', self.SCROLL_RANDOM_EXTRA_MIN)
        self.SCROLL_RANDOM_EXTRA_MAX = anti_det.get('scroll_random_extra_max', self.SCROLL_RANDOM_EXTRA_MAX)

        scrolling = cfg.get('scrolling', {})
        self.SCROLL_RATIO = scrolling.get('scroll_ratio', self.SCROLL_RATIO)
        self.SCROLL_START_X_RATIO = scrolling.get('scroll_start_x_ratio', self.SCROLL_START_X_RATIO)
        self.SCROLL_START_Y_RATIO = scrolling.get('scroll_start_y_ratio', self.SCROLL_START_Y_RATIO)

        thresholds = cfg.get('thresholds', {})
        self.ITEM_MATCH_THRESHOLD = thresholds.get('item_match', self.ITEM_MATCH_THRESHOLD)
        self.BUTTON_MATCH_THRESHOLD = thresholds.get('button_match', self.BUTTON_MATCH_THRESHOLD)
        self.SHOP_CHECK_THRESHOLD = thresholds.get('shop_check', self.SHOP_CHECK_THRESHOLD)
        self.BUY_BUTTON_THRESHOLD = thresholds.get('buy_button', self.BUY_BUTTON_THRESHOLD)
        self.SOLD_INDICATOR_THRESHOLD = thresholds.get('sold_indicator', self.SOLD_INDICATOR_THRESHOLD)

        reference = cfg.get('reference', {})
        self.REFERENCE_WIDTH = reference.get('width', self.REFERENCE_WIDTH)
        self.REFERENCE_HEIGHT = reference.get('height', self.REFERENCE_HEIGHT)

    def debug_log(self, message):
        """Write debug message to both console and debug.log file"""
        if self.debug:
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_message = f'[{timestamp}] {message}'
            print(log_message)
            if self.debug_log_file:
                self.debug_log_file.write(log_message + '\n')
                self._debug_log_counter += 1
                if self._debug_log_counter % 10 == 0 or 'ERROR' in message or 'WARNING' in message:
                    self.debug_log_file.flush()

    def __del__(self):
        """Cleanup: close debug log file if open"""
        self._closeDebugLog()


    def randomClickOffset(self):
        """Get random x,y offset for anti-detection click variation"""
        offset_x = random.randint(-self.CLICK_OFFSET_MAX, self.CLICK_OFFSET_MAX)
        offset_y = random.randint(-self.CLICK_OFFSET_MAX, self.CLICK_OFFSET_MAX)
        if self.debug:
            self.debug_log(f'[DEBUG] Click offset: ({offset_x:+d}, {offset_y:+d}) pixels')
        return offset_x, offset_y

    def randomClick(self):
        """Perform a click with random single/double for anti-detection"""
        if not self.loop_active:
            return
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
                aspect_ratio = self.getAspectRatio()
                threshold = self.SHOP_CHECK_THRESHOLD
                if aspect_ratio == '16:9':
                    threshold = max(0.65, threshold - 0.05)
                pos = self.findButtonPosition(process_screenshot, self.refresh_btn, threshold=threshold, search_region=refresh_region, button_name="refresh button")
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

    def getAspectRatio(self):
        """Detect the aspect ratio category of the current window.

        Returns:
            str: '21:9' for ultrawide, '16:9' for standard widescreen, or 'other'
        """
        current_size = (self.window.width, self.window.height)
        if (self._cached_aspect_ratio is not None and
            self._cached_aspect_window_size == current_size):
            return self._cached_aspect_ratio

        aspect_ratio = self.window.width / self.window.height
        result = '21:9' if aspect_ratio >= 2.0 else ('16:9' if aspect_ratio >= 1.6 else 'other')

        self._cached_aspect_ratio = result
        self._cached_aspect_window_size = current_size

        return result

    def getSearchRegions(self):
        """Calculate optimized search regions based on reference window size.

        Uses independent width_scale and height_scale for X/Y dimensions to properly
        handle different aspect ratios. Different measurements and reference resolutions
        are used for 21:9 vs 16:9:
        - 21:9: uses 3840x1600 reference
        - 16:9: uses 1920x1080 reference

        Returns:
            Dict with region definitions for each UI element:
            - refresh_btn: bottom-left region
            - confirm_btn: bottom-middle region (also catches out-of-gold popup)
            - items_search: left-anchored vertical strip
            - buy_btn: relative to found item (handled separately)
            - confirm_buy_btn: bottom-middle region
        """
        current_size = (self.window.width, self.window.height)
        if (self._cached_search_regions is not None and
            self._cached_search_regions_window_size == current_size):
            return self._cached_search_regions

        aspect_ratio = self.getAspectRatio()

        if aspect_ratio == '16:9':
            ref_width = 1920
            ref_height = 1080
        else:
            ref_width = self.REFERENCE_WIDTH
            ref_height = self.REFERENCE_HEIGHT

        width_scale = self.window.width / ref_width
        height_scale = self.window.height / ref_height

        if self.debug:
            self.debug_log(f'[SEARCH_REGIONS] Aspect ratio: {aspect_ratio}, using reference: {ref_width}x{ref_height}')
            self.debug_log(f'[SEARCH_REGIONS] Window: {self.window.width}x{self.window.height}, scales: width={width_scale:.4f}, height={height_scale:.4f}')

        sr_cfg = get_search_regions_for_aspect(self._config, aspect_ratio)

        refresh_cfg = sr_cfg.get('refresh_button', {})
        refresh_w_ref = refresh_cfg.get('width', 900)
        refresh_h_ref = refresh_cfg.get('height', 275)
        refresh_margin_left_ref = refresh_cfg.get('margin_left', 540)

        confirm_cfg = sr_cfg.get('confirm_button', {})
        confirm_w_ref = confirm_cfg.get('width', 500)
        confirm_h_ref = confirm_cfg.get('height', 500)
        confirm_margin_bottom_ref = confirm_cfg.get('margin_bottom', 225)
        confirm_margin_right_ref = confirm_cfg.get('margin_right', 250 if aspect_ratio != '16:9' else 0)

        items_cfg = sr_cfg.get('items_search', {})
        items_x_ref = items_cfg.get('x', 1680)
        items_w_ref = items_cfg.get('width', 300)

        buy_cfg = sr_cfg.get('buy_button', {})
        buy_margin_x_ref = buy_cfg.get('margin_x', 1139)
        buy_w_ref = buy_cfg.get('width', 450)
        buy_h_ref = buy_cfg.get('height', 250)

        confirm_buy_cfg = sr_cfg.get('confirm_buy_button', {})
        confirm_buy_w_ref = confirm_buy_cfg.get('width', 600)
        confirm_buy_h_ref = confirm_buy_cfg.get('height', 230)
        confirm_buy_margin_bottom_ref = confirm_buy_cfg.get('margin_bottom', 350)
        confirm_buy_offset_right_ref = confirm_buy_cfg.get('offset_right', 15)

        regions = {}

        refresh_w = int(refresh_w_ref * width_scale)
        refresh_h = int(refresh_h_ref * height_scale)
        refresh_margin_left = int(refresh_margin_left_ref * width_scale)
        regions['refresh_btn'] = (refresh_margin_left, self.window.height - refresh_h, refresh_w, refresh_h)

        confirm_w = int(confirm_w_ref * width_scale)
        confirm_h = int(confirm_h_ref * height_scale)
        confirm_margin_right = int(confirm_margin_right_ref * width_scale)
        confirm_x = self.window.width // 2 + confirm_margin_right
        confirm_y = self.window.height - int(confirm_margin_bottom_ref * height_scale) - confirm_h
        regions['confirm_btn'] = (confirm_x, confirm_y, confirm_w, confirm_h)

        items_x = int(items_x_ref * width_scale)
        items_w = int(items_w_ref * width_scale)
        items_h = self.window.height
        regions['items_search'] = (items_x, 0, items_w, items_h)

        buy_margin_x = int(buy_margin_x_ref * width_scale)
        buy_w = int(buy_w_ref * width_scale)
        buy_h = int(buy_h_ref * height_scale)
        regions['buy_btn'] = {'margin_x': buy_margin_x, 'width': buy_w, 'height': buy_h,
                             'note': 'Relative to found item - calculated dynamically in findItemPosition()'}

        confirm_buy_w = int(confirm_buy_w_ref * width_scale)
        confirm_buy_h = int(confirm_buy_h_ref * height_scale)
        confirm_buy_margin_bottom = int(confirm_buy_margin_bottom_ref * height_scale)
        confirm_buy_offset_right = int(confirm_buy_offset_right_ref * width_scale)
        confirm_buy_x = self.window.width // 2 + confirm_buy_offset_right
        confirm_buy_y = self.window.height - confirm_buy_margin_bottom - confirm_buy_h
        regions['confirm_buy_btn'] = (confirm_buy_x, confirm_buy_y, confirm_buy_w, confirm_buy_h)

        self._cached_search_regions = regions
        self._cached_search_regions_window_size = current_size

        return regions

    def updateScaleFactor(self):
        """Calculate scale factor based on current window size vs reference resolution

        Assets (buttons, items) are ALWAYS scaled from 3840x1600 reference, regardless of aspect ratio.
        Uses height scale for buttons and items (assets) as it better matches the game's UI scaling.
        Search regions use independent width/height scaling based on aspect ratio (1920x1080 for 16:9, 3840x1600 for 21:9).

        If scale factor is below 0.85, resizes the window to achieve at least 0.85 scaling.
        """
        asset_ref_height = 1600

        aspect_ratio = self.getAspectRatio()

        height_scale = self.window.height / asset_ref_height
        self.scale_factor = height_scale

        if aspect_ratio == '16:9':
            target_height = 900
            target_scale = target_height / asset_ref_height
        else:
            target_height = 1000
            target_scale = target_height / asset_ref_height

        if self.scale_factor < target_scale:
            if aspect_ratio == '21:9':
                current_aspect = self.window.width / self.window.height
                target_width = int(target_height * current_aspect)
            elif aspect_ratio == '16:9':
                target_width = int(target_height * (16 / 9))
            else:
                current_aspect = self.window.width / self.window.height
                target_width = int(target_height * current_aspect)

            if self.debug:
                self.debug_log(f'[WINDOW_RESIZE] Scale factor {self.scale_factor:.3f} below {target_scale}, resizing {aspect_ratio} window from {self.window.width}x{self.window.height} to {target_width}x{target_height}')

            try:
                self.window.resizeTo(target_width, target_height)
                windows = gw.getWindowsWithTitle(self.title_name)
                self.window = next((w for w in windows if w.title == self.title_name), self.window)
                height_scale = self.window.height / asset_ref_height
                self.scale_factor = height_scale
                print(f'Window resized to {self.window.width}x{self.window.height} (scale: {self.scale_factor:.3f})')
            except Exception as e:
                if self.debug:
                    self.debug_log(f'[WINDOW_RESIZE] Failed to resize window: {e}')
                print(f'Warning: Could not resize window: {e}')
        print(f'Window size: {self.window.width}x{self.window.height} (aspect: {aspect_ratio})')
        print(f'Asset scale factor (from 3840x1600, height-based): {self.scale_factor:.3f}')

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

        self._cached_blurred_buttons.clear()
        self._cached_blurred_items.clear()

    def scaleImage(self, image, custom_scale=None):
        """Scale an image by the current scale factor (or custom scale if provided)"""
        if image is None:
            return None
        scale = custom_scale if custom_scale is not None else self.scale_factor
        new_width = int(image.shape[1] * scale)
        new_height = int(image.shape[0] * scale)
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
            if keyboard.is_pressed('esc'):
                self.loop_active = False
                break
            time.sleep(0.01)
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

        if hasattr(self, '_mss_instance') and self._mss_instance is not None:
            try:
                self._mss_instance.close()
            except Exception:
                logger.debug("error closing _mss_instance", exc_info=True)
            self._mss_instance = None

    def _cleanupAndExit(self, hint=None):
        """Clean up resources and exit the refresh loop"""
        if hint:
            hint.destroy()
        self.rs_instance.writeToCSV()
        self.loop_active = False
        self.loop_finish = True
        self._closeDebugLog()

        if self.tk_instance:
            self._showSummaryWindow()

        self.callback()

    def _showSummaryWindow(self):
        """Display a summary window showing refresh count and items found"""
        bg_color = '#1a1a1a'
        bg_secondary = '#252525'
        fg_color = '#f5f5f5'
        fg_secondary = '#a3a3a3'

        summary = tk.Toplevel(self.tk_instance)
        summary.title('Shopping Summary')
        summary.geometry('400x500')
        summary.iconbitmap(get_asset_path(os.path.join('assets', 'icon.ico')))
        summary.config(bg=bg_color)

        summary.update_idletasks()
        x = (summary.winfo_screenwidth() // 2) - (summary.winfo_width() // 2)
        y = (summary.winfo_screenheight() // 2) - (summary.winfo_height() // 2)
        summary.geometry(f'+{x}+{y}')

        title_frame = tk.Frame(summary, bg=bg_color, pady=20)
        title_frame.pack(fill=tk.X)
        tk.Label(title_frame, text='Shopping Summary', bg=bg_color, fg=fg_color,
                font=('Segoe UI', 18, 'bold')).pack()

        refresh_frame = tk.Frame(summary, bg=bg_secondary, padx=20, pady=15)
        refresh_frame.pack(fill=tk.X, padx=20, pady=(0, 15))
        tk.Label(refresh_frame, text='Total Refreshes', bg=bg_secondary, fg=fg_secondary,
                font=('Segoe UI', 10)).pack(anchor='w')
        tk.Label(refresh_frame, text=str(self.rs_instance.refresh_count), bg=bg_secondary,
                fg='#88FF88', font=('Segoe UI', 24, 'bold')).pack(anchor='w', pady=(5, 0))

        items_frame = tk.Frame(summary, bg=bg_secondary, padx=20, pady=15)
        items_frame.pack(fill=tk.X, padx=20, pady=(0, 15))
        tk.Label(items_frame, text='Items Found', bg=bg_secondary, fg=fg_secondary,
                font=('Segoe UI', 10)).pack(anchor='w')

        items_content = tk.Frame(items_frame, bg=bg_secondary)
        items_content.pack(fill=tk.X, pady=(10, 0))

        total_items = 0
        for name, shop_item in self.rs_instance.getInventory().items():
            count = shop_item.count
            total_items += count
            item_row = tk.Frame(items_content, bg=bg_secondary)
            item_row.pack(fill=tk.X, pady=5)
            tk.Label(item_row, text=name, bg=bg_secondary, fg=fg_color,
                    font=('Segoe UI', 11)).pack(side=tk.LEFT)
            tk.Label(item_row, text=str(count), bg=bg_secondary, fg='#FFBF00',
                    font=('Segoe UI', 11, 'bold')).pack(side=tk.RIGHT)

        if total_items == 0:
            tk.Label(items_content, text='No items purchased', bg=bg_secondary, fg=fg_secondary,
                    font=('Segoe UI', 10, 'italic')).pack(pady=10)

        total_cost = self.rs_instance.getTotalCost()
        if total_cost > 0:
            cost_frame = tk.Frame(summary, bg=bg_secondary, padx=20, pady=15)
            cost_frame.pack(fill=tk.X, padx=20, pady=(0, 15))
            tk.Label(cost_frame, text='Total Gold Spent', bg=bg_secondary, fg=fg_secondary,
                    font=('Segoe UI', 10)).pack(anchor='w')
            tk.Label(cost_frame, text=f'{total_cost:,}', bg=bg_secondary,
                    fg='#FF6B6B', font=('Segoe UI', 18, 'bold')).pack(anchor='w', pady=(5, 0))

        button_frame = tk.Frame(summary, bg=bg_color, pady=20)
        button_frame.pack(fill=tk.X)
        close_btn = tk.Button(button_frame, text='Close', command=summary.destroy,
                             bg='#6366f1', fg='white', font=('Segoe UI', 11, 'bold'),
                             padx=30, pady=10, relief=tk.FLAT, cursor='hand2')
        close_btn.pack()

        close_btn.bind('<Enter>', lambda e: close_btn.config(bg='#818cf8'))
        close_btn.bind('<Leave>', lambda e: close_btn.config(bg='#6366f1'))

        summary.lift()
        summary.focus_force()
        summary.attributes('-topmost', True)
        summary.after(100, lambda: summary.attributes('-topmost', False))

    def _shouldContinueLoop(self):
        """Check if the loop should continue running"""
        return self.loop_active and self.window.title == self.title_name

    def shopRefreshLoop(self):
        """Main shop refresh loop - handles the entire refresh cycle"""
        try:
            if self.window.isMinimized:
                self.window.restore()
            if not self.allow_move and not self.window.isMaximized:
                self.window.moveTo(0, 0)
            self.updateScaleFactor()
            self.scaleAllAssets()
        except Exception as e:
            print(e)
            self._cleanupAndExit()
            return

        hint, mini_labels, refresh_label = None, None, None
        if self.tk_instance:
            selected_path = self.rs_instance.getPath()
            mini_images = []
            for path in selected_path:
                img = Image.open(get_asset_path(os.path.join('assets', path)))
                img = img.resize((45, 45))
                img = ImageTk.PhotoImage(img)
                mini_images.append(img)
            hint, mini_labels, refresh_label = self.showMiniDisplays(mini_images)

        def updateMiniDisplay():
            if mini_labels:
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
            self._cleanupAndExit(hint)
            return

        try:
            try:
                self.window.activate()
            except Exception as e:
                print(e)

            self.rs_instance.updateTime()
            sliding_time = max(0.7 + self.SCREENSHOT_SLEEP, 1)
            loop_count = 0

            while self._shouldContinueLoop():
                loop_start_time = time.time()
                loop_count += 1

                if self.debug:
                    aspect_ratio = self.getAspectRatio()
                    self.debug_log(f'\n[DEBUG] ══════ Loop #{loop_count} started ══════')
                    self.debug_log(f'[DEBUG] Window size: {self.window.width}x{self.window.height} (aspect ratio: {self.window.width/self.window.height:.4f}, detected: {aspect_ratio})')

                if not self.isInShop():
                    if not self.waitForShop():
                        break
                    continue

                if self.budget and self.rs_instance.refresh_count >= self.budget // 3:
                    break

                bought = set()
                time.sleep(sliding_time)
                screenshot = self.takeScreenshot()
                if screenshot is None:
                    break
                process_screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
                process_screenshot = self._buyAvailableItems(process_screenshot, bought)
                if hint:
                    updateMiniDisplay()
                if not self._shouldContinueLoop():
                    break

                self.scrollShop()
                time.sleep(max(0.3, self.SCREENSHOT_SLEEP))
                if not self._shouldContinueLoop():
                    break

                screenshot = self.takeScreenshot()
                if screenshot is None:
                    break
                process_screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
                self._buyAvailableItems(process_screenshot, bought, ' (after scroll)')
                if hint:
                    updateMiniDisplay()
                if not self._shouldContinueLoop():
                    break

                refresh_success = self.clickRefresh()
                if not refresh_success:
                    if hint:
                        refresh_label.config(text='Out of skystones!', fg='#FF6666')
                    break

                self.rs_instance.incrementRefreshCount()
                if hint:
                    updateRefreshCounter()

                if self.debug:
                    loop_duration = time.time() - loop_start_time
                    self.debug_log(f'[DEBUG] ══════ Loop #{loop_count} completed in {loop_duration:.2f}s ══════')

                time.sleep(self.MOUSE_SLEEP)

        except Exception as e:
            print(e)
            self._cleanupAndExit(hint)
            return

        self._cleanupAndExit(hint)

    def showMiniDisplays(self, mini_images):
        bg_color = '#171717'
        fg_color = '#dddddd'

        if self.tk_instance is None:
            return None, None, None
        hint = tk.Toplevel(self.tk_instance)
        hint.geometry(r'220x250+%d+%d' % (self.window.left, self.window.top))
        hint.title('Shopping')
        hint.iconbitmap(get_asset_path(os.path.join('assets', 'icon.ico')))
        hint.attributes('-topmost', True)
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

    def _saveDebugScreenshot(self, full_screenshot, search_region, search_label, color_bgr, additional_rects=None):
        """Save a debug screenshot with marked search area

        Args:
            full_screenshot: Full grayscale screenshot
            search_region: Tuple (x, y, width, height) of search area
            search_label: Label for the screenshot filename
            color_bgr: BGR color tuple for the rectangle (e.g., (255, 0, 0) for red)
            additional_rects: Optional list of tuples ((x, y, w, h), color) for additional rectangles
        """
        if not self.save_screenshots:
            return

        debug_dir = 'debug'
        os.makedirs(debug_dir, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]

        if len(full_screenshot.shape) == 2:
            screenshot_bgr = cv2.cvtColor(full_screenshot, cv2.COLOR_GRAY2BGR)
        else:
            screenshot_bgr = full_screenshot.copy()

        if search_region:
            x, y, w, h = search_region
            cv2.rectangle(screenshot_bgr, (x, y), (x + w, y + h), color_bgr, 3)

        if additional_rects:
            for rect, rect_color in additional_rects:
                if rect:
                    rx, ry, rw, rh = rect
                    cv2.rectangle(screenshot_bgr, (rx, ry), (rx + rw, ry + rh), rect_color, 2)

        filename = os.path.join(debug_dir, f'{search_label}_{timestamp}.png')
        cv2.imwrite(filename, screenshot_bgr)
        self.debug_log(f'[DEBUG] Saved screenshot: {filename}')

    def takeScreenshot(self, activate_window=True):
        """Take a screenshot of the game window using mss for faster performance.

        Args:
            activate_window: Whether to activate the window before taking screenshot (default: True)
        """
        try:
            if activate_window:
                try:
                    self.window.activate()
                except PyGetWindowException as e:
                    self.debug_log(f'[WARNING] Failed to activate window: {e}')

            current_size = (self.window.width, self.window.height)
            if (self._cached_screenshot_region is None or
                self._cached_window_size != current_size):
                left, top = self.window.left, self.window.top
                width, height = self.window.width, self.window.height
                self._cached_window_props = (left, top, width, height)
                self._cached_screenshot_region = {"top": top, "left": left, "width": width, "height": height}
                self._cached_window_size = current_size

            if self._mss_instance is None:
                self._mss_instance = mss.mss()
            screenshot = self._mss_instance.grab(self._cached_screenshot_region)
            screenshot = np.array(screenshot)
            screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2BGR)
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

        full_screenshot = process_screenshot

        region_offset = (0, 0)
        if search_region is not None:
            x, y, w, h = search_region
            item_h, item_w = process_item.shape[:2]

            if w < item_w or h < item_h:
                if self.debug:
                    self.debug_log(f'[ITEM_SEARCH] Search region too small ({w}x{h}) for template ({item_w}x{item_h}), using full screenshot')
                search_region = None
                region_offset = (0, 0)
            else:
                region_offset = (x, y)
                process_screenshot = process_screenshot[y:y+h, x:x+w]
                if self.debug:
                    self.debug_log(f'[ITEM_SEARCH] Limited search to region: x={x}, y={y}, w={w}, h={h}')

        process_screenshot = cv2.GaussianBlur(process_screenshot, (3, 3), 0)

        if item_name not in self._cached_blurred_items:
            self._cached_blurred_items[item_name] = cv2.GaussianBlur(process_item, (3, 3), 0)
        process_item_blurred = self._cached_blurred_items[item_name]

        result = cv2.matchTemplate(process_screenshot, process_item_blurred, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        threshold = self.ITEM_MATCH_THRESHOLD
        item_name_lower = item_name.lower()
        if 'mystic' in item_name_lower:
            threshold = max(0.70, self.ITEM_MATCH_THRESHOLD - 0.05)
            if self.debug:
                self.debug_log(f'[ITEM_SEARCH] Using lower threshold for mystic item: {threshold:.3f} (normal: {self.ITEM_MATCH_THRESHOLD:.3f})')

        loc = np.where(result >= threshold)

        item_search_time = (time.time() - search_start_time) * 1000

        if self.debug:
            status = "FOUND" if loc[0].size > 0 else "not found"
            self.debug_log(f'[ITEM_SEARCH] Searching for "{item_name}" - confidence: {max_val:.3f}, threshold: {threshold:.3f}, {status}')
            self.debug_log(f'[ITEM_SEARCH] Search time: {item_search_time:.2f}ms')
            if loc[0].size > 0:
                self.debug_log(f'[ITEM_SEARCH] Top-left corner (in search area): x={max_loc[0]}, y={max_loc[1]}')

        if loc[0].size > 0:
            item_x = loc[1][0] + region_offset[0]
            item_y = loc[0][0] + region_offset[1]
            item_h, item_w = process_item_blurred.shape[:2]

            if self.debug:
                win_left, win_top, _, _ = self._getWindowProps()
                self.debug_log(f'[ITEM_SEARCH] Item found at (screen): ({win_left + item_x}, {win_top + item_y})')
                self.debug_log(f'[ITEM_SEARCH] Item size: {item_w}x{item_h}')

            if self.save_screenshots:
                fresh_screenshot = self.takeScreenshot(activate_window=False)
                if fresh_screenshot is not None:
                    fresh_screenshot_gray = cv2.cvtColor(fresh_screenshot, cv2.COLOR_BGR2GRAY)
                    additional_rects = [
                        ((item_x, item_y, item_w, item_h), (0, 255, 0))
                    ]
                    self._saveDebugScreenshot(fresh_screenshot_gray, search_region,
                                            f'search_item_{item_name.replace(" ", "_")}',
                                            (0, 255, 0),
                                            additional_rects)

            buy_info = self.getSearchRegions()['buy_btn']
            roi_x_start = item_x + buy_info['margin_x']
            roi_y_start = item_y

            if self.buy_btn is not None:
                buy_btn_h, buy_btn_w = self.buy_btn.shape[:2]
                roi_width = max(buy_info['width'], buy_btn_w + 20)
                roi_height = max(buy_info['height'], buy_btn_h + 20)
            else:
                roi_width = buy_info['width']
                roi_height = buy_info['height']

            roi_y_end = item_y + roi_height

            screenshot_h, screenshot_w = full_screenshot.shape[:2]
            roi_y_end = min(screenshot_h, roi_y_end)
            roi_y_start = max(0, roi_y_start)
            roi_x_start = max(0, roi_x_start)
            roi_x_end = min(screenshot_w, roi_x_start + roi_width)

            if roi_y_end > roi_y_start and roi_x_end > roi_x_start:
                roi = full_screenshot[roi_y_start:roi_y_end, roi_x_start:roi_x_end]

                if self.debug and roi.size > 0:
                    self.debug_log(f'[ITEM_SEARCH] ROI size: {roi.shape[1]}x{roi.shape[0]} (x: {roi_x_start}, y: {roi_y_start}-{roi_y_end})')

                if self.save_screenshots and roi.size > 0:
                    fresh_screenshot = self.takeScreenshot(activate_window=False)
                    if fresh_screenshot is not None:
                        fresh_screenshot_gray = cv2.cvtColor(fresh_screenshot, cv2.COLOR_BGR2GRAY)
                        additional_rects = [
                            ((item_x, item_y, item_w, item_h), (0, 255, 0))
                        ]
                        self._saveDebugScreenshot(fresh_screenshot_gray,
                                                (roi_x_start, roi_y_start, roi_x_end - roi_x_start, roi_y_end - roi_y_start),
                                                f'search_buy_button_{item_name.replace(" ", "_")}',
                                                (0, 0, 255),
                                                additional_rects)
            else:
                if self.debug:
                    self.debug_log(f'[ITEM_SEARCH] Invalid ROI bounds: x={roi_x_start}-{roi_x_end}, y={roi_y_start}-{roi_y_end}, screenshot={screenshot_w}x{screenshot_h}')
                return None

            if roi.size > 0:

                roi_blurred = cv2.GaussianBlur(roi, (3, 3), 0)

                if self.buy_btn is not None:
                    buy_btn_h, buy_btn_w = self.buy_btn.shape[:2]
                    roi_h, roi_w = roi.shape[:2]

                    if self.debug:
                        self.debug_log(f'[BUY_BUTTON] Template size: {buy_btn_w}x{buy_btn_h}, ROI size: {roi_w}x{roi_h}')
                        self.debug_log(f'[BUY_BUTTON] ROI position in screenshot: x={roi_x_start}-{roi_x_end}, y={roi_y_start}-{roi_y_end}')

                    if roi_w < buy_btn_w or roi_h < buy_btn_h:
                        if self.debug:
                            self.debug_log(f'[BUY_BUTTON] ROI too small ({roi_w}x{roi_h}) for buy button template ({buy_btn_w}x{buy_btn_h}), skipping')
                        return None

                    if self.debug:
                        self.debug_log(f'[BUY_BUTTON] Searching for "buy button" for item "{item_name}"')

                    buy_search_start = time.time()
                    if 'buy_btn' not in self._cached_blurred_buttons:
                        self._cached_blurred_buttons['buy_btn'] = cv2.GaussianBlur(self.buy_btn, (3, 3), 0)
                    buy_btn_blurred = self._cached_blurred_buttons['buy_btn']
                    buy_result = cv2.matchTemplate(roi_blurred, buy_btn_blurred, cv2.TM_CCOEFF_NORMED)
                    _, buy_max_val, _, buy_max_loc = cv2.minMaxLoc(buy_result)
                    buy_search_time = (time.time() - buy_search_start) * 1000

                    if self.debug:
                        status = "FOUND" if buy_max_val >= self.BUY_BUTTON_THRESHOLD else "not found"
                        self.debug_log(f'[BUY_BUTTON] "buy button" for "{item_name}" - confidence: {buy_max_val:.3f}, threshold: {self.BUY_BUTTON_THRESHOLD:.3f}, {status}')
                        self.debug_log(f'[BUY_BUTTON] Best match location in ROI: x={buy_max_loc[0]}, y={buy_max_loc[1]}')
                        self.debug_log(f'[BUY_BUTTON] Search time: {buy_search_time:.2f}ms')

                        if 0.5 <= buy_max_val < self.BUY_BUTTON_THRESHOLD:
                            self.debug_log(f'[BUY_BUTTON] WARNING: Confidence ({buy_max_val:.3f}) is close to threshold but below. Consider checking ROI position or template quality.')

                    if buy_max_val >= self.BUY_BUTTON_THRESHOLD:
                        btn_h, btn_w = self.buy_btn.shape[:2]
                        buy_top_left_x = roi_x_start + buy_max_loc[0]
                        buy_top_left_y = roi_y_start + buy_max_loc[1]
                        win_left, win_top, _, _ = self._getWindowProps()
                        x = win_left + buy_top_left_x + btn_w // 2
                        y = win_top + buy_top_left_y + btn_h // 2

                        if self.debug:
                            self.debug_log(f'[BUY_BUTTON] Found! Top-left (screen): ({win_left + buy_top_left_x}, {win_top + buy_top_left_y})')
                            self.debug_log(f'[BUY_BUTTON] Center (screen): ({x}, {y})')

                        return (x, y)

                if self.sold_indicator is not None:
                    if 'sold_indicator' not in self._cached_blurred_buttons:
                        self._cached_blurred_buttons['sold_indicator'] = cv2.GaussianBlur(self.sold_indicator, (3, 3), 0)
                    sold_blurred = self._cached_blurred_buttons['sold_indicator']
                    sold_result = cv2.matchTemplate(roi_blurred, sold_blurred, cv2.TM_CCOEFF_NORMED)
                    _, sold_max_val, _, _ = cv2.minMaxLoc(sold_result)
                    if sold_max_val >= self.SOLD_INDICATOR_THRESHOLD:
                        if self.debug:
                            self.debug_log(f'[SOLD] Item already sold (confidence: {sold_max_val:.3f})')
                        return None

            return None
        return None

    def findButtonPosition(self, process_screenshot, button_image, threshold=0.8, search_region=None, button_name="button"):
        """Find a button in the screenshot and return its center position.

        Args:
            process_screenshot: Grayscale screenshot to search in
            button_image: Template image to find
            threshold: Minimum match confidence (0.0-1.0)
            search_region: Optional tuple (x, y, width, height) to limit search area
            region_offset: Offset to add to coordinates if searching in a cropped region
            button_name: Name of the button for debug logging (e.g., "refresh button", "confirm button")

        Returns:
            Tuple (center_x, center_y) in screen coordinates, or None if not found
        """
        if button_image is None:
            return None

        search_start_time = time.time()

        if self.debug:
            self.debug_log(f'[BUTTON_SEARCH] Searching for "{button_name}"')

        original_search_region = search_region

        if search_region is not None:
            x, y, w, h = search_region
            btn_h, btn_w = button_image.shape[:2]

            if w < btn_w or h < btn_h:
                if self.debug:
                    self.debug_log(f'[BUTTON_SEARCH] Search region too small ({w}x{h}) for template ({btn_w}x{btn_h}), using full screenshot')
                search_region = None
                region_offset = (0, 0)
            else:
                region_offset = (x, y)
                process_screenshot = process_screenshot[y:y+h, x:x+w]
                if self.debug:
                    _, _, win_width, win_height = self._getWindowProps()
                    self.debug_log(f'[BUTTON_SEARCH] Window size: {win_width}x{win_height}')
                    self.debug_log(f'[BUTTON_SEARCH] Limited search to region: x={x}, y={y}, w={w}, h={h}')

        if self.save_screenshots:
            full_screenshot = self.takeScreenshot()
            if full_screenshot is not None:
                full_screenshot_gray = cv2.cvtColor(full_screenshot, cv2.COLOR_BGR2GRAY)

                color_map = {
                    'refresh button': (255, 0, 0),
                    'confirm refresh button': (255, 255, 0),
                    'confirm buy button': (0, 165, 255),
                    'confirm button (out of skystones check)': (255, 255, 0),
                    'refresh button (out of skystones check)': (255, 0, 0),
                }
                color = color_map.get(button_name, (255, 255, 255))

                self._saveDebugScreenshot(full_screenshot_gray, original_search_region,
                                        f'search_{button_name.replace(" ", "_").replace("(", "").replace(")", "")}', color)

        process_screenshot = cv2.GaussianBlur(process_screenshot, (3, 3), 0)

        if button_name not in self._cached_blurred_buttons:
            self._cached_blurred_buttons[button_name] = cv2.GaussianBlur(button_image, (3, 3), 0)
        button_image_blurred = self._cached_blurred_buttons[button_name]

        result = cv2.matchTemplate(process_screenshot, button_image_blurred, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        search_time = (time.time() - search_start_time) * 1000

        if self.debug:
            status = "FOUND" if max_val >= threshold else "not found"
            self.debug_log(f'[BUTTON_SEARCH] "{button_name}" - confidence: {max_val:.3f}, threshold: {threshold:.3f}, {status}')
            self.debug_log(f'[BUTTON_SEARCH] Top-left corner (in search area): x={max_loc[0]}, y={max_loc[1]}')
            self.debug_log(f'[BUTTON_SEARCH] Search time: {search_time:.2f}ms')

        if max_val >= threshold:
            btn_h, btn_w = button_image_blurred.shape[:2]

            top_left_x = max_loc[0] + region_offset[0]
            top_left_y = max_loc[1] + region_offset[1]

            center_x_in_area = top_left_x + btn_w // 2
            center_y_in_area = top_left_y + btn_h // 2

            win_left, win_top, _, _ = self._getWindowProps()
            center_x = win_left + center_x_in_area
            center_y = win_top + center_y_in_area

            if self.debug:
                self.debug_log(f'[BUTTON_SEARCH] Button size: {btn_w}x{btn_h}')
                self.debug_log(f'[BUTTON_SEARCH] Top-left (screen): ({win_left + top_left_x}, {win_top + top_left_y})')
                self.debug_log(f'[BUTTON_SEARCH] Center (screen): ({center_x}, {center_y})')

            return (center_x, center_y)

        return None

    def clickButtonByImage(self, button_image, fallback_x_ratio=None, fallback_y_ratio=None, threshold=0.8, max_retries=3, search_region=None, button_name="button"):
        """Find and click a button using image detection, with optional fallback to fixed coordinates"""
        for attempt in range(max_retries):
            if not self.loop_active:
                return False

            screenshot = self.takeScreenshot(activate_window=(attempt == 0))
            if screenshot is None:
                continue
            process_screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)

            pos = self.findButtonPosition(process_screenshot, button_image, threshold, search_region=search_region, button_name=button_name)
            if pos is not None:
                if not self.loop_active:
                    return False
                x, y = pos
                offset_x, offset_y = self.randomClickOffset()
                x += offset_x
                y += offset_y
                pyautogui.moveTo(x, y)
                self.randomClick()
                return True

            if not self.loop_active:
                return False
            time.sleep(0.1)

        if fallback_x_ratio is not None and fallback_y_ratio is not None:
            if not self.loop_active:
                return False
            win_left, win_top, win_width, win_height = self._getWindowProps()
            x = win_left + win_width * fallback_x_ratio
            y = win_top + win_height * fallback_y_ratio
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
        if pos is None or not self.loop_active:
            return False

        x, y = pos
        offset_x, offset_y = self.randomClickOffset()
        x += offset_x
        y += offset_y
        pyautogui.moveTo(x, y)
        self.randomClick()

        if not self.loop_active:
            return False
        time.sleep(self.MOUSE_SLEEP)

        if not self.loop_active:
            return False
        self.clickConfirmBuy()
        return True

    def clickConfirmBuy(self):
        if not self.loop_active:
            return
        if self.debug:
            self.debug_log('[DEBUG] Clicking confirm buy button')

        confirm_buy_region = self.getSearchRegions()['confirm_buy_btn']
        if self.debug:
            x, y, w, h = confirm_buy_region
            self.debug_log(f'[DEBUG] Confirm buy search region: x={x}, y={y}, w={w}, h={h} (window: {self.window.width}x{self.window.height})')
        self.clickButtonByImage(
            self.confirm_buy_btn,
            fallback_x_ratio=0.55,
            fallback_y_ratio=0.70,
            threshold=self.BUTTON_MATCH_THRESHOLD,
            search_region=confirm_buy_region,
            button_name="confirm buy button"
        )

        if not self.loop_active:
            return
        time.sleep(self.MOUSE_SLEEP)
        time.sleep(self.SCREENSHOT_SLEEP)

    def clickRefresh(self):
        """Click refresh and handle the confirmation flow.

        Returns:
            True if refresh succeeded, False if user is out of gold
        """
        if not self.loop_active:
            return False
        if self.debug:
            self.debug_log('[DEBUG] Clicking refresh button')

        refresh_region = self.getSearchRegions()['refresh_btn']
        self.clickButtonByImage(
            self.refresh_btn,
            fallback_x_ratio=0.20,
            fallback_y_ratio=0.90,
            threshold=self.BUTTON_MATCH_THRESHOLD,
            search_region=refresh_region,
            button_name="refresh button"
        )

        if not self.loop_active:
            return False
        time.sleep(self.MOUSE_SLEEP)
        return self.clickConfirmRefresh()

    def clickConfirmRefresh(self):
        """Click confirm button and check for out-of-gold scenario.

        Returns:
            True if refresh succeeded, False if user is out of gold
        """
        if not self.loop_active:
            return False
        if self.debug:
            self.debug_log('[DEBUG] Clicking confirm refresh button')

        confirm_region = self.getSearchRegions()['confirm_btn']
        self.clickButtonByImage(
            self.confirm_btn,
            fallback_x_ratio=0.58,
            fallback_y_ratio=0.65,
            threshold=self.BUTTON_MATCH_THRESHOLD,
            search_region=confirm_region,
            button_name="confirm refresh button"
        )

        if not self.loop_active:
            return False
        time.sleep(self.SCREENSHOT_SLEEP)

        if not self._checkOutOfSkystones():
            return False

        return True

    def _checkOutOfSkystones(self):
        """Check if another confirm button appeared after refresh confirm (indicates out of skystones).

        Flow:
        1. After clicking refresh confirm, check if another confirm button appears
        2. If yes, click it (this is the "buy more skystones" popup)
        3. Check if refresh button disappeared (confirms we're out of skystones)
        4. If refresh button is gone, user was redirected to shop -> out of skystones

        Returns:
            True if we can continue (either no popup or just a missed click), False if out of skystones
        """
        screenshot = self.takeScreenshot()
        if screenshot is None:
            return True

        process_screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
        confirm_region = self.getSearchRegions()['confirm_btn']
        confirm_pos = self.findButtonPosition(
            process_screenshot, self.confirm_btn, self.BUTTON_MATCH_THRESHOLD,
            search_region=confirm_region, button_name="confirm button (out of skystones check)"
        )

        if confirm_pos is None:
            return True

        if self.debug:
            self.debug_log('[DEBUG] Detected another confirm button - possible out of skystones popup')

        if not self.loop_active:
            return True
        x, y = confirm_pos
        offset_x, offset_y = self.randomClickOffset()
        pyautogui.moveTo(x + offset_x, y + offset_y)
        self.randomClick()

        if not self.loop_active:
            return True
        time.sleep(0.5)

        screenshot = self.takeScreenshot(activate_window=False)
        if screenshot is None:
            return True

        process_screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
        refresh_region = self.getSearchRegions()['refresh_btn']
        refresh_pos = self.findButtonPosition(
            process_screenshot, self.refresh_btn, self.BUTTON_MATCH_THRESHOLD,
            search_region=refresh_region, button_name="refresh button (out of skystones check)"
        )

        if refresh_pos is None:
            print('[INFO] Out of skystones! User has been redirected to shop. Stopping script.')
            return False
        else:
            if self.debug:
                self.debug_log('[DEBUG] Refresh button still visible - was just a missed click')
            return True

    def scrollShop(self):
        win_left, win_top, win_width, win_height = self._getWindowProps()
        x = win_left + win_width * self.SCROLL_START_X_RATIO
        y = win_top + win_height * self.SCROLL_START_Y_RATIO

        base_scroll = self.SCROLL_RATIO
        extra_scroll = random.uniform(self.SCROLL_RANDOM_EXTRA_MIN, self.SCROLL_RANDOM_EXTRA_MAX)
        total_scroll = base_scroll + (base_scroll * extra_scroll)

        if self.debug:
            self.debug_log(f'[DEBUG] Scrolling shop (base: {base_scroll:.3f}, extra: {extra_scroll*100:.1f}%)')

        pyautogui.moveTo(x, y)
        time.sleep(0.1)
        pyautogui.mouseDown(button='left')
        time.sleep(0.1)
        pyautogui.moveTo(x, y - win_height * total_scroll)
        pyautogui.mouseUp(button='left')

class AppConfig():
    def __init__(self):
        self._config = get_config()

        recognized = self._config.get('recognized_titles', [
            'Epic Seven',
            'BlueStacks App Player',
            'LDPlayer',
            'MuMu Player 12',
            '에픽세븐',
            'Google Play Games on PC Emulator'
        ])
        self.RECOGNIZE_TITLES = set(recognized)

        self.ALL_ITEMS = self._config.get('shop_items', [
            {"image": "item_covenant.png", "name": "Covenant bookmark", "price": 184000},
            {"image": "item_mystic.png", "name": "Mystic medal", "price": 280000},
            {"image": "item_friendship.png", "name": "Friendship bookmark", "price": 18000}
        ])

        debug_cfg = self._config.get('debug', {})
        self.DEBUG = debug_cfg.get('enabled', False)

class AutoRefreshGUI:
    def __init__(self, debug_mode=False, custom_size=None, save_screenshots=False):
        self.app_config = AppConfig()
        self.app_config.DEBUG = debug_mode
        self.custom_size = custom_size
        self.save_screenshots = save_screenshots
        self.root = tk.Tk()

        self.bg_primary = '#0f0f0f'
        self.bg_secondary = '#1a1a1a'
        self.bg_tertiary = '#252525'
        self.accent_primary = '#6366f1'
        self.accent_hover = '#818cf8'
        self.accent_success = '#10b981'
        self.accent_danger = '#ef4444'
        self.text_primary = '#f5f5f5'
        self.text_secondary = '#a3a3a3'
        self.border_color = '#333333'

        self.root.config(bg=self.bg_primary)
        self.root.title('Epic7 Shopper')
        self.root.geometry('480x750')
        self.root.minsize(480, 750)

        icon_path = get_asset_path(os.path.join('assets', 'icon.ico'))
        self.root.iconbitmap(icon_path)
        self.title_name = ''
        self.ignore_path = {'item_friendship.png'}
        self.keep_image_open = []
        self.lock_start_button = False
        self.budget = ''

        main_container = tk.Frame(self.root, bg=self.bg_primary, padx=20, pady=20)
        main_container.pack(fill=tk.BOTH, expand=True)

        title_frame = tk.Frame(main_container, bg=self.bg_primary)
        title_frame.pack(pady=(0, 25))

        app_title = tk.Label(title_frame, text='Epic7 Shopper',
                             font=('Segoe UI', 28, 'bold'),
                             bg=self.bg_primary,
                             fg=self.text_primary)
        app_title.pack()

        subtitle = tk.Label(title_frame, text='Secret Shop Auto Refresh',
                             font=('Segoe UI', 11),
                             bg=self.bg_primary,
                             fg=self.text_secondary)
        subtitle.pack(pady=(2, 0))

        def onSelect(event):
            t_name = titles_combo_box.get()
            if t_name not in gw.getAllTitles():
                self.start_button.config(state=tk.DISABLED, bg='#404040')
                return

            self.title_name = titles_combo_box.get()
            if not self.lock_start_button:
                self.start_button.config(state=tk.NORMAL, bg=self.accent_primary)

        def onEnter(event):
            title = titles_combo_box.get()
            if title == '' or title not in gw.getAllTitles():
                self.start_button.config(state=tk.DISABLED, bg='#404040')
                return
            self.title_name = titles_combo_box.get()
            if not self.lock_start_button:
                self.start_button.config(state=tk.NORMAL, bg=self.accent_primary)

        titles = [title for title in self.app_config.RECOGNIZE_TITLES]
        titles.sort()

        emulator_frame = tk.Frame(main_container, bg=self.bg_secondary, relief=tk.FLAT, bd=0)
        emulator_frame.pack(fill=tk.X, pady=(0, 15), padx=0)

        emulator_inner = tk.Frame(emulator_frame, bg=self.bg_secondary, padx=15, pady=12)
        emulator_inner.pack(fill=tk.X)

        emulator_label = tk.Label(emulator_inner, text='Emulator Window',
                                  font=('Segoe UI', 10, 'bold'),
                                  bg=self.bg_secondary,
                                  fg=self.text_primary,
                                  anchor='w')
        emulator_label.pack(fill=tk.X, pady=(0, 8))

        style = ttk.Style()
        style.theme_use('clam')
        style.configure('Modern.TCombobox',
                       fieldbackground=self.bg_tertiary,
                       background=self.bg_tertiary,
                       foreground=self.text_primary,
                       borderwidth=1,
                       relief=tk.FLAT,
                       padding=8)
        style.map('Modern.TCombobox',
                 fieldbackground=[('readonly', self.bg_tertiary)],
                 selectbackground=[('readonly', self.bg_tertiary)],
                 selectforeground=[('readonly', self.text_primary)],
                 foreground=[('readonly', self.text_primary)])

        titles_combo_box = ttk.Combobox(master=emulator_inner,
                                        values=titles,
                                        style='Modern.TCombobox',
                                        font=('Segoe UI', 10),
                                        state='readonly')
        titles_combo_box.bind('<<ComboboxSelected>>', onSelect)
        titles_combo_box.bind('<KeyRelease>', onEnter)
        titles_combo_box.pack(fill=tk.X)

        items_section = tk.Frame(main_container, bg=self.bg_secondary, relief=tk.FLAT, bd=0)
        items_section.pack(fill=tk.X, pady=(0, 15), padx=0)

        items_inner = tk.Frame(items_section, bg=self.bg_secondary, padx=15, pady=12)
        items_inner.pack(fill=tk.X)

        items_label = tk.Label(items_inner, text='Target Items',
                               font=('Segoe UI', 10, 'bold'),
                               bg=self.bg_secondary,
                               fg=self.text_primary,
                               anchor='w')
        items_label.pack(fill=tk.X, pady=(0, 10))

        GUI_ITEM_SIZE = (80, 80)
        items_frame = tk.Frame(items_inner, bg=self.bg_secondary)

        for index, item in enumerate(self.app_config.ALL_ITEMS):
            img = Image.open(get_asset_path(os.path.join('assets', item["image"])))
            img = img.resize(GUI_ITEM_SIZE, Image.Resampling.LANCZOS)
            self.keep_image_open.append(ImageTk.PhotoImage(img))
            self.packItemHorizontal(items_frame, index, item["image"])

        items_frame.pack()

        settings_section = tk.Frame(main_container, bg=self.bg_secondary, relief=tk.FLAT, bd=0)
        settings_section.pack(fill=tk.X, pady=(0, 15), padx=0)

        settings_inner = tk.Frame(settings_section, bg=self.bg_secondary, padx=15, pady=12)
        settings_inner.pack(fill=tk.X)

        settings_label = tk.Label(settings_inner, text='Settings',
                                  font=('Segoe UI', 10, 'bold'),
                                  bg=self.bg_secondary,
                                  fg=self.text_primary,
                                  anchor='w')
        settings_label.pack(fill=tk.X, pady=(0, 12))

        self.move_zerozero_cbv = tk.BooleanVar(value=True)
        self.debug_cbv = tk.BooleanVar(value=self.app_config.DEBUG)

        def setupSpecialSetting(label, value, description=None):
            frame = tk.Frame(settings_inner, bg=self.bg_secondary, pady=6)
            label_frame = tk.Frame(frame, bg=self.bg_secondary)
            label_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

            special_label = tk.Label(label_frame,
                                     text=label,
                                     bg=self.bg_secondary,
                                     fg=self.text_primary,
                                     font=('Segoe UI', 10),
                                     anchor='w')
            special_label.pack(fill=tk.X)

            if description:
                desc_label = tk.Label(label_frame,
                                      text=description,
                                      bg=self.bg_secondary,
                                      fg=self.text_secondary,
                                      font=('Segoe UI', 8),
                                      anchor='w')
                desc_label.pack(fill=tk.X, pady=(2, 0))

            special_cb = tk.Checkbutton(frame,
                                        variable=value,
                                        bg=self.bg_secondary,
                                        activebackground=self.bg_secondary,
                                        selectcolor=self.bg_tertiary,
                                        fg=self.accent_primary,
                                        activeforeground=self.accent_primary,
                                        relief=tk.FLAT,
                                        bd=0,
                                        cursor='hand2')
            if value.get():
                special_cb.select()
            special_cb.pack(side=tk.RIGHT, padx=(10, 0))
            frame.pack(fill=tk.X, pady=4)
            return frame

        setupSpecialSetting('Auto move window to top-left', self.move_zerozero_cbv,
                           'Automatically positions the emulator window')
        setupSpecialSetting('Debug mode', self.debug_cbv,
                           'Writes detailed logs to debug.log')

        def packSettingEntry(text, default=None, description=None):
            frame = tk.Frame(settings_inner, bg=self.bg_secondary, pady=6)
            label_frame = tk.Frame(frame, bg=self.bg_secondary)
            label_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

            label = tk.Label(label_frame,
                             text=text,
                             bg=self.bg_secondary,
                             fg=self.text_primary,
                             font=('Segoe UI', 10),
                             anchor='w')
            label.pack(fill=tk.X)

            if description:
                desc_label = tk.Label(label_frame,
                                      text=description,
                                      bg=self.bg_secondary,
                                      fg=self.text_secondary,
                                      font=('Segoe UI', 8),
                                      anchor='w')
                desc_label.pack(fill=tk.X, pady=(2, 0))

            entry = tk.Entry(frame,
                             bg=self.bg_tertiary,
                             fg=self.text_primary,
                             font=('Segoe UI', 10),
                             width=12,
                             relief=tk.FLAT,
                             bd=0,
                             insertbackground=self.text_primary,
                             selectbackground=self.accent_primary,
                             selectforeground=self.text_primary)
            entry.pack(side=tk.RIGHT, padx=(10, 0))

            if default or default == 0:
                entry.insert(0, default)

            frame.pack(fill=tk.X, pady=4)
            return entry

        button_frame = tk.Frame(main_container, bg=self.bg_primary)
        button_frame.pack(fill=tk.X, pady=(10, 0))

        self.start_button = tk.Button(button_frame,
                                text='▶ Start Refresh',
                                font=('Segoe UI', 12, 'bold'),
                                state=tk.DISABLED,
                                command=self.startShopRefresh,
                                bg='#404040',
                                fg='#000000',
                                activebackground=self.accent_hover,
                                activeforeground='#000000',
                                relief=tk.FLAT,
                                bd=0,
                                padx=20,
                                pady=14,
                                cursor='hand2')

        def on_enter(e):
            if self.start_button['state'] != 'disabled':
                self.start_button.config(bg=self.accent_hover)

        def on_leave(e):
            if self.start_button['state'] != 'disabled':
                self.start_button.config(bg=self.accent_primary)

        self.start_button.bind('<Enter>', on_enter)
        self.start_button.bind('<Leave>', on_leave)
        if titles:
            for t in titles:
                if t in gw.getAllTitles():
                    self.title_name = t
                    titles_combo_box.set(self.title_name)
                    if not self.lock_start_button:
                        self.start_button.config(state=tk.NORMAL, bg=self.accent_primary)
                    break
        if not self.title_name:
            google_play_title_pattern = re.compile(r"^(Epic Seven|에픽세븐) - \w+$", re.UNICODE)
            for t in gw.getAllTitles():
                if google_play_title_pattern.fullmatch(t):
                    self.title_name = t
                    titles_combo_box.set(self.title_name)
                    if not self.lock_start_button:
                        self.start_button.config(state=tk.NORMAL, bg=self.accent_primary)
                    break

        def validateInt(value):
            try:
                if value == '':
                    return True
                int_value = int(value)
                if int_value > 100000000:
                    return False
                else:
                    return value.isdigit()
            except ValueError:
                return False

        valid_int_reg = self.root.register(validateInt)
        self.limit_spend_entry = packSettingEntry('Skystone Budget', None, 'Leave empty for unlimited')
        self.limit_spend_entry.config(validate='key', validatecommand=(valid_int_reg, '%P'))

        self.start_button.pack(fill=tk.X, pady=(0, 0))
        self.root.mainloop()

    def packItemHorizontal(self, parent_frame, index, path):
        """Pack item with icon that has colored border (green=active, red=inactive) and is clickable"""

        is_checked = [path not in self.ignore_path]

        item_frame = tk.Frame(parent_frame, bg=self.bg_secondary, padx=8)

        border_color = self.accent_success if is_checked[0] else self.accent_danger
        border_width = 3

        border_frame = tk.Frame(item_frame,
                               bg=border_color,
                               padx=border_width,
                               pady=border_width)
        border_frame.pack(side=tk.TOP, pady=(0, 8))

        image_label = tk.Label(border_frame,
                              image=self.keep_image_open[index],
                              bg=self.bg_secondary,
                              relief=tk.FLAT,
                              bd=0)
        image_label.pack()

        def toggle(event=None):
            """Toggle the item's checked state"""
            is_checked[0] = not is_checked[0]

            if is_checked[0]:
                border_frame.config(bg=self.accent_success)
                self.ignore_path.discard(path)
            else:
                border_frame.config(bg=self.accent_danger)
                self.ignore_path.add(path)

        image_label.bind('<Button-1>', toggle)
        border_frame.bind('<Button-1>', toggle)
        image_label.config(cursor='hand2')

        item_frame.pack(side=tk.LEFT, padx=6)

    def packMessage(self, message, text_size=14, pady=10):
        new_label = tk.Label(self.root, text=message, font=('Segoe UI', text_size), bg=self.bg_primary, fg=self.text_primary)
        new_label.pack(pady=pady)
        return new_label

    def refreshComplete(self):
        print('Terminated!')
        self.root.title('Epic7 Shopper')
        self.start_button.config(state=tk.NORMAL, text='▶ Start Refresh', bg=self.accent_primary)
        self.lock_start_button = False

    def startShopRefresh(self):
        self.root.title('Press ESC to stop!')
        self.lock_start_button = True
        self.start_button.config(state=tk.DISABLED, text='⏸ Running...', bg='#404040')
        self.app_config.DEBUG = self.debug_cbv.get()
        self.ssr = SecretShopRefresh(
            title_name=self.title_name,
            callback=self.refreshComplete,
            debug=self.app_config.DEBUG,
            custom_size=self.custom_size,
            save_screenshots=self.save_screenshots
        )

        self.ssr.tk_instance = self.root

        if not self.move_zerozero_cbv.get():
            self.ssr.allow_move = True

        for item in self.app_config.ALL_ITEMS:
            if item["image"] not in self.ignore_path:
                self.ssr.addShopItem(path=item["image"], name=item["name"], price=item["price"])

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
    parser.add_argument('--screenshot', action='store_true', help='Save debug screenshots of search areas (requires --debug)')
    parser.add_argument('--size', type=str, help='Custom reference size for assets (e.g., --size=1920x1080)')
    parser.add_argument('--info', action='store_true', help='Show window size and scaling info, then exit')
    parser.add_argument('--generate-config', action='store_true', help='Generate a config.example.json with all default values')
    args = parser.parse_args()

    if args.generate_config:
        save_default_config('config.example.json')
        print('\nYou can copy config.example.json to config.json and customize the values.')
        print('Only include the values you want to change - the app uses defaults for missing values.')
        exit(0)

    custom_width, custom_height = None, None
    if args.size:
        try:
            parts = args.size.lower().split('x')
            custom_width = int(parts[0])
            custom_height = int(parts[1])
            print(f'[CONFIG] Custom reference size: {custom_width}x{custom_height}')
        except (ValueError, IndexError) as e:
            print(f'[ERROR] Invalid size format: {args.size}. Use format: --size=WIDTHxHEIGHT. Error: {e}')
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

    gui = AutoRefreshGUI(debug_mode=args.debug, custom_size=(custom_width, custom_height) if args.size else None, save_screenshots=args.screenshot)