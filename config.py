"""
Configuration module for Epic7 Secret Shop Auto Refresh.

This module handles loading configuration from an optional config.json file.
If the file doesn't exist, default values are used.
If it exists, values from the file override the defaults.
"""

import copy
import json
import os
from typing import Any, Dict

DEFAULT_CONFIG = {
    "timing": {
        "mouse_sleep": 0.15,
        "screenshot_sleep": 0.15,
    },

    "anti_detection": {
        "click_offset_max": 10,
        "double_click_chance": 0.3,
        "scroll_random_extra_min": 0.0,
        "scroll_random_extra_max": 0.15,
    },

    "scrolling": {
        "scroll_ratio": 0.277,
        "scroll_start_x_ratio": 0.58,
        "scroll_start_y_ratio": 0.65,
    },

    "thresholds": {
        "item_match": 0.75,
        "button_match": 0.75,
        "shop_check": 0.7,
        "buy_button": 0.7,
        "sold_indicator": 0.7,
    },

    "reference": {
        "width": 3840,
        "height": 1600,
    },

    "search_regions_21_9": {
        "refresh_button": {
            "width": 900,
            "height": 275,
            "margin_left": 540,
        },
        "confirm_button": {
            "width": 500,
            "height": 500,
            "margin_bottom": 225,
            "margin_right": 250,
        },
        "items_search": {
            "x": 1680,
            "width": 300,
        },
        "buy_button": {
            "margin_x": 1139,
            "width": 450,
            "height": 250,
        },
        "confirm_buy_button": {
            "width": 600,
            "height": 230,
            "margin_bottom": 350,
            "offset_right": 15,
        },
    },

    "search_regions_16_9": {
        "refresh_button": {
            "width": 580,
            "height": 160,
            "margin_left": 0,
        },
        "confirm_button": {
            "width": 400,
            "height": 300,
            "margin_bottom": 160,
            "margin_right": 0,
        },
        "items_search": {
            "x": 810,
            "width": 190,
        },
        "buy_button": {
            "margin_x": 740,
            "width": 300,
            "height": 180,
        },
        "confirm_buy_button": {
            "width": 440,
            "height": 150,
            "margin_bottom": 240,
            "offset_right": 15,
        },
    },

    "search_regions_other": {
        "refresh_button": {
            "width": 900,
            "height": 275,
            "margin_left": 540,
        },
        "confirm_button": {
            "width": 450,
            "height": 500,
            "margin_bottom": 275,
            "margin_right": 250,
        },
        "items_search": {
            "x": 1680,
            "width": 300,
        },
        "buy_button": {
            "margin_x": 1100,
            "width": 450,
            "height": 250,
        },
        "confirm_buy_button": {
            "width": 650,
            "height": 200,
            "margin_bottom": 375,
            "offset_right": 15,
        },
    },

    "recognized_titles": [
        "Epic Seven",
        "BlueStacks App Player",
        "LDPlayer",
        "MuMu Player 12",
        "에픽세븐",
        "Google Play Games on PC Emulator"
    ],

    "shop_items": [
        {"image": "item_covenant.png", "name": "Covenant bookmark", "price": 184000},
        {"image": "item_mystic.png", "name": "Mystic medal", "price": 280000},
        {"image": "item_friendship.png", "name": "Friendship bookmark", "price": 18000}
    ],

    "debug": {
        "enabled": False,
        "save_screenshots": False,
    },
}

CONFIG_FILE = "config.json"

def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deep merge override dict into base dict.
    Returns a new dict with base values overwritten by override values.
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result

def load_config() -> Dict[str, Any]:
    """
    Load configuration from config.json if it exists.
    Returns the merged configuration (defaults + file overrides).
    """
    config = copy.deepcopy(DEFAULT_CONFIG)

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                file_config = json.load(f)

            config = _deep_merge(config, file_config)
            print(f"[CONFIG] Loaded configuration from {CONFIG_FILE}")
        except json.JSONDecodeError as e:
            print(f"[CONFIG] Warning: Failed to parse {CONFIG_FILE}: {e}")
            print("[CONFIG] Using default configuration")
        except OSError as e:
            print(f"[CONFIG] Warning: Failed to load {CONFIG_FILE}: {e}")
            print("[CONFIG] Using default configuration")

    return config

def save_default_config(filepath: str = "config.example.json") -> bool:
    """
    Save the default configuration to a JSON file.
    Useful for generating a template config file.

    Args:
        filepath: Path to the output file.

    Returns:
        True if the file was saved successfully, False otherwise.
    """
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
        print(f"[CONFIG] Saved default configuration to {filepath}")
        return True
    except (OSError, IOError) as e:
        print(f"[CONFIG] Error: Failed to save configuration to '{filepath}': {e}")
        return False
    except Exception as e:
        print(f"[CONFIG] Error: Unexpected error saving configuration to '{filepath}': {e}")
        return False

def get_search_regions_for_aspect(config: Dict[str, Any], aspect_ratio: str) -> Dict[str, Any]:
    """
    Get the appropriate search regions config for the given aspect ratio.

    Args:
        config: The loaded configuration dict
        aspect_ratio: One of '21:9', '16:9', or 'other'

    Returns:
        The search regions dict for that aspect ratio
    """
    if aspect_ratio == '21:9':
        return config.get('search_regions_21_9', DEFAULT_CONFIG['search_regions_21_9'])
    elif aspect_ratio == '16:9':
        return config.get('search_regions_16_9', DEFAULT_CONFIG['search_regions_16_9'])
    else:
        return config.get('search_regions_other', DEFAULT_CONFIG['search_regions_other'])

_config = None

def get_config() -> Dict[str, Any]:
    """
    Get the current configuration. Loads from file on first call.
    """
    global _config
    if _config is None:
        _config = load_config()
    return _config

def reload_config() -> Dict[str, Any]:
    """
    Force reload configuration from file.
    """
    global _config
    _config = load_config()
    return _config
