@echo off
echo ================================================
echo Building Epic7 Shopper...
echo ================================================
echo.

python -W ignore::DeprecationWarning -W ignore::PendingDeprecationWarning -m PyInstaller E7SecretShopRefresh.spec --noconfirm --clean

echo.
echo ================================================
echo Build complete!
echo Executable: dist\Epic7Shopper.exe
echo ================================================

pause