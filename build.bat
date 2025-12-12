@echo off
REM Build script for Epic7 Shopper
REM Suppresses pkg_resources deprecation warnings from setuptools 81+

echo ================================================
echo Building Epic7 Shopper...
echo ================================================
echo.

REM Run PyInstaller with warning filters
python -W ignore::DeprecationWarning -W ignore::PendingDeprecationWarning -m PyInstaller E7SecretShopRefresh.spec --noconfirm --clean

echo.
echo ================================================
echo Build complete!
echo Executable: dist\Epic7Shopper.exe
echo ================================================

pause

