@echo off
REM Builds dist\MarkdownStudio.exe (requires Python 3.9+ with "Add Python to PATH").
python -m pip install --upgrade pyinstaller
python -m PyInstaller --noconfirm --onefile --windowed --name MarkdownStudio --icon icon.ico --add-data "icon.ico;." markdown_studio.py
echo.
echo Done. Your program is here: dist\MarkdownStudio.exe
pause
