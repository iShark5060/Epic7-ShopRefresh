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

# Suppress ALL deprecation warnings before importing anything else
warnings.filterwarnings('ignore', category=DeprecationWarning)
warnings.filterwarnings('ignore', category=PendingDeprecationWarning)
warnings.filterwarnings('ignore', message='.*pkg_resources.*')
warnings.filterwarnings('ignore', module='pkg_resources')

# Set environment variables to suppress warnings in subprocesses
# This affects Python subprocesses spawned by PyInstaller
os.environ['PYTHONWARNINGS'] = 'ignore::DeprecationWarning,ignore::PendingDeprecationWarning'

# Additional way to suppress - modify sys.warnoptions
if not sys.warnoptions:
    sys.warnoptions.append('ignore::DeprecationWarning')

def main():
    # Import PyInstaller after setting up warning filters
    try:
        # Suppress the warning that occurs on import
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', DeprecationWarning)
            import PyInstaller.__main__
    except ImportError:
        print("PyInstaller not found. Install it with:")
        print("  pip install pyinstaller")
        sys.exit(1)
    
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    spec_file = os.path.join(script_dir, 'E7SecretShopRefresh.spec')
    
    if not os.path.exists(spec_file):
        print(f"Spec file not found: {spec_file}")
        sys.exit(1)
    
    print("=" * 50)
    print("Building Epic7 Shopper...")
    print("=" * 50)
    print()
    
    # Run PyInstaller with the spec file
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        PyInstaller.__main__.run([
            spec_file,
            '--noconfirm',  # Don't ask for confirmation to overwrite
            '--clean',      # Clean PyInstaller cache before building
        ])
    
    print()
    print("=" * 50)
    print("Build complete!")
    print("Executable: dist/Epic7Shopper.exe")
    print("=" * 50)

if __name__ == '__main__':
    # One more layer of warning suppression
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        main()

