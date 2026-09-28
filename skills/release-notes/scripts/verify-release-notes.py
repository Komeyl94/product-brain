#!/usr/bin/env python3
"""Check both release notes against their contracts before anything is sent.

The two notes fail in opposite directions, so they are checked for opposite
things:

  client note   - fails by LEAKING (jargon, SHAs, spec numbers, unwrapped
                  identifiers), by SHOWING A PICTURE that will not travel with
                  the file, by being too THIN - a card that names a feature and
                  never says what it does for anyone - and by STRAYING FROM THE
                  DESIGN SYSTEM (brand-system's check-brand.py runs on it).
  internal note - fails by OMITTING (an empty Risks section, a test-coverage
                  claim with no command behind it, a citation-free assertion).

The client note is written in ONE language: releases.client_note.locale, with
direction releases.client_note.dir. There is no second article to pair against,
so the check runs the other way: exactly one article in the client locale, and
no article in any other language smuggled back in. The internal note is written
in releases.internal_note.locale only.

"Too thin" is a real failure, not a style note. A list of one-line bullets lets a
client read the whole page and still not know whether any of it affected them.
Every card in the "new" block must carry a .benefit paragraph, and any card
claiming a screen change must show that screen.

Usage:
    python verify-release-notes.py "<releases.out>/<version> - <date>/client.html"
    python verify-release-notes.py "<releases.out>/<version> - <date>/internal.md"
    python verify-release-notes.py "<releases.out>/<version> - <date>"/*
    python verify-release-notes.py --locale fa --dir rtl <file>   override the hub's config
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys

sys.dont_write_bytecode = True  # a skill does not litter its own folder with __pycache__

from html.parser import HTMLParser
from pathlib import Path

from _hub import BRAND_SCRIPTS, SKILL, Config, find_hub, utf8_stdio

# --- client note: vocabulary that must never reach a client -------------------
# Hard failures. Each maps to what to say instead. English is checked whatever
# the client locale: technical English leaks into any language's copy - a stray
# "endpoint" in a caption is the usual way.
BLOCK_EN = {
    "endpoint": "name the screen, not the endpoint",
    "api": "say what the feature does",
    "backend": "say what the feature does",
    "frontend": "say what the feature does",
    "deploy": "say 'update'",
    "deployment": "say 'update'",
    "migration": "invisible to the client - cut it",
    "migrating": "invisible to the client - cut it",
    "refactor": "invisible to the client - cut it",
    "commit": "cut it",
    "branch": "cut it",
    "merge": "cut it",
    "repo": "cut it",
    "repository": "cut it",
    "cache": "say 'loads faster'",
    "caching": "say 'loads faster'",
    "query": "say what the user sees",
    "sql": "cut it",
    "database": "cut it",
    "schema": "cut it",
    "null": "cut it",
    "exception": "say 'error message'",
    "regression": "say 'this had stopped working'",
    "paginate": "say 'shown in pages'",
    "pagination": "say 'shown in pages'",
    "timestamp": "say 'date and time'",
    "webhook": "cut it",
    "cron": "say 'automatically'",
    "middleware": "cut it",
    "token": "cut it",
    "jwt": "cut it",
    "rbac": "say 'permissions'",
    "latency": "say 'speed'",
    "docker": "cut it",
    "kubernetes": "cut it",
    "laravel": "cut it",
    "angular": "cut it",
    "react": "cut it",
    "django": "cut it",
    "nginx": "cut it",
    "pipeline": "cut it",
    "hotfix": "say 'fix'",
    "changelog": "this page is the changelog",
    "filament": "say 'the admin area'",
}
# Per-locale jargon: the same leaks, transliterated. Add a locale here when a hub
# writes its client note in it. Persian is the worked example.
BLOCK_LOCAL = {
    "fa": {
        "کامیت": "cut it",
        "مرج": "cut it",
        "دیپلوی": "بگویید «به‌روزرسانی»",
        "بک‌اند": "cut it",
        "بکاند": "cut it",
        "فرانت‌اند": "cut it",
        "ای‌پی‌آی": "cut it",
        "دیتابیس": "cut it",
        "پایگاه داده": "cut it",
        "مایگریشن": "cut it",
        "ریفکتور": "cut it",
        "اندپوینت": "cut it",
        "کوئری": "cut it",
        "توکن": "cut it",
        "سرور": "cut it",
        "باگ": "بگویید «مشکل»",
    },
}
WARN_EN = {"bug", "issue", "patch", "release", "version", "sync", "config", "log", "logs"}

# Which script a locale is written in, so "the note contains text in its own
# language" and "the internal note contains none of the client's" can be checked
# without a language detector. Latin-script locales are not distinguishable this
# way, and those two checks are skipped for them.
SCRIPTS = {
    "arabic": re.compile(r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\ufb50-\ufdff\ufe70-\ufeff]"),
    "hebrew": re.compile(r"[\u0590-\u05ff]"),
    "cyrillic": re.compile(r"[\u0400-\u04ff]"),
    "greek": re.compile(r"[\u0370-\u03ff]"),
    "cjk": re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]"),
    "devanagari": re.compile(r"[\u0900-\u097f]"),
    "thai": re.compile(r"[\u0e00-\u0e7f]"),
}
LOCALE_SCRIPT = {
    "fa": "arabic", "ar": "arabic", "ur": "arabic", "ps": "arabic", "ku": "arabic",
    "he": "hebrew", "yi": "hebrew",
    "ru": "cyrillic", "uk": "cyrillic", "bg": "cyrillic", "sr": "cyrillic", "kk": "cyrillic",
    "el": "greek",
    "zh": "cjk", "ja": "cjk", "ko": "cjk",
    "hi": "devanagari", "mr": "devanagari", "ne": "devanagari",
    "th": "thai",
}


def script_of(locale: str):
    return LOCALE_SCRIPT.get(locale.split("-")[0].lower())


# A commit hash is 7-40 hex characters with at least one digit AND at least one
# letter a-f: an all-digit run is a phone number or a date (20260922), and an
# all-letter one is a word ("defaced"). An all-digit run still counts when the
# copy itself calls it a commit or a SHA. Text inside <bdi> (a version, a phone
# number) is never checked.
SHA = re.compile(r"\b(?=[0-9a-f]{7,40}\b)(?=[0-9a-f]*[a-f])(?=[0-9a-f]*[0-9])[0-9a-f]+\b")
SHA_CONTEXT = re.compile(r"\b(?:commit|sha)\b\W{0,3}([0-9a-f]{7,40})\b", re.IGNORECASE)
VERSIONISH = re.compile(r"\bv-?\d+\.\d+\.\d+\b")
SPEC = re.compile(r"\b\d{3}-[a-z][a-z0-9-]{3,}\b")
# Case-sensitive on purpose: template slots are uppercase REPLACE, and prose
# legitimately uses the word "replace" ("replace this section once the suite runs").
PLACEHOLDER = re.compile(r"REPLACE")
DARK_SELECTOR = ':root:not([data-theme="light"])'
DARK_ATTR = ':root[data-theme="dark"]'

REQUIRED_INTERNAL_SECTIONS = [
    ("technical changes", "what changed, with evidence a reader can jump to"),
    ("risks", "what could bite, or 'None found' plus the check that says so"),
    ("test coverage", "the command you ran and its output"),
    ("build", "how this became production"),
    ("citation", "the written sources behind the claims"),
]

# Per-role word ceilings. The cap that matters is the FLOOR on .benefit: a single
# low ceiling pushes the note towards the one-line stubs it should not have.
# Numbers are warn-level - a long paragraph is a judgement call, an absent one is
# not.
WORD_CEILING = {
    "benefit": 85,
    "scenario": 70,
    "lede": 55,
    "figcaption": 36,
    "where": 34,
    "glance": 34,      # the whole chip row; each chip is capped separately below
    "who": 8,
    "minor": 44,
    "stamp-pill": 14,
}
TAG_CEILING = {"h1": 16, "b": 16}
DEFAULT_CEILING = 44
# A chip is a label, not a sentence. Measured per <li>, because the ceiling on
# .glance covers the whole row and would let one essay-length chip through.
GLANCE_ITEM_CEILING = 9

# A card that names one integration and stops has told the client nothing.
BENEFIT_FLOOR_WORDS = 12

VOID = {"img", "br", "hr", "input", "meta", "link", "source", "col", "area", "base", "wbr"}


class Frame:
    __slots__ = ("tag", "classes", "attrs", "text", "item", "block", "lang")

    def __init__(self, tag, classes, attrs, item, block, lang=""):
        self.lang = lang
        self.tag = tag
        self.classes = classes
        self.attrs = attrs
        self.text = []
        self.item = item          # the enclosing [data-id] record, if any
        self.block = block        # the enclosing data-block value, if any


class Articles(HTMLParser):
    """Pull per-language content out of the client note.

    Frame-based rather than flat: the checks need to know which element a run of
    text belongs to (a 60-word .benefit is right, a 60-word title is not), which
    card an image sits in, and whether that card explained itself.
    """

    def __init__(self):
        super().__init__()
        self.lang = None
        self.stack: list[Frame] = []
        self.text: dict[str, list[str]] = {}
        self.items: dict[str, list[dict]] = {}
        self.images: list[dict] = []
        self.figures: dict[str, list[str]] = {}
        self.outside_bdi: list[tuple[str, str]] = []
        # Authored copy only: text inside a [data-chrome] element is the page's
        # own fixed wording (labels, the version stamp, the footer) - written
        # by the scaffold, not the author - and is exempt from the jargon lists.
        self.copy: list[str] = []
        self.copy_plain: list[str] = []   # authored copy outside any <bdi>
        self.long: list[tuple[str, str, int, int]] = []
        self.bdi_depth = 0

    # -- helpers ---------------------------------------------------------------
    @property
    def item(self):
        return self.stack[-1].item if self.stack else None

    @property
    def block(self):
        return self.stack[-1].block if self.stack else None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set((attrs.get("class") or "").split())

        if tag == "article" and attrs.get("data-lang") and not self.lang:
            self.lang = attrs["data-lang"]
            self.text.setdefault(self.lang, [])
            self.items.setdefault(self.lang, [])
            self.figures.setdefault(self.lang, [])
            self.stack.append(Frame(tag, classes, attrs, None, None, self.lang))
            return
        if not self.lang:
            return

        item, block = self.item, self.block
        if attrs.get("data-block"):
            block = attrs["data-block"]
        if attrs.get("data-id"):
            item = {
                "id": attrs["data-id"], "lang": self.lang, "block": block,
                "classes": classes, "benefit_words": 0,
                "has_shot": "has-shot" in classes, "figures": [], "text": [],
            }
            self.items[self.lang].append(item)

        if tag == "bdi":
            self.bdi_depth += 1
        if tag == "figure" and attrs.get("data-shot"):
            self.figures[self.lang].append(attrs["data-shot"])
        if tag == "img":
            self.images.append({
                "lang": self.lang,
                "figure": attrs.get("data-figure"),
                "locale": attrs.get("data-locale"),
                "src": attrs.get("src", ""),
                "alt": attrs.get("alt"),
                "item": item["id"] if item else None,
            })
            if item is not None and attrs.get("data-figure"):
                item["figures"].append(attrs["data-figure"])

        if tag not in VOID:
            self.stack.append(Frame(tag, classes, attrs, item, block, self.lang))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if not self.lang or not self.stack:
            return
        if tag == "bdi" and self.bdi_depth:
            self.bdi_depth -= 1
        for depth in range(len(self.stack) - 1, -1, -1):
            if self.stack[depth].tag == tag:
                frame = self.stack[depth]
                ancestors = self.stack[:depth]
                del self.stack[depth:]
                self._close(frame, ancestors)
                if frame.tag == "article" and frame.attrs.get("data-lang"):
                    self.lang = None
                return

    def _close(self, frame: Frame, ancestors: list[Frame] = ()):
        body = " ".join(frame.text).strip()
        if not body:
            return
        words = len(body.split())
        role = next((c for c in frame.classes if c in WORD_CEILING), None)
        ceiling = WORD_CEILING.get(role) if role else TAG_CEILING.get(frame.tag, None)
        if frame.tag == "li" and any("glance" in a.classes for a in ancestors):
            role, ceiling = "glance chip", GLANCE_ITEM_CEILING
        if ceiling is None and frame.tag in ("p", "span", "li", "figcaption"):
            # An unclassified run of copy still should not be an essay.
            ceiling = DEFAULT_CEILING if frame.tag != "li" else WORD_CEILING["where"]
        if ceiling is not None and words > ceiling:
            self.long.append((frame.lang, role or frame.tag, words, ceiling))
        if role == "benefit" and frame.item is not None:
            frame.item["benefit_words"] += words

    def handle_data(self, data):
        if not self.lang:
            return
        chunk = data.strip()
        if not chunk:
            return
        self.text[self.lang].append(chunk)
        chrome = any("data-chrome" in frame.attrs for frame in self.stack)
        if not chrome:
            self.copy.append(chunk)
            if not self.bdi_depth:
                self.copy_plain.append(chunk)
        if not self.bdi_depth:
            self.outside_bdi.append((self.lang, chunk))
        if self.item is not None:
            self.item["text"].append(chunk)
        # Text belongs to every open element, so ceilings measure whole passages
        # rather than the fragments an inline <span> chops them into.
        for frame in self.stack:
            frame.text.append(chunk)


def css_rules(css: str) -> list:
    """(media conditions, selector, body) for every style rule, through nested @media.

    Brace-matched rather than regex-matched: the checks below need to know which
    rules sit inside `@media print` and which inside the dark-scheme query, and a
    flat regex cannot tell a rule's context from its neighbour's.
    """
    rules = []

    def walk(text: str, media: list) -> None:
        i, n = 0, len(text)
        while i < n:
            j = text.find("{", i)
            if j == -1:
                return
            depth, k = 1, j + 1
            while k < n and depth:
                if text[k] == "{":
                    depth += 1
                elif text[k] == "}":
                    depth -= 1
                k += 1
            head = re.split(r"[;}]", text[i:j])[-1].strip()
            body = text[j + 1:k - 1]
            if head.startswith("@media"):
                walk(body, media + [head[6:].strip()])
            elif not head.startswith("@"):
                rules.append((media, re.sub(r"\s+", " ", head), body))
            i = k

    walk(css, [])
    return rules


def selectors(head: str) -> list:
    return [re.sub(r"\s+", "", s).replace("'", '"') for s in head.split(",")]


def custom_props(body: str) -> set:
    return set(re.findall(r"(--[\w-]+)\s*:", body))


def run_check_brand(path: Path, hub: Path):
    """Run brand-system's check-brand.py. Returns (ok, lines worth showing)."""
    script = BRAND_SCRIPTS / "check-brand.py"
    if not script.is_file():
        return False, [f"brand toolkit missing ({script}) - install the brand-system skill "
                       "next to this one; the design-system check cannot run without it"]
    proc = subprocess.run([sys.executable, str(script), str(path.resolve())],
                          cwd=hub, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode == 0:
        return True, []
    # Pass its report through whole, minus the file header and zero tallies:
    # the per-category lines ARE the diagnosis.
    lines = [ln.rstrip() for ln in (proc.stdout + "\n" + proc.stderr).splitlines() if ln.strip()]
    lines = [ln for ln in lines
             if not ln.startswith("FAIL ") and not re.match(r"^\s*[\w-]+\s+0$", ln)]
    return False, lines[:30] or [f"check-brand.py exited {proc.returncode}"]


def check_client(path: Path, locale: str, direction: str, hub: Path, tag_regex: str | None) -> tuple:
    markup = path.read_text(encoding="utf-8")
    fails, warns = [], []

    parser = Articles()
    parser.feed(markup)
    langs = set(parser.text)
    rtl = direction == "rtl"

    # -- one language ---------------------------------------------------------
    # Exactly one article, in the client locale. A second-language half
    # reappearing is a regression, not a bonus: it doubles the page and nobody
    # maintains the second half.
    opening = re.findall(rf'<article\b[^>]*\bdata-lang="{re.escape(locale)}"[^>]*>', markup)
    if not opening:
        fails.append(f'no <article data-lang="{locale}"> - the client note is written in {locale} '
                     "(releases.client_note.locale)")
    elif len(opening) > 1:
        fails.append(f'{len(opening)} <article data-lang="{locale}"> elements - the client note is '
                     "exactly one article")
    for stray in sorted(langs - {locale}):
        fails.append(
            f'an <article data-lang="{stray}"> is in the file - the client note is {locale} only; '
            "delete it rather than letting it drift"
        )

    shots = 0
    if locale in langs:
        items = parser.items[locale]
        ids = [i["id"] for i in items]
        if not ids:
            fails.append("no [data-id] items - nothing to check")
        for dupe in sorted({i for i in ids if ids.count(i) > 1}):
            fails.append(f"duplicate data-id '{dupe}'")

        # -- the anti-stub rule ------------------------------------------------
        # A card in the "new" block that never says what changes for the person
        # is the exact failure this layout replaced. Improvements ("fixed") are
        # allowed to stay one line - they are one line of news.
        for item in items:
            if item["block"] != "new":
                continue
            words = item.get("benefit_words", 0)
            if not words:
                fails.append(
                    f"'{item['id']}' has no <p class=\"benefit\"> - a new feature has to "
                    "say what a person can now do, in two or three sentences"
                )
            elif words < BENEFIT_FLOOR_WORDS:
                fails.append(
                    f"'{item['id']}' explains itself in {words} words - under "
                    f"{BENEFIT_FLOOR_WORDS} is a restated title, not a benefit"
                )

        # -- screenshots -------------------------------------------------------
        figures = parser.figures[locale]
        shots = len(figures)
        for dupe in sorted({f for f in figures if figures.count(f) > 1}):
            fails.append(f"figure '{dupe}' is shown twice")
        if not shots:
            warns.append(
                "no screenshots in this note - if the release changed a screen, capture it "
                "with scripts/capture-figures.py; if it changed none, this warning is the answer"
            )

        for img in parser.images:
            where = "image" + (f" in '{img['item']}'" if img["item"] else "")
            src = img["src"] or ""
            if not src:
                fails.append(f"{where} has no src - run capture-figures.py to fill it")
            elif not src.startswith("data:image/"):
                # The note is published as one self-contained Artifact behind a CSP
                # that blocks every external host, and is also read as a PDF. A
                # relative or remote src renders on this machine and shows the
                # client a broken image.
                shown = src[:60] + ("..." if len(src) > 60 else "")
                fails.append(
                    f"{where} src is not embedded ({shown}) - inline it as a data: URI; "
                    "an external or relative src is blocked in the published page"
                )
            if not (img["alt"] or "").strip():
                fails.append(f"{where} has no alt text - the picture carries meaning, so it needs words too")
            if img["figure"] and not img["locale"]:
                fails.append(f"{where} '{img['figure']}' has no data-locale - capture-figures.py cannot match it")
            if img["locale"] and img["locale"] != locale:
                # A capture in another language shows the client a screen they
                # will never see.
                fails.append(
                    f"{where} '{img['figure']}' is the '{img['locale']}' capture - the note is "
                    f"{locale}, so the picture has to be of the {locale} screen"
                )

        found = opening[0] if opening else ""
        if f'dir="{direction}"' not in found:
            fails.append(f'the article needs dir="{direction}" (releases.client_note.dir)')
        if f'lang="{locale}"' not in re.sub(r"data-lang=\"[^\"]*\"", "", found):
            fails.append(f'the article needs lang="{locale}" - screen readers and hyphenation read it')
        script = script_of(locale)
        if script and not SCRIPTS[script].search(" ".join(parser.text[locale])):
            fails.append(f"the article contains no {locale} text")

    body = " ".join(t for texts in parser.text.values() for t in texts)
    # The leak checks read authored copy only, never the scaffold's [data-chrome]
    # wording: "Version" and "release" in the stamp are not the author's jargon.
    copy = " ".join(parser.copy)

    # -- the machine-readable headline --------------------------------------
    # One sentence on what a person can now do, read by other skills (the
    # roadmap) - distinct from the h1, which is a title, not a sentence.
    # Comments stripped first: a comment that quotes the tag is not the tag.
    live = re.sub(r"(?s)<!--.*?-->", "", markup)
    meta = re.search(r"<meta\b[^>]*\bname=[\"']release-headline[\"'][^>]*>", live, re.I)
    headline = None
    if not meta:
        fails.append('no <meta name="release-headline" content="..."> - one sentence on what a '
                     "person can now do; other skills read it")
    else:
        found = re.search(r"\bcontent=([\"'])(.*?)\1", meta.group(0), re.S)
        headline = (found.group(2) if found else "").strip()
        h1 = re.search(r"(?s)<h1[^>]*>(.*?)</h1>", live)
        h1_text = re.sub(r"<[^>]+>|\s+", " ", h1.group(1)).strip() if h1 else ""
        if not headline:
            fails.append("the release-headline meta is empty")
        elif headline == h1_text:
            fails.append("the release-headline repeats the h1 - the h1 is a title, the headline "
                         "a sentence on what a person can now do")
        elif len(headline.split()) > 30:
            warns.append(f"a {len(headline.split())}-word release-headline (over 30) - one sentence")
        if headline:
            copy = f"{copy} {headline}"
    lowered = copy.lower()

    # Match ordinary inflections too - "refactored" and "endpoints" leak exactly
    # as much as the bare stem does. The suffix set is closed so that 'api' does
    # not swallow 'apiece'.
    for term, fix in BLOCK_EN.items():
        if re.search(rf"(?<![a-z]){re.escape(term)}(?:s|es|ed|d|ing)?(?![a-z])", lowered):
            fails.append(f"client note says '{term}' - {fix}")
    for term, fix in BLOCK_LOCAL.get(locale.split("-")[0].lower(), {}).items():
        # \b matches correctly around non-Latin letters in Python's re (Unicode
        # word chars), unlike a bare substring check - which flags real names
        # that merely start with a jargon stem (a person's name beginning with
        # the transliteration of "merge" once tripped exactly that).
        if re.search(rf"\b{re.escape(term)}\b", copy):
            fails.append(f"client note says '{term}' - {fix}")
    for term in sorted(WARN_EN):
        if re.search(rf"(?<![a-z]){term}(?:s|es|ed|d|ing)?(?![a-z])", lowered):
            warns.append(f"client note says '{term}' - check it reads as plain language")

    plain = " ".join(parser.copy_plain) + (f" {headline}" if headline else "")
    leaked = SHA.search(plain) or SHA_CONTEXT.search(plain)
    if leaked:
        fails.append(f"commit SHA in client copy: {leaked.group(leaked.lastindex or 0)}")
    # A spec/branch-shaped id (NNN-slug) inside <bdi dir="ltr"> is this note's own
    # version stamp - the role a release tag plays - not a stray internal
    # citation. Only an UNWRAPPED occurrence is the real leak: a spec id cited in
    # passing prose, which a client has no way to look up.
    outside = " ".join(chunk for _, chunk in parser.outside_bdi)
    if SPEC.search(outside):
        fails.append(f"spec identifier in client copy: {SPEC.search(outside).group(0)}")

    if rtl:
        # -- RTL: identifiers are LTR islands ---------------------------------
        patterns = [VERSIONISH]
        if tag_regex:
            patterns.append(re.compile(tag_regex.lstrip("^").rstrip("$")))
        for lang, chunk in parser.outside_bdi:
            found = next((p.search(chunk) for p in patterns if p.search(chunk)), None)
            if found:
                fails.append(
                    f"version '{found.group(0)}' in the {lang} note is not wrapped in <bdi dir=\"ltr\"> "
                    "- bidi will scramble it next to right-to-left text"
                )
                break

        # A neutral separator sitting against an LTR run inside RTL text resolves
        # unpredictably: "<name> <bdi>v1.2.3</bdi> · <date>" renders with the
        # date's first digit torn off and parked next to the version. An em dash,
        # or an explicit RLM, resolves correctly.
        article = re.search(rf'(?s)<article[^>]*data-lang="{re.escape(locale)}".*?</article>', markup)
        if article and re.search(r"</bdi>\s*[·•]|[·•]\s*<bdi", article.group(0)):
            fails.append(
                "'·' used as a separator next to <bdi> in a right-to-left note - "
                "bidi tears the following date apart; use an em dash instead"
            )

    if PLACEHOLDER.search(markup):
        fails.append("template placeholder 'REPLACE' still in the file")

    # A file opened from disk has no HTTP header to name its encoding, and the
    # embedded fonts put hundreds of KB of ASCII base64 ahead of the first
    # non-ASCII byte - so Chrome's sniffer gives up, decodes as windows-1252,
    # and the PDF comes out as mojibake while every other check here passes.
    if not re.search(r'<meta\s+charset=["\']?utf-8', markup[:1024], re.I):
        fails.append('no <meta charset="utf-8"> at the top of the file - opened from disk, '
                     "Chrome guesses windows-1252 and the PDF prints mojibake")

    # -- the PDF must be the screen -------------------------------------------
    css = "\n".join(re.findall(r"(?is)<style[^>]*>(.*?)</style>", markup))
    # Strip comments first: the stylesheet explains these very rules in comments
    # that quote the selectors, and an uncommented check matches the prose
    # instead of the rule - passing a file whose rule is broken.
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    flat = re.sub(r"\s+", " ", css)
    rules = css_rules(css)
    print_rules = [r for r in rules if any("print" in m for m in r[0])]

    if not re.search(r"@media\s+print", flat):
        fails.append("no @media print block - the PDF will not look like the page")
    else:
        page = re.search(r"@page\s*\{([^}]*)\}", flat)
        size = re.search(r"size\s*:\s*([^;}]+)", page.group(1)) if page else None
        if not size:
            fails.append(
                "@page declares no size - the PDF defaults to A4 portrait, whose ~688px of "
                "printable width collapses every two-column card"
            )
        elif not re.search(r"\d+\s*px", size.group(1)):
            fails.append(
                f"@page size is '{size.group(1).strip()}' - a paper size cannot hold the "
                "62rem layout. Set a pixel page at least as wide as the design "
                "(e.g. `size: 1120px 1584px`), and let the viewer scale it to paper"
            )
        if not re.search(r"print-color-adjust\s*:\s*exact", flat):
            fails.append(
                "the print block never sets print-color-adjust: exact - Chrome drops the "
                "wash, the card surfaces and every tinted panel, and prints the note on "
                "bare white"
            )
        # A width media query that is not scoped to `screen` also matches the
        # printed page, so the narrow-viewport fallback fires inside a 1120px
        # PDF and undoes the whole layout. Invisible on screen; only the file
        # you send shows it.
        for query in re.findall(r"@media\s+([^{]+)\{", flat):
            if "max-width" in query and "screen" not in query and "print" not in query:
                fails.append(
                    f"@media ({query.strip()}) is not scoped to `screen` - it also applies to "
                    "the printed page, so the PDF reflows to the narrow layout"
                )
                break

        # Paper is always light. Every custom property the dark rule sets must be
        # reset inside @media print AT THE SAME SPECIFICITY. A bare `:root`
        # (0,1,0) - or `:root[data-theme]`, which does not even match a root
        # with no data-theme attribute - loses to
        # `:root:not([data-theme="light"])` (0,2,0), so the reset silently does
        # nothing and a reader printing from a dark-mode browser gets pale ink
        # on white stock with no error anywhere.
        # The same holds for an explicit `:root[data-theme="dark"]` rule, which
        # `:root[data-theme="dark"]` or `:root[data-theme]` in print does reset.
        missing = set()
        for dark, resets in ((DARK_SELECTOR, {DARK_SELECTOR}),
                             (DARK_ATTR, {DARK_ATTR, ':root[data-theme]'})):
            dark_props, reset_props = set(), set()
            for media, head, decl in rules:
                sels = set(selectors(head))
                in_print = any("print" in m for m in media)
                if in_print and sels & resets:
                    reset_props |= custom_props(decl)
                elif not in_print and dark in sels:
                    dark_props |= custom_props(decl)
            missing |= {f"{prop} under {dark}" for prop in dark_props - reset_props}
        missing = sorted(missing)
        if missing:
            fails.append(
                f"the print block does not reset {len(missing)} dark token(s) at matching "
                f"specificity ({', '.join(missing[:3])}{', ...' if len(missing) > 3 else ''}) - "
                f"a print rule needs the matching selector (for {DARK_SELECTOR}, that exact "
                "selector), or printing from a dark-mode browser yields pale ink on white paper. "
                "If the tokens are the BRAND block's, the fix belongs in brand-system's print rule"
            )

        # Cards must not be sliced across a page boundary. On screen this is
        # free; in the PDF a card that breaks loses either its picture or the
        # sentence explaining it.
        if not any(re.search(r"break-inside\s*:\s*avoid", decl) for _, _, decl in print_rules):
            fails.append(
                "the print block never says break-inside: avoid - cards will be sliced "
                "across page boundaries"
            )

    # -- the design system ----------------------------------------------------
    ok, lines = run_check_brand(path, hub)
    if not ok:
        fails.append("check-brand.py failed - the note strays from the design system:")
        fails.extend(f"  {line}" for line in lines)

    for lang, role, words, ceiling in parser.long:
        warns.append(f"a {words}-word {role} (over {ceiling}) - tighten it or split it")

    counts = {lang: len(parser.items.get(lang, [])) for lang in sorted(parser.items)}
    figures = len(parser.images)
    return fails, warns, f"{counts} items, {figures} image(s), {len(body.split())} words"


# -- internal note: author-written content, not the scaffold's -----------------
# Every omission check below reads only lines the AUTHOR wrote. The template's
# own lines carry backticks, paths and links, so a scaffold with every slot set
# to "none" once passed "All contracts satisfied" - each check was satisfied by
# the template's prose. So each line is classified against the template first.
SCAFFOLD_TOKENS = {"REPLACE-TAG", "REPLACE-VERSION", "REPLACE-DATE", "REPLACE-RANGES",
                   "REPLACE-PRODUCT", "REPLACE-PRODUCTION-BRANCH", "REPLACE-TAG-REGEX",
                   "REPLACE-SPECS-LINK", "REPLACE-ROADMAP-LINK", "REPLACE-TEST-ROWS"}
SLOT = re.compile(r"REPLACE(?:-[A-Za-z0-9_]+)*")
HOLLOW = {"", "none", "n/a", "na", "-", "--", "—", "–", "tbd", "todo", "tba", "nothing", "no",
          "none found", "not run", "?", "...", "…", "unknown", "same", "ok", "yes"}


def hollow(value: str) -> bool:
    bare = re.sub(r"[`*_\"'.,;:()\[\]]", "", value or "").strip().lower()
    return bare in HOLLOW or bare.startswith("replace")


def template_patterns(tests: dict) -> tuple:
    """(literal template lines, [(regex, slot tokens)]) from the internal template."""
    raw = (SKILL / "assets" / "internal-note-template.md").read_text(encoding="utf-8")
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    lines += [f"| {repo} | `{cmd}` | REPLACE | REPLACE |" for repo, cmd in tests.items()]
    literal, patterns = set(), []
    for line in lines:
        tokens = SLOT.findall(line)
        if not tokens:
            literal.add(line)
            continue
        if line in SCAFFOLD_TOKENS:
            continue  # a whole-line scaffold expansion; its rows are added above
        parts = SLOT.split(line)
        regex = "^" + "(.*?)".join(re.escape(part) for part in parts) + "$"
        patterns.append((re.compile(regex), tokens))
    return literal, patterns


def classify(line: str, literal: set, patterns: list) -> str:
    """'template' (the scaffold's own line), 'hollow' (a slot filled with nothing), or 'authored'."""
    text = line.strip()
    if text in literal:
        return "template"
    verdict = None
    for regex, tokens in patterns:
        match = regex.match(text)
        if not match:
            continue
        values = [v for tok, v in zip(tokens, match.groups()) if tok not in SCAFFOLD_TOKENS]
        kind = "template" if not values else "hollow" if all(hollow(v) for v in values) else "authored"
        # The least-authored reading wins: a hollow row must not pass because a
        # looser pattern would also accept it.
        rank = {"template": 0, "hollow": 1, "authored": 2}
        if verdict is None or rank[kind] < rank[verdict]:
            verdict = kind
    return verdict or "authored"


def check_internal(path: Path, internal_locale: str, client_locale: str, tests: dict) -> tuple:
    text = path.read_text(encoding="utf-8")
    fails, warns = [], []

    headings = [h.lower() for h in re.findall(r"^#{1,3}\s+(.+)$", text, re.MULTILINE)]
    blob = "\n".join(headings)
    for needle, why in REQUIRED_INTERNAL_SECTIONS:
        if needle not in blob:
            fails.append(f"missing section '{needle}' - {why}")

    if PLACEHOLDER.search(text):
        count = len(PLACEHOLDER.findall(text))
        fails.append(f"{count} unreplaced 'REPLACE' placeholder(s)")

    # The internal note is in its own locale only. Detectable when the client
    # locale's script differs from the internal one's.
    client_script, internal_script = script_of(client_locale), script_of(internal_locale)
    if client_script and client_script != internal_script and SCRIPTS[client_script].search(text):
        fails.append(f"{client_locale} text in the internal note - it is written in "
                     f"{internal_locale} only (releases.internal_note.locale)")

    literal, patterns = template_patterns(tests)
    sections = {}
    current = None
    for line in text.splitlines():
        heading = re.match(r"^#{1,3}\s+(.+)$", line)
        if heading:
            current = heading.group(1).lower()
            sections[current] = []
        elif current and line.strip():
            sections[current].append(line)

    def lines_of(needle, kind="authored"):
        for name, lines in sections.items():
            if needle in name:
                return [ln for ln in lines if classify(ln, literal, patterns) == kind]
        return []

    def all_of(needle):
        for name, lines in sections.items():
            if needle in name:
                return lines
        return []

    def is_row(line):
        return line.strip().startswith("|") and not re.match(r"^\|[\s:|-]+\|$", line.strip())

    # -- technical changes: at least one row the author wrote ----------------
    if all_of("technical changes") and not [ln for ln in lines_of("technical changes") if is_row(ln)]:
        fails.append("Technical changes has no author-written row - one row per change, with a "
                     "SHA or path as evidence")

    # -- risks ----------------------------------------------------------------
    risks = lines_of("risks")
    if all_of("risks"):
        if not risks:
            fails.append("Risks has no author-written entry - every slot is the template's or "
                         "'none'. State the risks, or 'None found' and the check behind it")
        body = "\n".join(risks)
        if re.search(r"none\b", body, re.IGNORECASE) and not re.search(
                r"`[^`]+`|checked|verified|ran |grep|diff", body, re.IGNORECASE):
            fails.append("Risks says 'none' without naming the check that produced it")

    # -- test coverage: a real Result, not a slot ---------------------------
    if all_of("test coverage"):
        results = []
        for line in all_of("test coverage"):
            if not is_row(line):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 3 and cells[0].lower() != "suite":
                results.append((cells[2], cells[3] if len(cells) > 3 else ""))

        def answered(result, notes):
            if not hollow(result):
                return True
            # "not run" / "n/a" / "skipped" is an answer when a reason sits with it,
            # in the same cell or the Notes cell. "none" never is.
            bare = re.sub(r"[`*_]", "", result).strip().lower()
            if re.match(r"^(not run|n/?a|skipped)\W+\w+", bare):
                return True
            return bare in ("not run", "n/a", "na", "skipped") and not hollow(notes)

        real = [r for r, notes in results if answered(r, notes)]
        if not real:
            fails.append("Test coverage has no row with a real Result - paste what each suite "
                         "printed, or write `not run - <why>`; a slot or 'none' is not coverage")
        untested = [ln for ln in all_of("test coverage") if re.search(
            r"no accompanying test|shipped untested|without a test", ln, re.IGNORECASE)]
        if not untested or all(classify(ln, literal, patterns) != "authored" for ln in untested):
            fails.append("Test coverage never says which changes shipped with no test - name "
                         "them, or say 'none' and how you know")

    # -- build and release ----------------------------------------------------
    if all_of("build") and not lines_of("build"):
        fails.append("Build and release has no author-written line - say how this became "
                     "production and who confirmed the running version")

    # -- citations: a link the author put there -----------------------------
    if all_of("citation") and not [ln for ln in lines_of("citation") if re.search(r"\]\([^)]+\)", ln)]:
        fails.append("Document citations carries no author-written link - the template's "
                     "example rows do not count")

    authored_text = "\n".join(ln for name in sections for ln in lines_of(name))

    # A screenshot in the client note is a claim about the product, made in a
    # picture. If figures were captured, the internal note is where the state
    # behind each one is recorded - which stub data, which toggles, why. If none
    # were, the note says why (no screen changed / capture not configured / the
    # app could not be served).
    mentions = re.search(r"screenshot|figure|capture", authored_text, re.IGNORECASE)
    if (path.parent / "figures.json").is_file() and not mentions:
        warns.append(
            "figures.json exists but the internal note never mentions the screenshots - "
            "record what state each capture is in; a picture is a claim like any other"
        )
    elif not (path.parent / "figures.json").is_file() and not mentions:
        warns.append("no figures.json and the internal note never says why there are no "
                     "screenshots - no screen changed, releases.capture is not configured, or the "
                     "app could not be served: say which")

    evidence = len(re.findall(r"`[0-9a-f]{7,40}`|\]\([^)]+\)|`[^`]*[/\\][^`]*`", authored_text))
    if evidence < 3:
        warns.append(f"only {evidence} pieces of author-written evidence (SHAs, paths, links)")

    return fails, warns, f"{len(sections)} sections, {evidence} evidence references"


def main() -> int:
    utf8_stdio()
    parser = argparse.ArgumentParser(description="Verify release notes against their contracts.")
    parser.add_argument("paths", nargs="+", help="client .html and/or internal .md notes")
    parser.add_argument("--hub", help="hub root (default: walk up from the current directory)")
    parser.add_argument("--locale", help="client locale (default: releases.client_note.locale)")
    parser.add_argument("--dir", dest="direction", choices=("ltr", "rtl"),
                        help="client direction (default: releases.client_note.dir)")
    args = parser.parse_args()

    hub = find_hub(args.hub, also_from=Path(args.paths[0]).parent)
    cfg = Config(hub)
    locale = args.locale or cfg.client_locale
    direction = args.direction or cfg.client_dir
    internal_locale = cfg.get("releases.internal_note.locale")
    tag_regex = cfg.get("releases.tag_regex", None)

    total_fails = 0
    for raw in args.paths:
        path = Path(raw)
        if not path.is_file():
            print(f"FAIL {raw}: no such file")
            total_fails += 1
            continue

        if path.suffix == ".html":
            fails, warns, summary = check_client(path, locale, direction, hub, tag_regex)
            kind = f"client, {locale}/{direction}"
        elif path.suffix == ".md":
            fails, warns, summary = check_internal(path, internal_locale, locale,
                                                   cfg.get("releases.tests", {}))
            kind = f"internal, {internal_locale}"
        else:
            print(f"skip {path} (expected .html or .md)")
            continue

        status = "FAIL" if fails else "pass"
        print(f"\n{status} {path} [{kind}] - {summary}")
        for message in fails:
            print(f"  FAIL  {message}" if not message.startswith("  ") else f"        {message.strip()}")
        for message in warns:
            print(f"  warn  {message}")
        total_fails += sum(1 for m in fails if not m.startswith("  "))

    print()
    if total_fails:
        print(f"{total_fails} failure(s). Do not send or publish until these are zero.")
        return 1
    print("All contracts satisfied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
