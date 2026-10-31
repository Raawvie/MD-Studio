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
- **Bold**, *italic* and `inline code`
- [ ] A task to do
- [x] A finished task

> [!TIP]
> Use the Insert menu for templates, badges and alerts.

| Name | Value |
|------|-------|
| A    | 1     |
"""

CREDIT_URL = "https://github.com/Raawvie"
CREDIT_BLUE = {"dark": "#58a6ff", "light": "#0969da"}  # classic link blues

INLINE = re.compile(r"(\*\*.+?\*\*|`.+?`|\*[^*\s][^*]*?\*|_[^_\s][^_]*?_|\[[^\]]+\]\([^)]+\))")


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

        self.build_menu()
        self.build_toolbar()
        self.build_panes()
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
        edit_m.add_command(label="Find and Replace...", accelerator="Ctrl+F", command=self.open_find)
        edit_m.add_command(label="Copy All Markdown", command=self.copy_all)
        bar.add_cascade(label="Edit", menu=edit_m)

        ins_m = tk.Menu(bar, tearoff=0)
        tpl_m = tk.Menu(ins_m, tearoff=0)
        for name in TEMPLATES:
            tpl_m.add_command(label=name, command=lambda n=name: self.from_template(n))
        ins_m.add_cascade(label="New from Template", menu=tpl_m)
        alert_m = tk.Menu(ins_m, tearoff=0)
        for kind in ("NOTE", "TIP", "IMPORTANT", "WARNING", "CAUTION"):
            alert_m.add_command(label=kind, command=lambda k=kind: self.put(f"\n> [!{k}]\n> Alert text\n"))
        ins_m.add_cascade(label="GitHub Alert", menu=alert_m)
        ins_m.add_command(label="Badge...", command=self.badge)
        ins_m.add_command(label="Collapsible Section",
                          command=lambda: self.put("\n<details>\n<summary>Summary</summary>\n\nHidden content\n\n</details>\n"))
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
        items = [
            ("New", self.new), ("Open", self.open_file), ("Save", self.save), None,
            ("B", self.bold), ("I", self.italic), ("Code", self.code), None,
            ("H1", lambda: self.prefix("# ")), ("H2", lambda: self.prefix("## ")),
            ("H3", lambda: self.prefix("### ")), None,
            ("Bullets", lambda: self.prefix("- ")), ("Numbers", lambda: self.prefix("1. ")),
            ("Tasks", lambda: self.prefix("- [ ] ")), ("Quote", lambda: self.prefix("> ")), None,
            ("Link", self.link), ("Image", self.image), ("Table", self.table),
            ("Rule", lambda: self.put("\n---\n")),
        ]
        for item in items:
            if item is None:
                sep = tk.Frame(self.toolbar, width=1)
                sep.pack(side="left", fill="y", padx=4, pady=4)
                self.separators.append(sep)
            else:
                btn = tk.Button(self.toolbar, text=item[0], command=item[1], relief="flat", padx=8, bd=0)
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

    def apply_theme(self):
        c = THEMES[self.theme.get()]
        self.configure(bg=c["bg"])
        self.toolbar.config(bg=c["panel"])
        self.pw.config(bg=c["bg"])
        for b in self.buttons:
            b.config(bg=c["panel"], fg=c["fg"], activebackground=c["acc"], activeforeground="white")
        for s in self.separators:
            s.config(bg=c["mute"])
        self.editor.config(bg=c["code"], fg=c["fg"], insertbackground=c["fg"],
                           selectbackground=c["acc"], selectforeground="white")
        self.editor.tag_config("found", background=c["found"])
        p = self.preview
        p.config(bg=c["panel"], fg=c["fg"])
        p.tag_config("h1", font=("Segoe UI", 22, "bold"), spacing1=10)
        p.tag_config("h2", font=("Segoe UI", 17, "bold"), spacing1=8)
        p.tag_config("h3", font=("Segoe UI", 14, "bold"), spacing1=6)
        p.tag_config("bold", font=("Segoe UI", 11, "bold"))
        p.tag_config("italic", font=("Segoe UI", 11, "italic"))
        p.tag_config("code", font=("Consolas", 11), background=c["code"])
        p.tag_config("quote", foreground=c["mute"], lmargin1=16, lmargin2=16)
        p.tag_config("link", foreground=c["link"], underline=True)
        p.tag_config("label", foreground=c["acc"], font=("Segoe UI", 11, "bold"))
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

    # ------------------------------------------------------------- preview
    def on_edit(self, _event=None):
        self.dirty = True
        if self.timer:
            self.after_cancel(self.timer)
        self.timer = self.after(150, self.refresh)

    def refresh(self):
        p = self.preview
        p.config(state="normal")
        p.delete("1.0", "end")
        text = self.editor.get("1.0", "end-1c")
        in_code = False
        for line in text.split("\n"):
            if line.strip().startswith("```"):
                in_code = not in_code
                continue
            if in_code:
                p.insert("end", line + "\n", "code")
            else:
                self.render_line(line)
                p.insert("end", "\n")
        p.config(state="disabled")

        name = os.path.basename(self.path) if self.path else "Untitled"
        mark = " *" if self.dirty else ""
        self.status.config(text=f"  {len(text.split())} words  |  {len(text)} characters  |  {name}{mark}")
        self.title(f"{name}{mark} - {APP_NAME}")

    def render_line(self, line):
        p = self.preview
        if m := re.match(r"(#{1,6})\s+(.*)", line):
            self.inline(m.group(2), (f"h{min(len(m.group(1)), 3)}",))
        elif re.fullmatch(r"\s*([-*_])\1{2,}\s*", line):
            p.insert("end", "\u2500" * 40)
        elif m := re.match(r">\s?(.*)", line):
            alert = re.match(r"\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]", m.group(1), re.I)
            if alert:
                p.insert("end", alert.group(1).upper(), ("label",))
            else:
                self.inline(m.group(1), ("quote",))
        elif m := re.match(r"(\s*)[-*+]\s+(\[[ xX]\]\s+)?(.*)", line):
            if m.group(2):
                mark = "\u2611 " if "x" in m.group(2).lower() else "\u2610 "
            else:
                mark = "\u2022 "
            p.insert("end", "    " * (len(m.group(1)) // 2) + mark)
            self.inline(m.group(3))
        elif m := re.match(r"(\s*)(\d+)\.\s+(.*)", line):
            p.insert("end", "    " * (len(m.group(1)) // 2) + m.group(2) + ". ")
            self.inline(m.group(3))
        elif line.strip().startswith("|"):
            if not re.fullmatch(r"[\s|:-]+", line):
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                p.insert("end", "  \u2502  ".join(cells), ("code",))
        else:
            self.inline(line)

    def inline(self, text, tags=()):
        p = self.preview
        text = re.sub(r"!\[(.*?)\]\(.*?\)", "[image: \\1]", text)
        for part in INLINE.split(text):
            if not part:
                continue
            if part.startswith("**") and part.endswith("**") and len(part) > 4:
                p.insert("end", part[2:-2], tags + ("bold",))
            elif part.startswith("`") and part.endswith("`") and len(part) > 2:
                p.insert("end", part[1:-1], tags + ("code",))
            elif part[0] in "*_" and len(part) > 2 and part[-1] == part[0]:
                p.insert("end", part[1:-1], tags + ("italic",))
            elif m := re.fullmatch(r"\[(.*)\]\((.*)\)", part):
                p.insert("end", m.group(1), tags + ("link",))
            else:
                p.insert("end", part, tags)

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

    def prefix(self, text):
        t = self.editor
        if t.tag_ranges("sel"):
            first = int(t.index("sel.first").split(".")[0])
            last = int(t.index("sel.last").split(".")[0])
        else:
            first = last = int(t.index("insert").split(".")[0])
        for n in range(first, last + 1):
            t.insert(f"{n}.0", text)
        t.focus_set()
        self.on_edit()

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
