@echo off
chcp 65001 >nul
echo === Snap OCR : build exe ===
pip install pyinstaller PyQt6 pillow
python snap_ocr.pyw --make-icon
set ICON=
if exist icon.ico set ICON=--icon icon.ico
pyinstaller --noconsole --onefile --clean --name SnapOCR %ICON% --exclude-module tkinter snap_ocr.pyw
echo.
echo ===== Done:  dist\SnapOCR.exe =====
echo Tip: for a portable exe, copy the folder "Tesseract-OCR" next to SnapOCR.exe and rename it to "tesseract".
pause
