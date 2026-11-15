@echo off
REM Builds dist\MarkdownStudio.exe (requires Python 3.9+ with "Add Python to PATH").
python -m pip install --upgrade pyinstaller pillow
python -m PyInstaller --noconfirm --onefile --windowed --name MarkdownStudio --icon icon.ico --add-data "icon.ico;." --hidden-import md_render markdown_studio.py
echo.
echo Done. Your program is here: dist\MarkdownStudio.exe
pause
