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

- **Toolbar** (two rows) for bold, italic, bold+italic, strikethrough, inline code, headings (H1-H6), bullet / numbered / task lists, indent / outdent for nested lists, quotes, links, images, tables, code blocks, diff blocks, collapsible sections and horizontal rules
- **Insert menu** with submenus for headings, text styles, lists (Markdown and HTML), code blocks in 12 languages, quotes, links (inline, reference, HTML, `#anchor`), images (normal, linked, HTML), GitHub alerts, Shields.io badges and collapsible sections. It also has ready-made templates (README, changelog, contributing guide, pull request)
- **Live preview** that updates as you type and keeps its scroll position
- **Rich preview** that renders:
  - headings `#` to `######` and HTML `<h1>` to `<h6>`, with `id` anchors you can link to
  - nested lists (Markdown and HTML `<ul>` / `<ol>`), task lists
  - bold, italic, bold+italic, strikethrough, inline code, and inline HTML such as `<b>`, `<kbd>`, `<br>`
  - fenced code blocks with a language label, and `diff` blocks with green / red lines
  - nested block quotes and GitHub alerts (`[!NOTE]`, `[!TIP]`, ...)
  - links: inline, reference-style, HTML `<a>` and `#anchor` links (click to open)
  - images: `![]()`, `<img>` and linked images (see the note about Pillow below)
  - tables (Markdown and HTML)
  - collapsible `<details>` / `<summary>` sections, including nested ones (click to expand)
- **Copy, cut and paste** with `Ctrl+C` / `Ctrl+X` / `Ctrl+V`, the Edit menu, toolbar buttons and right-click menus. You can also select and copy text from the preview
- **Find and replace**, undo / redo, and one-click "copy all Markdown"
- **Dark and light themes**
- **Three layouts:** editor only, split view, preview only
- **Open and save** `.md` files (UTF-8), with a prompt before discarding unsaved changes
- **No dependencies** to run from source: it only uses Python's standard library. [Pillow](https://pypi.org/project/pillow/) is optional and adds more image formats

### Keyboard shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+B` | Bold |
| `Ctrl+I` | Italic |
| `Ctrl+K` | Insert link |
| `Ctrl+C` / `Ctrl+X` / `Ctrl+V` | Copy / cut / paste |
| `Ctrl+A` | Select all |
| `Tab` / `Shift+Tab` | Nest / un-nest a list item (or indent / outdent the selected lines) |
| `Ctrl+N` | New document |
| `Ctrl+O` | Open file |
| `Ctrl+S` | Save |
| `Ctrl+F` | Find and replace |
| `Ctrl+Z` / `Ctrl+Y` | Undo / redo |

Right-click in the editor for Cut, Copy, Paste, Delete and Select All. Right-click in the preview for Copy and Select All.

---

## Getting started

### Run from source

Requires **Python 3.9 or newer**. Tkinter is included with the Windows installer from [python.org](https://www.python.org/downloads/).

```bash
cd MD-Studio
python markdown_studio.py
```

On Windows you can also just double-click **`run.bat`**.

Optional: install Pillow so the preview can show JPEG, WebP and other image formats (without it, only PNG and GIF are shown):

```bash
pip install pillow
```

### Build a standalone `.exe`

Double-click **`build_exe.bat`**. It installs PyInstaller and Pillow, then builds the program. When it finishes, you will find it at:

```
MD-Studio/dist/MarkdownStudio.exe
```

It runs on any Windows PC without Python installed.

Equivalent manual command:

```bash
pip install pyinstaller pillow
pyinstaller --onefile --windowed --name MarkdownStudio --icon icon.ico --add-data "icon.ico;." --hidden-import md_render markdown_studio.py
```

---

## Project structure

```
MD-Studio/
├── markdown_studio.py   # the application (window, menus, toolbar, editing tools)
├── md_render.py         # the Markdown + HTML preview renderer (must stay next to markdown_studio.py)
├── icon.ico             # app icon (Windows)
├── icon.png             # app icon (PNG)
├── run.bat              # run from source
└── build_exe.bat        # one-click .exe build
```

---

## Limitations

- The preview is an **approximation**. It is not GitHub's renderer
- Images load from `http(s)` links or from files next to your `.md` file. They need an internet connection for web images, and SVG images (such as Shields.io badges) are not drawn in the preview. A placeholder is shown instead
- Tables are drawn as a text grid, so very wide tables wrap at the edge of the preview
- Raw HTML is supported only for common tags (headings, lists, links, images, tables, `<details>`, `<pre>`, `<blockquote>` and basic text styles). Styling and scripts are ignored
- No WYSIWYG editing
- No Mermaid or math rendering
- No syntax highlighting inside code blocks
- One document at a time

---

<div align="center">

Developed with ❤️ By [Raawvie](https://github.com/Raawvie)

</div>
