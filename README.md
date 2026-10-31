<div align="center">

<img width="256" height="256" alt="icon" src="https://github.com/user-attachments/assets/c28bbf05-69e3-4b7e-885a-3430cb7b9e87" />

# MD Studio

**A simple desktop Markdown editor for Windows, written in Python (Tkinter).**
Write Markdown on the left, see a live preview on the right. The toolbar writes the Markdown for you.

![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?logo=windows&logoColor=white)
![Dependencies](https://img.shields.io/badge/Dependencies-none-brightgreen)

</div>

---

## Features

- **Toolbar** for bold, italic, inline code, headings (H1-H3), bullet / numbered / task lists, quotes, links, images, tables and horizontal rules
- **Insert menu** with ready-made templates (README, changelog, contributing guide, pull request), GitHub alerts, Shields.io badges and collapsible sections
- **Live preview** that updates as you type
- **Find and replace**, undo / redo, and one-click "copy all Markdown"
- **Dark and light themes**
- **Three layouts:** editor only, split view, preview only
- **Open and save** `.md` files (UTF-8), with a prompt before discarding unsaved changes
- **No dependencies** to run from source: it only uses Python's standard library

### Keyboard shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+B` | Bold |
| `Ctrl+I` | Italic |
| `Ctrl+K` | Insert link |
| `Ctrl+N` | New document |
| `Ctrl+O` | Open file |
| `Ctrl+S` | Save |
| `Ctrl+F` | Find and replace |
| `Ctrl+Z` / `Ctrl+Y` | Undo / redo |

---

## Getting started

### Run from source

Requires **Python 3.9 or newer**. Tkinter is included with the Windows installer from [python.org](https://www.python.org/downloads/).

```bash
cd MD-Studio
python markdown_studio.py
```

On Windows you can also just double-click **`run.bat`**.

### Build a standalone `.exe`

Double-click **`build_exe.bat`**. When it finishes, you will find the program at:

```
MD-Studio/dist/MarkdownStudio.exe
```

It runs on any Windows PC without Python installed.

Equivalent manual command:

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name MarkdownStudio --icon icon.ico --add-data "icon.ico;." markdown_studio.py
```

---

## Project structure

```
MD-Studio/
├── markdown_studio.py   # the whole application
├── icon.ico             # app icon (Windows)
├── icon.png             # app icon (PNG)
├── run.bat              # run from source
└── build_exe.bat        # one-click .exe build
```

---

## Limitations

- The preview is an **approximation**. It is not GitHub's renderer, and images and HTML are not rendered in it.
- No WYSIWYG editing
- No Mermaid or math rendering
- No syntax highlighting
- One document at a time

---

<div align="center">

Developed with ❤️ By [Raawvie](https://github.com/Raawvie)

</div>
