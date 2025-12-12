#!/usr/bin/env python
"""
Build script for Epic7 Shopper
Suppresses deprecation warnings during PyInstaller build

The pkg_resources deprecation warning is from setuptools 81+.
See: https://setuptools.pypa.io/en/latest/pkg_resources.html
PyInstaller and some dependencies still use pkg_resources internally.
"""

import warnings
import sys
import os

warnings.filterwarnings('ignore', category=DeprecationWarning)
warnings.filterwarnings('ignore', category=PendingDeprecationWarning)
warnings.filterwarnings('ignore', message='.*pkg_resources.*')
warnings.filterwarnings('ignore', module='pkg_resources')

os.environ['PYTHONWARNINGS'] = 'ignore::DeprecationWarning,ignore::PendingDeprecationWarning'

if not sys.warnoptions:
    sys.warnoptions.append('ignore::DeprecationWarning')

def main():
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', DeprecationWarning)
            import PyInstaller.__main__
    except ImportError:
        print("PyInstaller not found. Install it with:")
        print("  pip install pyinstaller")
        sys.exit(1)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    spec_file = os.path.join(script_dir, 'E7SecretShopRefresh.spec')

    if not os.path.exists(spec_file):
        print(f"Spec file not found: {spec_file}")
        sys.exit(1)

    print("=" * 50)
    print("Building Epic7 Shopper...")
    print("=" * 50)
    print()

    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        PyInstaller.__main__.run([
            spec_file,
            '--noconfirm',
            '--clean',
        ])

    print()
    print("=" * 50)
    print("Build complete!")
    print("Executable: dist/Epic7Shopper.exe")
    print("=" * 50)

if __name__ == '__main__':
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        main()