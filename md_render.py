"""Markdown + HTML preview renderer for Markdown Studio.

Draws styled text into a read-only tk.Text widget. It understands the Markdown and the
HTML that GitHub READMEs use: headings (# and <h1>), nested lists (Markdown and <ul>/<ol>),
bold / italic / strikethrough, code blocks with a language (+ diff colouring), nested block
quotes, GitHub alerts, links (inline, reference, <a>, #anchors), images (![](), <img>, linked
images), tables (Markdown and <table>), collapsible <details>/<summary> and horizontal rules.

Images need network access for http(s) sources. With Pillow installed (pip install pillow) all
common formats work; without it only PNG and GIF are shown.
"""
import base64
import html
import io
import os
import pathlib
import queue
import re
import threading
import urllib.request
import webbrowser
from html.parser import HTMLParser
from urllib.parse import unquote

try:  # optional: JPEG / WebP / BMP ... support and better scaling
    from PIL import Image, ImageTk
except Exception:  # pragma: no cover
    Image = ImageTk = None

FONT, MONO = "Segoe UI", "Consolas"
SIZES = {1: 24, 2: 19, 3: 15, 4: 13, 5: 12, 6: 11}
BULLETS = ("\u2022", "\u25e6", "\u25aa")  # level 1, 2, 3 bullets
ALERT_COLORS = {"NOTE": "#388bfd", "TIP": "#3fb950", "IMPORTANT": "#ab7df8",
                "WARNING": "#d29922", "CAUTION": "#f85149"}
MAX_IMG_WIDTH = 460

# ---------------------------------------------------------------- patterns
FENCE = re.compile(r"^\s*(`{3,}|~{3,})\s*([^\s`~]*)(?:\s.*)?$")
HEADING = re.compile(r"^\s{0,3}(#{1,6})(?:\s+(.*?))?(?:\s+#+)?\s*$")
RULE = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$")
LIST = re.compile(r"^(\s*)([-*+]|\d{1,9}[.)])\s+(.*)$")
QUOTE = re.compile(r"^\s{0,3}((?:>\s?)+)(.*)$")
REF_DEF = re.compile(r"^\s{0,3}\[([^\]]+)\]:\s*(\S+)(?:\s+[\"'(].*)?\s*$")
HTML_BLOCK = re.compile(
    r"^\s{0,3}<(?:/?(?:h[1-6]|ul|ol|li|details|summary|p|div|pre|table|thead|tbody|tr|td|th|hr|"
    r"blockquote|center|section|figure|picture)\b|!--)", re.I)
ATTR = re.compile(r"""([\w:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""")

HTML_STYLE = {"b": "bold", "strong": "bold", "i": "italic", "em": "italic", "u": "underline",
              "ins": "underline", "s": "strike", "del": "strike", "strike": "strike",
              "code": "code", "kbd": "kbd", "mark": "mark", "sub": "sub", "sup": "sup"}

INLINE = re.compile("|".join([
    r"(?P<esc>\\(?P<ech>[\\`*_{}\[\]()#+\-.!|<>~]))",
    r"(?P<comment><!--.*?-->)",
    r"(?P<code>(?P<tick>`+)(?P<ctext>.+?)(?P=tick))",
    r"(?P<img>!\[(?P<ialt>[^\]]*)\]\((?P<isrc>[^)\s]+)(?:\s+\"[^\"]*\")?\))",
    r"(?P<link>\[(?P<ltext>(?:[^\[\]]|\[[^\]]*\])+)\]\((?P<lhref>[^)\s]*)(?:\s+\"[^\"]*\")?\))",
    r"(?P<reflink>\[(?P<rtext>[^\]]+)\]\[(?P<rid>[^\]]*)\])",
    r"(?P<htmlimg><img\b[^>]*>)",
    r"(?P<htmla><a\b[^>]*>(?P<atext>.*?)</a\s*>)",
    r"(?P<htmlbr><br\s*/?>)",
    r"(?P<htmltag><(?P<tname>b|strong|i|em|u|ins|s|del|strike|code|kbd|mark|sub|sup|small|span|"
    r"font|center|p|div)\b[^>]*>(?P<ttext>.*?)</(?P=tname)\s*>)",
    r"(?P<autolink><(?P<aurl>https?://[^>\s]+)>)",
    r"(?P<bolditalic>(?P<bich>\*\*\*|___)(?P<bitext>.+?)(?P=bich))",
    r"(?P<bold>(?P<bch>\*\*|__)(?P<btext>.+?)(?P=bch))",
    r"(?P<italic>(?<![\w*])(?P<ich>[*_])(?P<itext>[^\s*_](?:.*?[^\s])?)(?P=ich)(?![\w*]))",
    r"(?P<strike>~~(?P<stext>.+?)~~)",
]), re.I | re.S)


def attrs(tag_text):
    return {m.group(1).lower(): html.unescape(m.group(2) or m.group(3) or m.group(4) or "")
            for m in ATTR.finditer(tag_text)}


def parse_width(value):
    return int(value) if value and re.fullmatch(r"\d+", value.strip()) else None


def plain(text):
    """Visible text of a Markdown snippet (markers removed)."""
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"(\*\*\*|___|\*\*|__|~~|`)", "", text)
    return html.unescape(text).replace("\\|", "|").strip()


def is_sep(line):
    t = line.strip()
    return "|" in t and "-" in t and set(t) <= set("|:- \t")


def split_row(line):
    t = line.strip()
    if t.startswith("|"):
        t = t[1:]
    if t.endswith("|") and not t.endswith("\\|"):
        t = t[:-1]
    return [c.replace("\\|", "|").strip() for c in re.split(r"(?<!\\)\|", t)]


class Renderer:
    def __init__(self, widget, rerender, open_url):
        self.w = widget
        self.rerender = rerender        # called when the preview must be redrawn (details toggled, image loaded)
        self.open_url = open_url        # opens http(s) links in the browser
        self.base_dir = None            # folder of the open file, for relative images / links
        self.open_details = set()       # indexes of <details> blocks the user expanded
        self.images = {}                # (src, width, dir) -> PhotoImage | "loading" | "failed"
        self.pending = queue.Queue()
        self.polling = False
        self.mtags = set()
        self.anchors, self.slugs, self.refs = {}, {}, {}
        self.det_stack, self.det_counter, self.nlink = [], 0, 0
        self.list_indents = []
        widget.tag_bind("link", "<Enter>", lambda e: widget.config(cursor="hand2"))
        widget.tag_bind("link", "<Leave>", lambda e: widget.config(cursor="xterm"))
        widget.tag_bind("summary", "<Enter>", lambda e: widget.config(cursor="hand2"))
        widget.tag_bind("summary", "<Leave>", lambda e: widget.config(cursor="xterm"))

    # ------------------------------------------------------------- styling
    def configure(self, c, dark):
        w = self.w
        w.config(spacing3=5)
        for n, size in SIZES.items():
            w.tag_config(f"h{n}", font=(FONT, size, "bold"), spacing1=12 if n < 3 else 8, spacing3=6,
                         foreground=c["fg"] if n < 6 else c["mute"])
        w.tag_config("bold", font=(FONT, 11, "bold"))
        w.tag_config("italic", font=(FONT, 11, "italic"))
        w.tag_config("bolditalic", font=(FONT, 11, "bold italic"))
        w.tag_config("strike", overstrike=True)
        w.tag_config("underline", underline=True)
        w.tag_config("code", font=(MONO, 11), background=c["code"])
        w.tag_config("kbd", font=(MONO, 10), background=c["code"], relief="raised", borderwidth=1)
        w.tag_config("mark", background="#7a6200" if dark else "#ffe066")
        w.tag_config("sub", offset=-3, font=(FONT, 9))
        w.tag_config("sup", offset=4, font=(FONT, 9))
        w.tag_config("link", foreground=c["link"], underline=True)
        w.tag_config("summary", foreground=c["acc"], font=(FONT, 11, "bold"))
        w.tag_config("bullet", foreground=c["acc"])
        w.tag_config("quote", foreground=c["mute"])
        w.tag_config("qbar", foreground=c["acc"])
        w.tag_config("hr", foreground=c["mute"])
        w.tag_config("imgph", foreground=c["mute"], font=(FONT, 10, "italic"))
        w.tag_config("codeblock", font=(MONO, 11), background=c["code"], foreground=c["fg"],
                     spacing1=0, spacing3=0)
        w.tag_config("codelang", font=(MONO, 9, "italic"), background=c["code"], foreground=c["mute"],
                     spacing1=6, spacing3=0)
        w.tag_config("codeend", spacing3=10)
        w.tag_config("diff_add", background="#1f4d2b" if dark else "#ccf0d6")
        w.tag_config("diff_del", background="#5a2229" if dark else "#ffd7d5")
        w.tag_config("diff_hunk", foreground=c["acc"])
        w.tag_config("table", font=(MONO, 11), spacing1=0, spacing3=0)
        w.tag_config("tablehead", font=(MONO, 11, "bold"))
        w.tag_config("tableend", spacing3=10)
        for kind, colour in ALERT_COLORS.items():
            w.tag_config(f"alert_{kind}", foreground=colour, font=(FONT, 11, "bold"))

    def margin_tag(self, kind, lm1, lm2, rm=0, tabs=None):
        name = f"{kind}_{lm1}_{lm2}_{rm}"
        if name not in self.mtags:
            opts = {"lmargin1": lm1, "lmargin2": lm2, "rmargin": rm}
            if tabs:
                opts["tabs"] = tabs
            self.w.tag_config(name, **opts)
            self.mtags.add(name)
        return name

    def indent(self):
        return 22 * len(self.det_stack)

    def pad_tags(self):
        ind = self.indent()
        return (self.margin_tag("ind", ind, ind),) if ind else ()

    def style_tags(self, base, style):
        tags = list(base)
        heading = any(re.fullmatch(r"h[1-6]", t) for t in base)
        s = set(style)
        if not heading:  # headings keep their own big font
            if "bold" in s and "italic" in s:
                tags.append("bolditalic")
            elif "bold" in s:
                tags.append("bold")
            elif "italic" in s:
                tags.append("italic")
        for name in ("code", "kbd", "mark", "sub", "sup", "strike", "underline"):
            if name in s:
                tags.append(name)
        links = [x for x in style if x.startswith("lnk")]
        if links:
            tags.append("link")
            tags.extend(links)
        return tuple(tags)

    # ------------------------------------------------------------ plumbing
    def hidden(self):
        return any(not d[1] for d in self.det_stack)

    def out(self, text, tags=()):
        if not self.hidden() and text:
            self.w.insert("end", text, tuple(tags))

    def text(self, s, base=(), style=(), raw=False):
        if not raw:
            s = html.unescape(s)
        if s:
            self.out(s, self.style_tags(base, style))

    def begin_block(self):
        """A <details> without <summary> gets a default one before its first content."""
        if self.det_stack and not self.det_stack[-1][2]:
            self.det_summary("Details")

    # ------------------------------------------------------------- anchors
    def add_anchor(self, ident):
        if not ident:
            return
        w = self.w
        mark = f"anc{len(self.anchors)}"
        w.mark_set(mark, "end-1c")
        w.mark_gravity(mark, "left")
        self.anchors.setdefault(ident, mark)
        self.anchors.setdefault(ident.lower(), mark)

    def slug(self, text):
        s = re.sub(r"[^\w\- ]", "", text.lower()).strip().replace(" ", "-")
        if not s:
            return ""
        n = self.slugs.get(s, 0)
        self.slugs[s] = n + 1
        return s if n == 0 else f"{s}-{n}"

    def goto(self, ident):
        for key in (ident, ident.lower(), unquote(ident), unquote(ident).lower()):
            mark = self.anchors.get(key)
            if mark:
                self.w.yview(mark)
                return

    # --------------------------------------------------------------- links
    def link_tag(self, href):
        self.nlink += 1
        name = f"lnk{self.nlink}"
        self.w.tag_bind(name, "<Button-1>", lambda e, h=href: self.open_link(h))
        return name

    def open_link(self, url):
        url = html.unescape(url.strip())
        if url.startswith("#"):
            self.goto(url[1:])
        elif re.match(r"^(https?|mailto):", url, re.I):
            self.open_url(url)
        elif url:
            path = url if os.path.isabs(url) else os.path.join(self.base_dir or "", url)
            if os.path.exists(path):
                webbrowser.open(pathlib.Path(path).resolve().as_uri())

    # -------------------------------------------------------------- images
    def image(self, src, alt="", base=(), style=(), width=None):
        if self.hidden():
            return
        src = html.unescape(src.strip())
        tags = self.style_tags(base, style)
        photo = self.get_image(src, width)
        if photo in ("loading", "failed"):
            label = alt or "image"
            note = "[loading image: " if photo == "loading" else "[image: "
            self.out(f"{note}{label}]", tags + ("imgph",))
            return
        w = self.w
        start = w.index("end-1c")
        w.image_create("end", image=photo, padx=2, pady=2)
        stop = w.index("end-1c")
        for t in tags:
            w.tag_add(t, start, stop)

    def get_image(self, src, width):
        key = (src, width, self.base_dir)
        state = self.images.get(key)
        if state is None:
            self.images[key] = "loading"
            threading.Thread(target=self._fetch, args=(src, key), daemon=True).start()
            if not self.polling:
                self.polling = True
                self.w.after(200, self.poll)
            return "loading"
        return state

    def _fetch(self, src, key):  # worker thread: no Tk calls here
        try:
            if re.match(r"https?://", src, re.I):
                req = urllib.request.Request(src, headers={"User-Agent": "MarkdownStudio"})
                data = urllib.request.urlopen(req, timeout=15).read(10_000_000)
            else:
                path = src if os.path.isabs(src) else os.path.join(key[2] or "", unquote(src))
                with open(path, "rb") as f:
                    data = f.read(10_000_000)
        except Exception:
            data = None
        self.pending.put((key, data))

    def make_photo(self, data, width):
        limit = min(width, MAX_IMG_WIDTH) if width else MAX_IMG_WIDTH
        if Image is not None:
            im = Image.open(io.BytesIO(data))
            im.load()
            im = im.convert("RGBA")
            if width or im.width > limit:
                im = im.resize((limit, max(1, round(im.height * limit / im.width))), Image.LANCZOS)
            return ImageTk.PhotoImage(im)
        import tkinter as tk  # PNG / GIF only
        photo = tk.PhotoImage(data=base64.b64encode(data))
        if photo.width() > limit:
            photo = photo.subsample(-(-photo.width() // limit))
        return photo

    def poll(self):  # main thread: turn downloaded bytes into images
        changed = False
        try:
            while True:
                key, data = self.pending.get_nowait()
                try:
                    self.images[key] = self.make_photo(data, key[1]) if data else "failed"
                except Exception:
                    self.images[key] = "failed"
                changed = True
        except queue.Empty:
            pass
        still = any(v == "loading" for v in self.images.values())
        self.polling = still
        if still:
            self.w.after(200, self.poll)
        if changed:
            self.rerender()

    # ------------------------------------------------------------- details
    def det_start(self):
        self.begin_block()
        idx = self.det_counter
        self.det_counter += 1
        self.det_stack.append([idx, idx in self.open_details, False])

    def det_end(self):
        if self.det_stack:
            if not self.det_stack[-1][2]:
                self.det_summary("Details")
            self.det_stack.pop()

    def det_summary(self, text, level=None):
        d = self.det_stack[-1]
        d[2] = True
        if any(not e[1] for e in self.det_stack[:-1]):
            return  # an outer <details> is collapsed
        lvl = len(self.det_stack) - 1 if level is None else level
        ind = 22 * lvl
        tag = f"det{d[0]}"
        self.w.tag_bind(tag, "<Button-1>", lambda e, k=d[0]: self.toggle(k))
        marker = "\u25bc " if d[1] else "\u25b6 "
        self.w.insert("end", marker + html.unescape(text) + "\n",
                      (self.margin_tag("ind", ind, ind), "summary", tag))

    def toggle(self, idx):
        if idx in self.open_details:
            self.open_details.discard(idx)
        else:
            self.open_details.add(idx)
        self.rerender()

    # ----------------------------------------------------- block emitters
    def heading(self, level, body, plain_text, anchor=None):
        self.begin_block()
        self.add_anchor(anchor)
        self.add_anchor(self.slug(plain_text))
        tags = (f"h{level}",) + self.pad_tags()
        body(tags)
        self.out("\n", tags)

    def paragraph(self, body):
        self.begin_block()
        tags = self.pad_tags()
        body(tags)
        self.out("\n", tags)

    def list_item(self, level, marker, body, checked=None):
        self.begin_block()
        lm = self.indent() + 16 + 24 * level
        tag = self.margin_tag("li", lm, lm + 22, tabs=(lm + 22,))
        if checked is not None:
            glyph = "\u2611" if checked else "\u2610"
        elif marker:
            glyph = marker
        else:
            glyph = BULLETS[level % 3]
        self.out(glyph + "\t", (tag, "bullet"))
        body((tag,))
        self.out("\n", (tag,))

    def quote_line(self, level, body, alert=None):
        self.begin_block()
        lm2 = self.indent() + 18 * level
        tag = self.margin_tag("q", self.indent(), lm2, tabs=(lm2,))
        self.out("\u2503" * level + "\t", (tag, "qbar"))
        if alert:
            self.out(alert.title(), (tag, f"alert_{alert}"))
        else:
            body((tag, "quote"))
        self.out("\n", (tag,))

    def rule(self):
        self.begin_block()
        self.out("\u2500" * 56 + "\n", self.pad_tags() + ("hr",))

    def code_block(self, lines, lang=""):
        self.begin_block()
        if self.hidden():
            return
        lines = [ln.expandtabs(4) for ln in (lines or [""])]
        width = min(max(len(ln) for ln in lines + [lang]), 110) + 1
        tag = self.margin_tag("cb", self.indent() + 12, self.indent() + 12, 12)
        if lang:
            self.out(lang.lower().ljust(width) + "\n", (tag, "codelang"))
        diff = lang.lower() in ("diff", "patch")
        for k, ln in enumerate(lines):
            extra = ()
            if diff:
                if ln.startswith("+") and not ln.startswith("+++"):
                    extra = ("diff_add",)
                elif ln.startswith("-") and not ln.startswith("---"):
                    extra = ("diff_del",)
                elif ln.startswith("@@"):
                    extra = ("diff_hunk",)
            if k == len(lines) - 1:
                extra += ("codeend",)
            self.out(ln.ljust(width) + "\n", (tag, "codeblock") + extra)

    def table(self, rows, aligns=None, header=True):
        self.begin_block()
        if self.hidden() or not rows:
            return
        ncol = max(len(r) for r in rows)
        cells = [[plain(c) for c in r] + [""] * (ncol - len(r)) for r in rows]
        widths = [max(1, max(len(r[c]) for r in cells)) for c in range(ncol)]
        aligns = list(aligns or []) + ["l"] * ncol
        tags = self.pad_tags() + ("table",)

        def border(left, mid, right):
            return left + mid.join("\u2500" * (wd + 2) for wd in widths) + right

        def row(r):
            parts = []
            for c, wd in enumerate(widths):
                txt = r[c].rjust(wd) if aligns[c] == "r" else r[c].center(wd) if aligns[c] == "c" else r[c].ljust(wd)
                parts.append(" " + txt + " ")
            return "\u2502" + "\u2502".join(parts) + "\u2502"

        self.out(border("\u250c", "\u252c", "\u2510") + "\n", tags)
        for k, r in enumerate(cells):
            self.out(row(r) + "\n", tags + (("tablehead",) if header and k == 0 else ()))
            if header and k == 0:
                self.out(border("\u251c", "\u253c", "\u2524") + "\n", tags)
        self.out(border("\u2514", "\u2534", "\u2518") + "\n", tags + ("tableend",))

    # ------------------------------------------------------ inline parsing
    def inline(self, text, tags=(), style=()):
        pos = 0
        for m in INLINE.finditer(text):
            if m.start() > pos:
                self.text(text[pos:m.start()], tags, style)
            pos = m.end()
            self.inline_token(m, tags, style)
        if pos < len(text):
            self.text(text[pos:], tags, style)

    def inline_token(self, m, tags, style):
        g = m.group
        if g("esc") is not None:
            self.text(g("ech"), tags, style, raw=True)
        elif g("comment") is not None:
            return
        elif g("code") is not None:
            self.out(g("ctext"), self.style_tags(tags, style + ("code",)))
        elif g("img") is not None:
            self.image(g("isrc"), g("ialt"), tags, style)
        elif g("link") is not None:
            self.inline(g("ltext"), tags, style + (self.link_tag(g("lhref")),))
        elif g("reflink") is not None:
            url = self.refs.get((g("rid") or g("rtext")).strip().lower())
            if url is None:
                self.text(m.group(0), tags, style)
            else:
                self.inline(g("rtext"), tags, style + (self.link_tag(url),))
        elif g("htmlimg") is not None:
            a = attrs(g("htmlimg"))
            self.image(a.get("src", ""), a.get("alt", ""), tags, style, parse_width(a.get("width")))
        elif g("htmla") is not None:
            whole = m.group(0)
            href = attrs(whole[:whole.find(">") + 1]).get("href")
            self.inline(g("atext"), tags, style + ((self.link_tag(href),) if href else ()))
        elif g("htmlbr") is not None:
            self.out("\n", self.style_tags(tags, style))
        elif g("htmltag") is not None:
            st = HTML_STYLE.get(g("tname").lower())
            self.inline(g("ttext"), tags, style + ((st,) if st else ()))
        elif g("autolink") is not None:
            self.text(g("aurl"), tags, style + (self.link_tag(g("aurl")),), raw=True)
        elif g("bolditalic") is not None:
            self.inline(g("bitext"), tags, style + ("bold", "italic"))
        elif g("bold") is not None:
            self.inline(g("btext"), tags, style + ("bold",))
        elif g("italic") is not None:
            self.inline(g("itext"), tags, style + ("italic",))
        elif g("strike") is not None:
            self.inline(g("stext"), tags, style + ("strike",))

    def emit_pieces(self, base, pieces):  # pieces come from the HTML parser
        for kind, payload, style in pieces:
            if kind == "t":
                self.text(payload, base, style, raw=True)
            else:
                self.image(payload[0], payload[1], base, style, payload[2])

    # --------------------------------------------------------- block parse
    def render(self, text):
        w = self.w
        for mark in set(self.anchors.values()):
            try:
                w.mark_unset(mark)
            except Exception:
                pass
        self.anchors, self.slugs = {}, {}
        self.det_stack, self.det_counter, self.nlink = [], 0, 0
        self.list_indents = []
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        self.blocks(self.collect_refs(lines))

    @staticmethod
    def closes(line, fence):
        s = line.strip()
        return s.startswith(fence) and set(s) <= {fence[0]}

    def collect_refs(self, lines):
        self.refs, keep, fence = {}, [], None
        for ln in lines:
            if fence:
                if self.closes(ln, fence):
                    fence = None
                keep.append(ln)
                continue
            m = FENCE.match(ln)
            if m:
                fence = m.group(1)
                keep.append(ln)
                continue
            d = REF_DEF.match(ln)
            if d:
                self.refs[d.group(1).strip().lower()] = d.group(2).strip("<>")
                continue
            keep.append(ln)
        return keep

    def table_at(self, lines, j):
        return ("|" in lines[j] and j + 1 < len(lines) and is_sep(lines[j + 1]) and not is_sep(lines[j]))

    def starts_block(self, lines, j):
        ln = lines[j]
        return bool(FENCE.match(ln) or HEADING.match(ln) or RULE.match(ln) or QUOTE.match(ln)
                    or LIST.match(ln) or HTML_BLOCK.match(ln) or self.table_at(lines, j))

    @staticmethod
    def join_para(para):
        out = ""
        for k, ln in enumerate(para):
            hard = ln.endswith("  ") or ln.endswith("\\")
            s = ln.strip()
            if ln.endswith("\\"):
                s = s[:-1]
            out += s
            if k < len(para) - 1:
                out += "\n" if hard else " "
        return out

    def blocks(self, lines):
        n, i = len(lines), 0
        while i < n:
            line = lines[i]
            if not line.strip():
                i += 1
                continue
            is_list = bool(LIST.match(line)) and not RULE.match(line)
            continuation = bool(self.list_indents) and line[:1] in " \t" and not is_list \
                and not self.starts_block(lines, i)
            if not is_list and not continuation:
                self.list_indents = []

            m = FENCE.match(line)
            if m:  # fenced code block
                fence, lang, code, j = m.group(1), m.group(2), [], i + 1
                while j < n and not self.closes(lines[j], fence):
                    code.append(lines[j])
                    j += 1
                self.code_block(code, lang)
                i = j + 1
                continue

            m = HEADING.match(line)
            if m:
                text = (m.group(2) or "").strip()
                self.heading(len(m.group(1)), lambda t, s=text: self.inline(s, t), plain(text))
                i += 1
                continue

            if RULE.match(line):
                self.rule()
                i += 1
                continue

            if QUOTE.match(line):
                while i < n and QUOTE.match(lines[i]):
                    q = QUOTE.match(lines[i])
                    level, content = q.group(1).count(">"), q.group(2).strip()
                    alert = re.fullmatch(r"\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]", content, re.I)
                    if content or alert:
                        self.quote_line(level, lambda t, s=content: self.inline(s, t),
                                        alert.group(1).upper() if alert else None)
                    i += 1
                continue

            if HTML_BLOCK.match(line):
                i = self.html_block(lines, i)
                continue

            if self.table_at(lines, i):
                aligns = []
                for cell in split_row(lines[i + 1]):
                    c = cell.strip()
                    aligns.append("c" if c.startswith(":") and c.endswith(":") else "r" if c.endswith(":") else "l")
                rows, j = [split_row(line)], i + 2
                while j < n and lines[j].strip() and "|" in lines[j]:
                    rows.append(split_row(lines[j]))
                    j += 1
                self.table(rows, aligns, header=True)
                i = j
                continue

            if is_list:
                lm = LIST.match(line)
                indent = len(lm.group(1).expandtabs(4))
                while self.list_indents and indent < self.list_indents[-1]:
                    self.list_indents.pop()
                if not self.list_indents or indent > self.list_indents[-1]:
                    self.list_indents.append(indent)
                level = len(self.list_indents) - 1
                marker, text = lm.group(2), lm.group(3).rstrip()
                num = marker if marker[0].isdigit() else None
                task = re.match(r"\[([ xX])\]\s+(.*)$", text, re.S)
                checked = None
                if task:
                    checked, text = task.group(1) in "xX", task.group(2)
                self.list_item(level, num, lambda t, s=text: self.inline(s, t), checked)
                i += 1
                continue

            # paragraph (or an indented continuation of a list item)
            para, j = [line], i + 1
            while j < n and lines[j].strip() and not self.starts_block(lines, j):
                para.append(lines[j])
                j += 1
            text = self.join_para(para)
            if continuation:
                lm_px = self.indent() + 16 + 24 * (len(self.list_indents) - 1) + 22
                tag = self.margin_tag("cont", lm_px, lm_px)
                self.begin_block()
                self.inline(text, (tag,))
                self.out("\n", (tag,))
            else:
                self.paragraph(lambda t, s=text: self.inline(s, t))
            i = j

    def html_block(self, lines, i):
        n, j = len(lines), i
        first = lines[i].strip().lower()
        if first.startswith("<!--"):  # comment: skip to its end
            while j < n and "-->" not in lines[j]:
                j += 1
            return j + 1
        if first.startswith("<pre"):  # keep blank lines inside <pre>
            while j < n and "</pre" not in lines[j].lower():
                j += 1
            block = lines[i:j + 1]
            j += 1
        else:
            while j < n and lines[j].strip():
                j += 1
            block = lines[i:j]
        parser = _Html(self)
        parser.feed("\n".join(block))
        parser.close()
        parser.flush()
        return j


class _Html(HTMLParser):
    """Feeds one HTML block into the renderer. Tolerant of unclosed <li> / odd nesting."""
    BLOCKS = {"p", "div", "center", "section", "figure", "picture"}

    def __init__(self, r):
        super().__init__(convert_charrefs=True)
        self.r = r
        self.pieces, self.block, self.lists, self.styles = [], None, [], []
        self.quote = 0
        self.pre = self.summary = self.rows = self.row = self.cell = None
        self.anchor = None
        self.has_head = False

    def cur_style(self):
        return tuple(s for _, s in self.styles if s)

    def list_level(self):
        scope = len(self.r.det_stack)
        inside = sum(1 for lst in self.lists if lst[2] == scope)
        return max(inside - 1, 0)  # details depth is added by Renderer.list_item via indent()

    def handle_data(self, data):
        if self.pre is not None:
            self.pre.append(data)
        elif self.summary is not None:
            self.summary.append(data)
        elif self.cell is not None:
            self.cell.append(data)
        else:
            text = re.sub(r"\s+", " ", data)
            if text.strip() or self.pieces:
                self.pieces.append(("t", text, self.cur_style()))

    def handle_starttag(self, tag, attrs_):
        a = {k: (v or "") for k, v in attrs_}
        r = self.r
        ident = a.get("id") or (a.get("name") if tag == "a" else "")
        if ident:
            self.anchor = ident
        if re.fullmatch(r"h[1-6]", tag):
            self.flush()
            self.block = {"kind": "h", "level": int(tag[1])}
        elif tag in self.BLOCKS:
            self.flush()
        elif tag in ("ul", "ol"):
            self.flush()
            self.lists.append([tag, 0, len(r.det_stack)])
        elif tag == "li":
            self.flush()
            if not self.lists:
                self.lists.append(["ul", 0, len(r.det_stack)])
            lst = self.lists[-1]
            lst[1] += 1
            self.block = {"kind": "li", "level": self.list_level(),
                          "marker": f"{lst[1]}." if lst[0] == "ol" else None}
        elif tag == "br":
            self.pieces.append(("t", "\n", self.cur_style()))
        elif tag == "hr":
            self.flush()
            r.rule()
        elif tag == "img":
            self.pieces.append(("i", (a.get("src", ""), a.get("alt", ""), parse_width(a.get("width"))),
                                self.cur_style()))
        elif tag == "a":
            self.styles.append(("a", r.link_tag(a["href"]) if a.get("href") else ""))
        elif tag in HTML_STYLE:
            self.styles.append((tag, HTML_STYLE[tag]))
        elif tag == "pre":
            self.flush()
            self.pre = []
        elif tag == "blockquote":
            self.flush()
            self.quote += 1
        elif tag == "details":
            self.flush()
            r.det_start()
        elif tag == "summary":
            self.flush()
            self.summary = []
        elif tag == "table":
            self.flush()
            self.rows, self.has_head = [], False
        elif tag == "tr" and self.rows is not None:
            self.row = []
        elif tag in ("td", "th") and self.rows is not None:
            self.cell = []
            if self.row is None:
                self.row = []
            if tag == "th" and not self.rows:
                self.has_head = True

    def handle_endtag(self, tag):
        r = self.r
        if re.fullmatch(r"h[1-6]", tag) or tag in self.BLOCKS or tag == "li":
            self.flush()
        elif tag in ("ul", "ol"):
            self.flush()
            if self.lists:
                self.lists.pop()
        elif tag == "a" or tag in HTML_STYLE:
            for k in range(len(self.styles) - 1, -1, -1):
                if self.styles[k][0] == tag:
                    del self.styles[k]
                    break
        elif tag == "pre" and self.pre is not None:
            r.code_block("".join(self.pre).strip("\n").split("\n"), "")
            self.pre = None
        elif tag == "blockquote":
            self.flush()
            self.quote = max(0, self.quote - 1)
        elif tag == "details":
            self.flush()
            r.det_end()
        elif tag == "summary" and self.summary is not None:
            text = " ".join("".join(self.summary).split())
            scope = len(r.det_stack) - 1
            inside = sum(1 for lst in self.lists if lst[2] == scope)
            r.det_summary(text or "Details", scope + max(inside - 1, 0))
            self.summary = None
            self.block = None
        elif tag in ("td", "th") and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None
        elif tag == "table" and self.rows is not None:
            if self.row:
                self.rows.append(self.row)
            r.table(self.rows, header=self.has_head)
            self.rows = self.row = None

    def flush(self):
        pieces, block = self.pieces, self.block
        self.pieces, self.block = [], None
        while pieces and pieces[0][0] == "t" and not pieces[0][1].strip():
            pieces.pop(0)
        while pieces and pieces[-1][0] == "t" and not pieces[-1][1].strip():
            pieces.pop()
        if not pieces:
            return
        if pieces[0][0] == "t":
            pieces[0] = ("t", pieces[0][1].lstrip(), pieces[0][2])
        if pieces[-1][0] == "t":
            pieces[-1] = ("t", pieces[-1][1].rstrip(), pieces[-1][2])
        r = self.r
        kind = block["kind"] if block else "p"
        body = lambda tags: r.emit_pieces(tags, pieces)  # noqa: E731
        text = " ".join(p[1] for p in pieces if p[0] == "t")
        if kind == "h":
            r.heading(block["level"], body, text, self.anchor)
            self.anchor = None
            return
        if self.anchor:
            r.add_anchor(self.anchor)
            self.anchor = None
        if kind == "li":
            r.list_item(block["level"], block["marker"], body)
        elif self.quote:
            r.quote_line(self.quote, body)
        else:
            r.paragraph(body)
