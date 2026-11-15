"""Markdown Studio - a simple desktop Markdown editor.

Pure Python 3 + Tkinter (no third-party packages needed to run).
Left: Markdown source. Right: live preview. Toolbar buttons write the Markdown for you.
"""
import math
import os
import re
import sys
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, simpledialog
from urllib.parse import quote

from md_render import Renderer

APP_NAME = "Markdown Studio"

THEMES = {
    "dark": {"bg": "#0f1224", "panel": "#161a30", "code": "#0b0e1d", "fg": "#e6e8f5",
             "mute": "#98a0c8", "acc": "#8b6cf6", "link": "#a994ff", "found": "#5b46b8"},
    "light": {"bg": "#f6f5fb", "panel": "#ffffff", "code": "#f1eefb", "fg": "#1d1b32",
              "mute": "#5d587e", "acc": "#6d4ae0", "link": "#5a38c8", "found": "#d9ccff"},
}

TEMPLATES = {
    "Blank": "",
    "GitHub README": (
        "# Project name\n\nOne-sentence description of the project.\n\n"
        "## Installation\n\n```bash\n# add install steps here\n```\n\n"
        "## Usage\n\nDescribe how to use the project.\n\n"
        "## Contributing\n\nSee [CONTRIBUTING.md](CONTRIBUTING.md).\n\n"
        "## License\n\nAdd your license here.\n"),
    "Changelog": (
        "# Changelog\n\n## [Unreleased]\n\n### Added\n- \n\n### Changed\n- \n\n### Fixed\n- \n"),
    "Contributing guide": (
        "# Contributing\n\nThanks for your interest in contributing.\n\n"
        "## Getting started\n\n1. Fork the repository\n2. Create a branch\n3. Open a pull request\n\n"
        "## Reporting issues\n\nDescribe what you expected and what happened.\n"),
    "Pull request template": (
        "## Summary\n\nWhat does this change?\n\n## Checklist\n\n"
        "- [ ] Tests added or updated\n- [ ] Docs updated\n"),
}

WELCOME = """# Welcome to Markdown Studio

Select some text and use the toolbar. The Markdown is written for you.

## Example
- **Bold**, *italic*, ***both***, ~~strikethrough~~ and `inline code`
- Nested lists
    - indent with Tab
- [ ] A task to do
- [x] A finished task

```python
print("code blocks with a language")
```

<details>
<summary>Click to expand</summary>

Collapsible sections work in the preview.

</details>

> [!TIP]
> Use the Insert menu for templates, badges and alerts.

| Name | Value |
|------|-------|
| A    | 1     |
"""

SAMPLE_NESTED_LIST = "\n- Item 1\n    - Item 1.1\n        - Item 1.1.1\n        - Item 1.1.2\n    - Item 1.2\n- Item 2\n"
SAMPLE_HTML_LIST = "\n<ul>\n    <li>Item 1</li>\n    <li>Item 2</li>\n</ul>\n"
SAMPLE_HTML_NESTED = (
    "\n<ul>\n    <li>Item 1\n        <ul>\n            <li>Item 1.1</li>\n"
    "            <li>Item 1.2</li>\n        </ul>\n    </li>\n    <li>Item 2</li>\n</ul>\n")
SAMPLE_DETAILS_MENU = (
    "\n<details>\n<summary>Menu Item</summary>\n<ul>\n"
    "<li><details>\n    <summary>Item 1</summary>\n    <ul>\n        <li>Item 1.1</li>\n"
    "        <li>Item 1.2</li>\n    </ul>\n</details></li>\n"
    "<li><details>\n    <summary>Item 2</summary>\n    <ul>\n        <li>Item 2.1</li>\n"
    "        <li>Item 2.2</li>\n    </ul>\n</details></li>\n</ul>\n</details>\n")

CREDIT_URL = "https://github.com/Raawvie"
CREDIT_BLUE = {"dark": "#58a6ff", "light": "#0969da"}  # classic link blues


def resource_path(name):
    """Find a bundled file both when running from source and from the PyInstaller exe."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def open_in_chrome_tab(url):
    """Open url in a new Google Chrome tab; fall back to the default browser if Chrome isn't found."""
    candidates = [
        os.path.join(os.environ.get(v, ""), "Google", "Chrome", "Application", "chrome.exe")
        for v in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")
    ] + ["/usr/bin/google-chrome", "/usr/bin/chromium", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    for path in candidates:
        if os.path.isfile(path):
            webbrowser.register("chrome-tab", None, webbrowser.BackgroundBrowser(path))
            if webbrowser.get("chrome-tab").open_new_tab(url):
                return
    webbrowser.open_new_tab(url)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.geometry("1150x720")
        self.minsize(640, 400)
        try:
            self.iconbitmap(resource_path("icon.ico"))
        except tk.TclError:
            pass  # icon is optional (e.g. on Linux)
        self.path = None
        self.dirty = False
        self.timer = None
        self.theme = tk.StringVar(value="dark")
        self.layout = tk.StringVar(value="split")
        self.buttons, self.separators = [], []
        self.find_win = None
        self.last_text = None  # last text pane that had focus (target for Copy/Paste buttons)

        self.build_menu()
        self.build_toolbar()
        self.build_panes()
        self.build_context_menus()
        self.build_footer()
        self.status = tk.Label(self, anchor="w")
        self.status.pack(fill="x", side="bottom")
        self.bind_shortcuts()
        self.protocol("WM_DELETE_WINDOW", self.quit_app)

        self.editor.insert("1.0", WELCOME)
        self.dirty = False
        self.apply_theme()

    # ------------------------------------------------------------------ UI
    def build_menu(self):
        bar = tk.Menu(self)
        file_m = tk.Menu(bar, tearoff=0)
        file_m.add_command(label="New", accelerator="Ctrl+N", command=self.new)
        file_m.add_command(label="Open...", accelerator="Ctrl+O", command=self.open_file)
        file_m.add_command(label="Save", accelerator="Ctrl+S", command=self.save)
        file_m.add_command(label="Save As...", command=lambda: self.save(as_new=True))
        file_m.add_separator()
        file_m.add_command(label="Exit", command=self.quit_app)
        bar.add_cascade(label="File", menu=file_m)

        edit_m = tk.Menu(bar, tearoff=0)
        edit_m.add_command(label="Undo", accelerator="Ctrl+Z", command=lambda: self.safe_edit("edit_undo"))
        edit_m.add_command(label="Redo", accelerator="Ctrl+Y", command=lambda: self.safe_edit("edit_redo"))
        edit_m.add_separator()
        edit_m.add_command(label="Cut", accelerator="Ctrl+X", command=self.cut)
        edit_m.add_command(label="Copy", accelerator="Ctrl+C", command=self.copy)
        edit_m.add_command(label="Paste", accelerator="Ctrl+V", command=self.paste)
        edit_m.add_command(label="Select All", accelerator="Ctrl+A", command=self.select_all)
        edit_m.add_separator()
        edit_m.add_command(label="Find and Replace...", accelerator="Ctrl+F", command=self.open_find)
        edit_m.add_command(label="Copy All Markdown", command=self.copy_all)
        bar.add_cascade(label="Edit", menu=edit_m)

        ins_m = tk.Menu(bar, tearoff=0)

        def sub(label, entries):
            m = tk.Menu(ins_m, tearoff=0)
            for text, cmd in entries:
                if text is None:
                    m.add_separator()
                else:
                    m.add_command(label=text, command=cmd)
            ins_m.add_cascade(label=label, menu=m)

        tpl_m = tk.Menu(ins_m, tearoff=0)
        for name in TEMPLATES:
            tpl_m.add_command(label=name, command=lambda n=name: self.from_template(n))
        ins_m.add_cascade(label="New from Template", menu=tpl_m)
        ins_m.add_separator()
        sub("Heading", [(f"Heading {n}", lambda n=n: self.set_heading(n)) for n in range(1, 7)]
            + [(None, None), ("HTML Heading with id...", self.html_heading)])
        sub("Text Style", [("Bold", self.bold), ("Italic", self.italic), ("Bold + Italic", self.bold_italic),
                           ("Strikethrough", self.strike), ("Inline Code", self.code)])
        sub("List", [("Bullet List", lambda: self.prefix("- ")), ("Numbered List", lambda: self.prefix("1. ")),
                     ("Task List", lambda: self.prefix("- [ ] ")),
                     ("Nested Bullet List", lambda: self.put(SAMPLE_NESTED_LIST)),
                     (None, None),
                     ("Indent (nest deeper)", lambda: self.indent_lines(1)),
                     ("Outdent", lambda: self.indent_lines(-1)),
                     (None, None),
                     ("HTML List", lambda: self.put(SAMPLE_HTML_LIST)),
                     ("HTML Nested List", lambda: self.put(SAMPLE_HTML_NESTED))])
        langs = ["", "python", "java", "javascript", "typescript", "bash", "json", "html", "css", "sql", "c", "cpp"]
        sub("Code Block", [(l or "Plain", lambda l=l: self.code_block(l)) for l in langs]
            + [(None, None), ("Diff (added / removed lines)", lambda: self.code_block("diff"))])
        sub("Quote", [("Quote", lambda: self.prefix("> ")), ("Nested Quote", lambda: self.prefix("> > "))])
        sub("Link", [("Link...", self.link), ("Reference Link...", self.ref_link), ("HTML Link...", self.html_link),
                     ("Link to a Section (#anchor)...", self.anchor_link)])
        sub("Image", [("Image...", self.image), ("Linked Image...", self.linked_image),
                      ("HTML Image...", self.html_image)])
        ins_m.add_command(label="Table...", command=self.table)
        ins_m.add_command(label="Horizontal Rule", command=lambda: self.put("\n---\n"))
        ins_m.add_separator()
        alert_m = tk.Menu(ins_m, tearoff=0)
        for kind in ("NOTE", "TIP", "IMPORTANT", "WARNING", "CAUTION"):
            alert_m.add_command(label=kind, command=lambda k=kind: self.put(f"\n> [!{k}]\n> Alert text\n"))
        ins_m.add_cascade(label="GitHub Alert", menu=alert_m)
        ins_m.add_command(label="Badge...", command=self.badge)
        sub("Collapsible", [("Collapsible Section", self.details),
                            ("Collapsible Menu (nested)", lambda: self.put(SAMPLE_DETAILS_MENU))])
        bar.add_cascade(label="Insert", menu=ins_m)

        view_m = tk.Menu(bar, tearoff=0)
        for label, value in (("Split View", "split"), ("Editor Only", "editor"), ("Preview Only", "preview")):
            view_m.add_radiobutton(label=label, value=value, variable=self.layout, command=self.set_layout)
        view_m.add_separator()
        view_m.add_radiobutton(label="Dark Theme", value="dark", variable=self.theme, command=self.apply_theme)
        view_m.add_radiobutton(label="Light Theme", value="light", variable=self.theme, command=self.apply_theme)
        bar.add_cascade(label="View", menu=view_m)

        help_m = tk.Menu(bar, tearoff=0)
        help_m.add_command(label="About", command=lambda: messagebox.showinfo(
            "About", f"{APP_NAME}\nA simple desktop Markdown editor.\n\n"
                     "The preview is an approximation and is not GitHub's renderer."))
        bar.add_cascade(label="Help", menu=help_m)
        self.config(menu=bar)

    def build_footer(self):
        """Bottom-left credit: 'Developed with <heart> By Raawvie'. Only the name is a link (new Chrome tab)."""
        self.footer = tk.Frame(self)
        self.footer.pack(fill="x", side="bottom")
        self.credit_plain = []
        font = ("Segoe UI", 9)

        def plain(text):
            lbl = tk.Label(self.footer, text=text, font=font, bd=0, padx=0, pady=3)
            lbl.pack(side="left")
            self.credit_plain.append(lbl)

        plain("  Developed with ")
        # Heart is drawn by hand: emoji rendering in Tk is inconsistent (crooked / monochrome on Windows).
        self.heart = tk.Canvas(self.footer, width=14, height=13, bd=0, highlightthickness=0)
        self.heart.pack(side="left", pady=3)
        pts = []
        for i in range(60):
            t = 2 * math.pi * i / 60
            x = 16 * math.sin(t) ** 3
            y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
            pts += [7 + x * 0.41, 5.8 - y * 0.41]
        self.heart.create_polygon(pts, fill="#e8384f", outline="#e8384f")
        plain(" By ")

        self.credit_link = tk.Label(self.footer, text="Raawvie", font=("Segoe UI", 9, "underline"),
                                    cursor="hand2", bd=0, padx=0, pady=3)
        self.credit_link.pack(side="left")
        self.credit_link.bind("<Button-1>", lambda e: open_in_chrome_tab(CREDIT_URL))

    def build_toolbar(self):
        self.toolbar = tk.Frame(self)
        self.toolbar.pack(fill="x")
        rows = [
            [("New", self.new), ("Open", self.open_file), ("Save", self.save), None,
             ("Cut", self.cut), ("Copy", self.copy), ("Paste", self.paste), None,
             ("B", self.bold), ("I", self.italic), ("B+I", self.bold_italic), ("S", self.strike),
             ("Code", self.code), None,
             ("H1", lambda: self.set_heading(1)), ("H2", lambda: self.set_heading(2)),
             ("H3", lambda: self.set_heading(3)), ("H4", lambda: self.set_heading(4)),
             ("H5", lambda: self.set_heading(5)), ("H6", lambda: self.set_heading(6))],
            [("Bullets", lambda: self.prefix("- ")), ("Numbers", lambda: self.prefix("1. ")),
             ("Tasks", lambda: self.prefix("- [ ] ")), ("Indent", lambda: self.indent_lines(1)),
             ("Outdent", lambda: self.indent_lines(-1)), ("Quote", lambda: self.prefix("> ")), None,
             ("Link", self.link), ("Image", self.image), ("Table", self.table), None,
             ("Code Block", lambda: self.code_block("")), ("Diff", lambda: self.code_block("diff")),
             ("Details", self.details), ("Rule", lambda: self.put("\n---\n"))],
        ]
        self.toolbar_rows = []
        for items in rows:
            row = tk.Frame(self.toolbar)
            row.pack(fill="x")
            self.toolbar_rows.append(row)
            for item in items:
                if item is None:
                    sep = tk.Frame(row, width=1)
                    sep.pack(side="left", fill="y", padx=4, pady=4)
                    self.separators.append(sep)
                else:
                    btn = tk.Button(row, text=item[0], command=item[1], relief="flat", padx=8, bd=0)
                    btn.pack(side="left", pady=3)
                    self.buttons.append(btn)

    def build_panes(self):
        self.pw = tk.PanedWindow(self, orient="horizontal", sashwidth=5)
        self.pw.pack(fill="both", expand=True)
        self.editor = tk.Text(self.pw, wrap="word", undo=True, font=("Consolas", 12),
                              padx=10, pady=10, relief="flat", tabs=("1c",))
        self.preview = tk.Text(self.pw, wrap="word", state="disabled", font=("Segoe UI", 11),
                               padx=18, pady=10, relief="flat")
        self.pw.add(self.editor, stretch="always")
        self.pw.add(self.preview, stretch="always")
        self.editor.bind("<KeyRelease>", self.on_edit)
        self.editor.tag_config("found")
        self.renderer = Renderer(self.preview, rerender=self.refresh, open_url=open_in_chrome_tab)
        for w in (self.editor, self.preview):
            w.bind("<FocusIn>", lambda e: setattr(self, "last_text", e.widget))
        # Tk does not focus a read-only Text on click; do it so Ctrl+C works in the preview.
        self.preview.bind("<Button-1>", lambda e: e.widget.focus_set(), add="+")

    def apply_theme(self):
        c = THEMES[self.theme.get()]
        self.configure(bg=c["bg"])
        self.toolbar.config(bg=c["panel"])
        for row in self.toolbar_rows:
            row.config(bg=c["panel"])
        self.pw.config(bg=c["bg"])
        for b in self.buttons:
            b.config(bg=c["panel"], fg=c["fg"], activebackground=c["acc"], activeforeground="white")
        for s in self.separators:
            s.config(bg=c["mute"])
        self.editor.config(bg=c["code"], fg=c["fg"], insertbackground=c["fg"],
                           selectbackground=c["acc"], selectforeground="white")
        self.editor.tag_config("found", background=c["found"])
        self.preview.config(bg=c["panel"], fg=c["fg"], selectbackground=c["acc"], selectforeground="white")
        self.renderer.configure(c, self.theme.get() == "dark")
        for m in (self.menu_editor, self.menu_preview):
            m.config(bg=c["panel"], fg=c["fg"], activebackground=c["acc"], activeforeground="white",
                     disabledforeground=c["mute"], bd=0)
        self.status.config(bg=c["panel"], fg=c["mute"])
        self.footer.config(bg=c["panel"])
        self.heart.config(bg=c["panel"])
        for lbl in self.credit_plain:
            lbl.config(bg=c["panel"], fg=c["mute"])
        self.credit_link.config(bg=c["panel"], fg=CREDIT_BLUE[self.theme.get()],
                                activebackground=c["panel"])
        self.refresh()

    def set_layout(self):
        mode = self.layout.get()
        for w in (self.editor, self.preview):
            try:
                self.pw.forget(w)
            except tk.TclError:
                pass
        if mode in ("split", "editor"):
            self.pw.add(self.editor, stretch="always")
        if mode in ("split", "preview"):
            self.pw.add(self.preview, stretch="always")

    def bind_shortcuts(self):
        keys = {"b": self.bold, "i": self.italic, "k": self.link, "s": self.save,
                "o": self.open_file, "n": self.new, "f": self.open_find}
        for key, fn in keys.items():
            handler = lambda e, f=fn: (f(), "break")[1]
            self.bind(f"<Control-{key}>", handler)
            # Bound on the editor too, so Tk's built-in Emacs-style shortcuts (Ctrl+B, Ctrl+I...) don't fire.
            self.editor.bind(f"<Control-{key}>", handler)
        self.editor.bind("<Control-y>", lambda e: (self.safe_edit("edit_redo"), "break")[1])
        self.editor.bind("<Tab>", self.on_tab)
        for seq in ("<Shift-Tab>", "<ISO_Left_Tab>"):  # Shift+Tab is ISO_Left_Tab on Linux
            try:
                self.editor.bind(seq, self.on_shift_tab)
            except tk.TclError:
                pass
        # Clipboard shortcuts are handled here and stopped with "break" so Tk's own bindings
        # never run a second time (that would paste twice). Ctrl+A would otherwise jump to line start.
        for key, fn in (("c", self.copy), ("x", self.cut), ("v", self.paste), ("a", self.select_all)):
            for k in (key, key.upper()):  # upper-case too, for Caps Lock
                handler = lambda e, f=fn: (f(e.widget), "break")[1]
                self.editor.bind(f"<Control-{k}>", handler)
                self.preview.bind(f"<Control-{k}>", handler)

    # ------------------------------------------------------------- preview
    NON_EDIT_KEYS = {"Control_L", "Control_R", "Shift_L", "Shift_R", "Alt_L", "Alt_R", "Caps_Lock",
                     "Left", "Right", "Up", "Down", "Home", "End", "Prior", "Next"}

    def on_edit(self, event=None):
        if event is not None and (event.keysym in self.NON_EDIT_KEYS
                                  or (event.state & 0x4 and event.keysym.lower() in ("c", "a"))):
            return  # moving the cursor, copying or selecting is not an edit
        self.dirty = True
        if self.timer:
            self.after_cancel(self.timer)
        self.timer = self.after(150, self.refresh)

    def refresh(self):
        p = self.preview
        text = self.editor.get("1.0", "end-1c")
        top = p.yview()[0]  # keep the scroll position while the preview is redrawn
        p.config(state="normal")
        p.delete("1.0", "end")
        self.renderer.base_dir = os.path.dirname(self.path) if self.path else None
        self.renderer.render(text)
        p.config(state="disabled")
        p.yview_moveto(top)

        name = os.path.basename(self.path) if self.path else "Untitled"
        mark = " *" if self.dirty else ""
        self.status.config(text=f"  {len(text.split())} words  |  {len(text)} characters  |  {name}{mark}")
        self.title(f"{name}{mark} - {APP_NAME}")

    # ----------------------------------------------------------- formatting
    def wrap(self, before, after, placeholder):
        t = self.editor
        if t.tag_ranges("sel"):
            start, end = t.index("sel.first"), t.index("sel.last")
            chosen = t.get(start, end)
            t.delete(start, end)
        else:
            start, chosen = t.index("insert"), placeholder
        t.insert(start, before + chosen + after)
        t.focus_set()
        self.on_edit()

    def selected_lines(self):
        t = self.editor
        if t.tag_ranges("sel"):
            first = int(t.index("sel.first").split(".")[0])
            last_idx = t.index("sel.last").split(".")
            last = int(last_idx[0])
            if last_idx[1] == "0" and last > first:
                last -= 1  # selection ends at the start of a line: that line is not included
        else:
            first = last = int(t.index("insert").split(".")[0])
        return first, last

    def prefix(self, text):
        t = self.editor
        first, last = self.selected_lines()
        for n in range(first, last + 1):
            t.insert(f"{n}.0", text)
        t.focus_set()
        self.on_edit()

    def replace_line(self, n, new):
        t = self.editor
        t.delete(f"{n}.0", f"{n}.end")
        t.insert(f"{n}.0", new)

    def set_heading(self, level):
        """Make the selected lines a heading of this level (pressing it again removes the heading)."""
        t = self.editor
        first, last = self.selected_lines()
        for n in range(first, last + 1):
            line = t.get(f"{n}.0", f"{n}.end")
            m = re.match(r"(#{1,6})(\s+|$)", line)
            body = line[m.end():] if m else line
            self.replace_line(n, body if (m and len(m.group(1)) == level) else "#" * level + " " + body)
        t.focus_set()
        self.on_edit()

    def indent_lines(self, direction):
        """Indent (nest deeper) or outdent the selected lines by 4 spaces. Used for nested lists."""
        t = self.editor
        first, last = self.selected_lines()
        for n in range(first, last + 1):
            line = t.get(f"{n}.0", f"{n}.end")
            if direction > 0:
                self.replace_line(n, "    " + line)
            else:
                self.replace_line(n, line[1:] if line.startswith("\t") else re.sub(r"^ {1,4}", "", line))
        t.focus_set()
        self.on_edit()

    def on_tab(self, _event):
        t = self.editor
        line = t.get("insert linestart", "insert lineend")
        if t.tag_ranges("sel") or re.match(r"\s*([-*+]|\d+[.)])\s", line):
            self.indent_lines(1)  # Tab nests a list item / indents a selection
            return "break"
        return None  # normal Tab character

    def on_shift_tab(self, _event):
        self.indent_lines(-1)
        return "break"

    def put(self, text):
        self.editor.insert("insert", text)
        self.editor.focus_set()
        self.on_edit()

    def bold(self):
        self.wrap("**", "**", "bold text")

    def italic(self):
        self.wrap("*", "*", "italic text")

    def code(self):
        self.wrap("`", "`", "code")

    def bold_italic(self):
        self.wrap("***", "***", "bold italic text")

    def strike(self):
        self.wrap("~~", "~~", "strikethrough text")

    def code_block(self, lang=""):
        """Fenced code block with an optional language (python, java, diff ...). Wraps the selection."""
        t = self.editor
        if t.tag_ranges("sel"):
            start, end = t.index("sel.first"), t.index("sel.last")
            body = t.get(start, end)
            t.delete(start, end)
        else:
            start = t.index("insert")
            body = "- removed line\n+ added line" if lang == "diff" else "code here"
        t.insert(start, f"\n```{lang}\n{body}\n```\n")
        t.focus_set()
        self.on_edit()

    def details(self):
        self.put("\n<details>\n<summary>Summary</summary>\n\nHidden content\n\n</details>\n")

    def html_link(self):
        url = simpledialog.askstring("HTML Link", "URL:", initialvalue="https://", parent=self)
        if url:
            self.wrap(f'<a href="{url}">', "</a>", "link text")

    def anchor_link(self):
        ident = simpledialog.askstring("Link to a Section", "Section id (for example Top-doc or my-heading):",
                                       parent=self)
        if ident:
            self.wrap("[", f"](#{ident.lstrip('#')})", "Go to section")

    def ref_link(self):
        text = simpledialog.askstring("Reference Link", "Link text:", parent=self)
        if not text:
            return
        ref = simpledialog.askstring("Reference Link", "Reference name:", initialvalue="link", parent=self)
        url = ref and simpledialog.askstring("Reference Link", "URL:", initialvalue="https://", parent=self)
        if not url:
            return
        self.put(f"[{text}][{ref}]")
        doc = self.editor.get("1.0", "end-1c")
        definition = f"[{ref}]: {url}"
        if definition not in doc:  # the definition goes at the end of the document
            self.editor.insert("end", ("" if doc.endswith("\n") else "\n") + "\n" + definition + "\n")
            self.on_edit()

    def linked_image(self):
        alt = simpledialog.askstring("Linked Image", "Alt text:", parent=self)
        src = simpledialog.askstring("Linked Image", "Image URL:", initialvalue="https://", parent=self)
        href = src and simpledialog.askstring("Linked Image", "Link URL (opens on click):",
                                              initialvalue="https://", parent=self)
        if href:
            self.put(f"[![{alt or ''}]({src})]({href})")

    def html_image(self):
        src = simpledialog.askstring("HTML Image", "Image URL:", initialvalue="https://", parent=self)
        if not src:
            return
        width = simpledialog.askstring("HTML Image", "Width in pixels (optional):", parent=self)
        size = f' width="{width.strip()}"' if width and width.strip().isdigit() else ""
        self.put(f'<img src="{src}"{size}/>')

    def html_heading(self):
        level = simpledialog.askinteger("HTML Heading", "Level (1-6):", initialvalue=1, minvalue=1, maxvalue=6,
                                        parent=self)
        ident = level and simpledialog.askstring("HTML Heading", "Section id (used by #links):",
                                                 initialvalue="Top-doc", parent=self)
        if ident:
            self.put(f'\n<h{level} id="{ident}">Heading {level}</h{level}>\n')

    def link(self):
        url = simpledialog.askstring("Link", "URL:", initialvalue="https://", parent=self)
        if url:
            self.wrap("[", f"]({url})", "link text")

    def image(self):
        alt = simpledialog.askstring("Image", "Alt text:", parent=self)
        url = simpledialog.askstring("Image", "Image URL:", initialvalue="https://", parent=self)
        if url:
            self.put(f"![{alt or ''}]({url})")

    def table(self):
        cols = simpledialog.askinteger("Table", "Columns:", initialvalue=3, minvalue=1, maxvalue=10, parent=self)
        rows = simpledialog.askinteger("Table", "Rows:", initialvalue=2, minvalue=1, maxvalue=50, parent=self)
        if cols and rows:
            head = "| " + " | ".join(f"Column {i + 1}" for i in range(cols)) + " |"
            sep = "|" + "|".join(["---"] * cols) + "|"
            body = "\n".join("| " + " | ".join(["  "] * cols) + " |" for _ in range(rows))
            self.put(f"\n{head}\n{sep}\n{body}\n")

    def badge(self):
        label = simpledialog.askstring("Badge", "Label (left side):", initialvalue="license", parent=self)
        if not label:
            return
        message = simpledialog.askstring("Badge", "Message (right side):", initialvalue="MIT", parent=self)
        color = simpledialog.askstring("Badge", "Color:", initialvalue="blue", parent=self) or "blue"
        if message:
            esc = lambda s: quote(s.replace("-", "--").replace("_", "__"), safe="")
            self.put(f"![{label}](https://img.shields.io/badge/{esc(label)}-{esc(message)}-{quote(color)})")

    # ---------------------------------------------------------------- edit
    def safe_edit(self, action):
        try:
            getattr(self.editor, action)()
            self.on_edit()
        except tk.TclError:
            pass  # nothing to undo/redo

    # ----------------------------------------------------------- clipboard
    def target(self, widget=None):
        """The text pane an action applies to: the given one, else the focused one, else the editor."""
        if widget in (self.editor, self.preview):
            return widget
        try:
            focused = self.focus_get()
        except KeyError:
            focused = None
        if focused in (self.editor, self.preview):
            return focused
        return self.last_text or self.editor

    def copy(self, widget=None):
        w = self.target(widget)
        if not w.tag_ranges("sel"):
            return
        self.clipboard_clear()
        self.clipboard_append(w.get("sel.first", "sel.last"))
        self.status.config(text="  Copied to clipboard")

    def cut(self, widget=None):
        w = self.target(widget)
        if w is not self.editor or not w.tag_ranges("sel"):
            return
        self.copy(w)
        w.edit_separator()
        w.delete("sel.first", "sel.last")
        w.edit_separator()
        self.on_edit()

    def paste(self, widget=None):
        w = self.target(widget)
        if w is not self.editor:
            return  # the preview is read-only
        try:
            text = self.clipboard_get()
        except tk.TclError:
            return  # clipboard is empty or holds something that is not text
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        w.edit_separator()
        if w.tag_ranges("sel"):
            w.delete("sel.first", "sel.last")  # pasting over a selection replaces it
        w.insert("insert", text)
        w.see("insert")
        w.edit_separator()
        w.focus_set()
        self.on_edit()

    def delete_selection(self, widget=None):
        w = self.target(widget)
        if w is self.editor and w.tag_ranges("sel"):
            w.edit_separator()
            w.delete("sel.first", "sel.last")
            w.edit_separator()
            self.on_edit()

    def select_all(self, widget=None):
        w = self.target(widget)
        w.tag_remove("sel", "1.0", "end")
        w.tag_add("sel", "1.0", "end-1c")

    def build_context_menus(self):
        """Right-click menus for the editor (Cut/Copy/Paste/Delete/Select All) and the preview (Copy/Select All)."""
        ed, pv = self.editor, self.preview
        self.menu_editor = tk.Menu(self, tearoff=0)
        self.menu_editor.add_command(label="Cut", accelerator="Ctrl+X", command=lambda: self.cut(ed))
        self.menu_editor.add_command(label="Copy", accelerator="Ctrl+C", command=lambda: self.copy(ed))
        self.menu_editor.add_command(label="Paste", accelerator="Ctrl+V", command=lambda: self.paste(ed))
        self.menu_editor.add_command(label="Delete", command=lambda: self.delete_selection(ed))
        self.menu_editor.add_separator()
        self.menu_editor.add_command(label="Select All", accelerator="Ctrl+A", command=lambda: self.select_all(ed))

        self.menu_preview = tk.Menu(self, tearoff=0)
        self.menu_preview.add_command(label="Copy", accelerator="Ctrl+C", command=lambda: self.copy(pv))
        self.menu_preview.add_separator()
        self.menu_preview.add_command(label="Select All", accelerator="Ctrl+A", command=lambda: self.select_all(pv))

        # Right button is Button-3 on Windows/Linux; on macOS it is Button-2 or Ctrl+click.
        seqs = ["<Button-3>"] + (["<Button-2>", "<Control-Button-1>"] if sys.platform == "darwin" else [])
        for widget, menu in ((ed, self.menu_editor), (pv, self.menu_preview)):
            for seq in seqs:
                widget.bind(seq, lambda e, m=menu: self.show_context_menu(e, m))

    def show_context_menu(self, event, menu):
        w = event.widget
        w.focus_set()
        has_sel = bool(w.tag_ranges("sel"))
        if w is self.editor:
            if not has_sel:
                w.mark_set("insert", f"@{event.x},{event.y}")  # paste lands where you right-clicked
            try:
                has_clip = bool(self.clipboard_get())
            except tk.TclError:
                has_clip = False
            state = lambda ok: "normal" if ok else "disabled"
            menu.entryconfig(0, state=state(has_sel))   # Cut
            menu.entryconfig(1, state=state(has_sel))   # Copy
            menu.entryconfig(2, state=state(has_clip))  # Paste
            menu.entryconfig(3, state=state(has_sel))   # Delete
        else:
            menu.entryconfig(0, state="normal" if has_sel else "disabled")  # Copy
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def copy_all(self):
        self.clipboard_clear()
        self.clipboard_append(self.editor.get("1.0", "end-1c"))
        self.status.config(text="  Markdown copied to clipboard")

    def open_find(self):
        if self.find_win and self.find_win.winfo_exists():
            self.find_win.lift()
            return
        c = THEMES[self.theme.get()]
        win = self.find_win = tk.Toplevel(self)
        win.title("Find and Replace")
        win.configure(bg=c["panel"])
        win.transient(self)
        win.resizable(False, False)
        find_var, repl_var = tk.StringVar(), tk.StringVar()
        for row, (label, var) in enumerate((("Find:", find_var), ("Replace with:", repl_var))):
            tk.Label(win, text=label, bg=c["panel"], fg=c["fg"]).grid(row=row, column=0, padx=8, pady=6, sticky="e")
            tk.Entry(win, textvariable=var, width=30).grid(row=row, column=1, padx=8, pady=6)

        def find_next():
            t = self.editor
            t.tag_remove("found", "1.0", "end")
            needle = find_var.get()
            if not needle:
                return
            pos = t.search(needle, "insert", nocase=True, stopindex="end") or t.search(needle, "1.0", nocase=True)
            if not pos:
                messagebox.showinfo("Find", "No matches found.", parent=win)
                return
            end = f"{pos}+{len(needle)}c"
            t.tag_add("found", pos, end)
            t.mark_set("insert", end)
            t.see(pos)

        def replace_one():
            t = self.editor
            ranges = t.tag_ranges("found")
            if ranges:
                t.delete(ranges[0], ranges[1])
                t.insert(ranges[0], repl_var.get())
                t.tag_remove("found", "1.0", "end")
                self.on_edit()
            find_next()

        def replace_all():
            needle = find_var.get()
            if not needle:
                return
            text = self.editor.get("1.0", "end-1c")
            new_text, count = re.subn(re.escape(needle), lambda _m: repl_var.get(), text, flags=re.I)
            if count:
                self.editor.delete("1.0", "end")
                self.editor.insert("1.0", new_text)
                self.on_edit()
            messagebox.showinfo("Replace All", f"{count} replacement(s) made.", parent=win)

        row = tk.Frame(win, bg=c["panel"])
        row.grid(row=2, column=0, columnspan=2, pady=8)
        for text, cmd in (("Find Next", find_next), ("Replace", replace_one), ("Replace All", replace_all)):
            tk.Button(row, text=text, command=cmd, padx=8).pack(side="left", padx=4)

    # --------------------------------------------------------------- files
    def confirm_discard(self):
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel(APP_NAME, "You have unsaved changes. Save them first?", parent=self)
        if answer is None:
            return False
        return self.save() if answer else True

    def load_text(self, text, path=None):
        self.renderer.open_details.clear()
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", text)
        self.editor.edit_reset()
        self.path, self.dirty = path, False
        self.refresh()

    def new(self):
        if self.confirm_discard():
            self.load_text("")

    def from_template(self, name):
        if self.confirm_discard():
            self.load_text(TEMPLATES[name])
            self.dirty = bool(TEMPLATES[name])
            self.refresh()

    def open_file(self):
        if not self.confirm_discard():
            return
        path = filedialog.askopenfilename(
            filetypes=[("Markdown", "*.md *.markdown *.txt"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                self.load_text(f.read(), path)
        except (OSError, UnicodeDecodeError) as err:
            messagebox.showerror("Error", f"Could not open the file:\n{err}")

    def save(self, as_new=False):
        if as_new or not self.path:
            chosen = filedialog.asksaveasfilename(defaultextension=".md", filetypes=[("Markdown", "*.md")])
            if not chosen:
                return False
            self.path = chosen
        try:
            with open(self.path, "w", encoding="utf-8", newline="\n") as f:
                f.write(self.editor.get("1.0", "end-1c"))
        except OSError as err:
            messagebox.showerror("Error", f"Could not save the file:\n{err}")
            return False
        self.dirty = False
        self.refresh()
        return True

    def quit_app(self):
        if self.confirm_discard():
            self.destroy()


if __name__ == "__main__":
    App().mainloop()
