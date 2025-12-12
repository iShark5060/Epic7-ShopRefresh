# Epic7 Shopper - Secret Shop Auto Refresh

An automated tool for refreshing the Secret Shop in Epic Seven, with support for any window resolution and built-in anti-detection features.

![Demo](https://github.com/sya1999/Epic-Seven-Secret-Shop-Refresh/blob/main/assets/E7.gif)

## Credits

**Original Project by [sya1999](https://github.com/sya1999/Epic-Seven-Secret-Shop-Refresh)**

This project is a fork of the original Epic Seven Secret Shop Refresh tool. Huge thanks to the original developer for creating the foundation that made this enhanced version possible!

---

## Features

- **Multi-Resolution Support** - Works with any window size (auto-scales detection images)
- **Image-Based Detection** - Uses template matching instead of fixed coordinates
- **Anti-Detection Measures** - Random delays, click offsets, and scroll variations
- **Multiple Item Support** - Detects and purchases all desired items in a single view
- **Safety Checks** - Pauses if you navigate away from the shop
- **Out of Skystone Check** - Stops script if the user is out of skystones
- **Live Shopping Display** - Shows items purchased and refresh counter
- **Debug Mode** - Detailed output for troubleshooting

## ToDo

- **Out of Gold check** - I .. have too much Gold to check that currently, sorry =D

## Quick Start

### Prerequisites

- Python 3.9+ (tested with 3.11)
- Epic Seven running in windowed mode
- Navigate to the Secret Shop before starting

### Installation

1. Clone or download this repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Running

1. Open Epic Seven and navigate to the **Secret Shop**
2. Run the application:
   ```bash
   python E7SecretShopRefresh.py
   ```
3. Select your game window from the dropdown
4. Check the items you want to purchase (Covenant, Mystic, Friendship bookmarks)
5. (Optional) Set a Skystone budget
6. Click **Start Refresh**
7. Press **ESC** to stop at any time

## Command Line Options

```bash
# Normal mode
python E7SecretShopRefresh.py

# Debug mode (detailed output)
python E7SecretShopRefresh.py --debug

# Show window info and scaling details
python E7SecretShopRefresh.py --info

# Use custom reference size (for your own screenshots)
python E7SecretShopRefresh.py --size=1920x1080

# Combine options
python E7SecretShopRefresh.py --debug --size=1920x1080
```

## Building an Executable

### Using the spec file (recommended):
```bash
pip install pyinstaller
pyinstaller E7SecretShopRefresh.spec
```

### Or with a simple command:
```bash
pyinstaller -F --noconsole -i assets/icon.ico E7SecretShopRefresh.py
```

The executable will be created in the `dist` folder.

**Note:** When distributing, you need to include the `assets` folder alongside the executable, or use the spec file which bundles assets automatically.

## Settings

| Setting | Description |
|---------|-------------|
| **Window Title** | Select your game window from the dropdown or type the exact window name |
| **Covenant/Mystic/Friendship** | Toggle which bookmark types to purchase |
| **Skystone Budget** | Maximum skystones to spend (leave empty for unlimited) |
| **Auto Placement** | Automatically position the game window |

## Important Notes

1. **Administrator Mode**: If using the PC client (not an emulator), run the program as Administrator

2. **Monitor Must Stay On**: The program takes screenshots to detect items - don't turn off your display

3. **Test First**: Manually refresh until a bookmark appears, then start the program to verify detection works

4. **Stay in Shop**: The program assumes you're already in the Secret Shop - it won't navigate there automatically

## Troubleshooting

### Items not being detected?

1. Run with `--debug` flag to see confidence scores
2. If confidence is low (<0.8), the images may need updating for your resolution
3. Use `--info` to check your window size
4. Try providing custom screenshots with `--size=WIDTHxHEIGHT`

### Button clicks missing?

The anti-detection system adds random offsets to clicks. If buttons are consistently missed, check if your window has unusual borders or scaling.

### Program clicking in wrong places?

Make sure you're in the Secret Shop before starting. The safety system will pause if it can't find the refresh button.

## Custom Screenshots

If the included images don't work for your setup:

1. Take screenshots of the items/buttons at your resolution
2. Save them in the `assets` folder with the same names:
   - `covenant.png`, `mystic.png`, `friendship.png` (items)
   - `buy.png`, `refresh.png`, `confirm.png`, `confirm_buy.png` (buttons)
   - `sold.png` (sold indicator)
3. Run with `--size=WIDTHxHEIGHT` matching your screenshot resolution

## History

Purchase history is saved to the `ShopRefreshHistory` folder as CSV files.

## License

See [LICENSE](LICENSE) file.

---

*Happy refreshing! May your bookmarks be plentiful!* 🎰✨
