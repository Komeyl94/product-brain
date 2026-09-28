#!/usr/bin/env python3
"""Drop both note skeletons into a release folder.

One folder per release, named "<version> - <release date>", under releases.out:

    <releases.out>/<version> - <date>/
        facts.json     written by gather-release-facts.py (derived, never edited)
        client.html    client locale only, publishable, BRAND block already filled
        client.pdf     rendered from client.html
        internal.md    internal locale only, team only

The client skeleton's BRAND block is filled by the brand-system toolkit
(`brand.py inline`), so the published page is self-contained: the design
system's faces and tokens travel inside it, and the PDF renders identically with
no network. This script never writes a colour or a face itself.

Config (brain.config.json):
    hub.name                         the product name (wordmark, footer)
    releases.out                     where release folders live
    releases.client_note.locale      lang / data-lang of the client note
    releases.client_note.dir         ltr | rtl
    releases.client_note.calendar    gregorian (default) | jalali
    releases.client_note.product_name   the product's name in the client locale (optional)
    releases.version_regex           optional; the version label shown instead of the raw tag
    releases.production_branch, releases.tag_regex, releases.tests   (internal note)
    releases.specs_dir | roadmap.specs_dir, roadmap.out   citation links (internal note)
    design.logo, design.source       the logo, read with `git show <ref>:<path>` (optional)

Usage:
    python scaffold-note.py --tag <tag>
    python scaffold-note.py --tag <tag> --force-client
    python scaffold-note.py --folder "<path to a release folder>"     e.g. a scratch copy
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import re
import subprocess
import sys

sys.dont_write_bytecode = True  # a skill does not litter its own folder with __pycache__

from pathlib import Path

import os

from _hub import (BRAND_SCRIPTS, SKILL, Config, find_hub, read_text_keep, safe_ref, shown,
                  utf8_stdio, version_label, write_text_keep)

# ── calendars ────────────────────────────────────────────────────────────────
JALALI_MONTHS = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
]
GREGORIAN_MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June",
           "July", "August", "September", "October", "November", "December"],
    "fa": ["ژانویه", "فوریه", "مارس", "آوریل", "مه", "ژوئن",
           "ژوئیه", "اوت", "سپتامبر", "اکتبر", "نوامبر", "دسامبر"],
}
# Locales that write numbers with their own digits.
NATIVE_DIGITS = {
    "fa": str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"),
    "ar": str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"),
}

# ── fixed page chrome, per locale ────────────────────────────────────────────
# The few words the template itself carries. A locale not listed here gets
# REPLACE slots instead, so the author translates them and the verifier refuses
# the file until they have. {product} is the product's name.
CHROME = {
    "en": {
        "VERSION": "Version",
        "EYEBROW": "{product} update",
        "NEW": "What's new",
        "FIXED": "Improvements",
        "EXAMPLE": "For example",
        "SUPPORT": "Questions, or need a hand? Contact {product} support.",
    },
    "fa": {
        "VERSION": "نسخهٔ",
        "EYEBROW": "به‌روزرسانی {product}",
        "NEW": "تازه‌ها",
        "FIXED": "بهبودها",
        "EXAMPLE": "مثلاً",
        "SUPPORT": "برای پرسش یا راهنمایی با پشتیبانی {product} تماس بگیرید.",
    },
}
RTL_CHARS = ("\u0590", "\u08ff")


def to_jalali(gy: int, gm: int, gd: int) -> tuple:
    """Gregorian -> Jalali. Anchor check: 2026-03-21 is 1405-01-01."""
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2, gm2, gd2 = gy - 1600, gm - 1, gd - 1
    days = 365 * gy2 + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400 + g_d_m[gm2] + gd2
    if gm > 2 and ((gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0):
        days += 1
    days -= 79
    cycles, days = days // 12053, days % 12053
    jy = 979 + 33 * cycles + 4 * (days // 1461)
    days %= 1461
    if days >= 366:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    for i in range(11):
        length = 31 if i < 6 else 30
        if days < length:
            return jy, i + 1, days + 1
        days -= length
    return jy, 12, days + 1


def client_date(iso_date: str, calendar: str, locale: str) -> str:
    """The release date as the client reads it: their calendar, their digits."""
    year, month, day = (int(p) for p in iso_date.split("-"))
    base = locale.split("-")[0].lower()
    digits = NATIVE_DIGITS.get(base)
    if calendar == "jalali":
        jy, jm, jd = to_jalali(year, month, day)
        label = f"{jd} {JALALI_MONTHS[jm - 1]} {jy}"
    elif calendar == "gregorian":
        months = GREGORIAN_MONTHS.get(base)
        label = f"{day} {months[month - 1]} {year}" if months else iso_date
    else:
        raise SystemExit(
            f"releases.client_note.calendar is {calendar!r} - supported: \"gregorian\" (default), \"jalali\""
        )
    return label.translate(digits) if digits else label


def english_date(iso_date: str) -> str:
    year, month, day = (int(p) for p in iso_date.split("-"))
    return f"{day} {GREGORIAN_MONTHS['en'][month - 1]} {year}"


# ── the logo ─────────────────────────────────────────────────────────────────
MIME = {".png": "image/png", ".svg": "image/svg+xml", ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}


def logo_markup(cfg: Config, product_html: str, alt: str) -> str:
    """The product's own logo as a data: URI, or the product name as a wordmark.

    Read from the design source repo AT design.source.ref with `git show`, never
    from the working tree, so a local checkout of some feature branch cannot
    change what a client sees. Downscaled when Pillow is available: the masthead
    shows it ~54px tall, and every byte travels inside the published page.
    """
    path = cfg.get("design.logo", None)
    wordmark = f'<span class="wordmark">{product_html}</span>'
    if not path:
        return wordmark
    repo_id = cfg.get("design.source.repo")
    ref = safe_ref(cfg.get("design.source.ref"), "design.source.ref")
    repo = cfg.repo_path(repo_id)
    proc = subprocess.run(["git", "-C", str(repo), "show", f"{ref}:{path}"], capture_output=True)
    if proc.returncode != 0 or not proc.stdout:
        print(f"  WARN: could not read design.logo {repo_id}:{ref}:{path} - using a wordmark")
        return wordmark
    blob, suffix = proc.stdout, Path(path).suffix.lower()
    mime = MIME.get(suffix)
    if not mime:
        print(f"  WARN: design.logo has an unsupported type ({suffix}) - using a wordmark")
        return wordmark
    if suffix in (".png", ".jpg", ".jpeg", ".webp"):
        try:
            from PIL import Image
            with Image.open(io.BytesIO(blob)) as img:
                if img.height > 216:
                    img = img.resize((round(img.width * 216 / img.height), 216), Image.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="PNG", optimize=True)
                blob, mime = buf.getvalue(), "image/png"
        except ImportError:
            pass
    uri = f"data:{mime};base64," + base64.b64encode(blob).decode("ascii")
    return f'<img class="logo" src="{uri}" alt="{alt}">'


# ── helpers ──────────────────────────────────────────────────────────────────
def find_folder(cfg: Config, tag: str) -> Path:
    """The release folder for a tag: `<version label> - <date>` (or `<tag> - <date>`).

    More than one match is an error, never a silent pick: a release gathered
    twice under two dates leaves two folders, and the alphabetically last is not
    necessarily the one being written.
    """
    releases = cfg.releases_dir()
    names = {version_label(cfg, tag), tag}
    matches = sorted({p for n in names for p in releases.glob(f"{n} - *") if p.is_dir()})
    if not matches:
        raise SystemExit(
            f"no release folder for {tag} under {shown(releases, cfg.hub)}. Run "
            f"gather-release-facts.py --to {tag} first - it creates the folder and writes facts.json."
        )
    if len(matches) > 1:
        listed = "\n".join(f"    {shown(m, cfg.hub)}" for m in matches)
        raise SystemExit(f"{len(matches)} release folders match {tag}:\n{listed}\n"
                         "Pass --folder with the one you mean.")
    return matches[0]


def fill_brand(cfg: Config, client: Path) -> bool:
    """Fill the BRAND block by calling the brand toolkit. Never inline CSS here."""
    brand_py = BRAND_SCRIPTS / "brand.py"
    if not brand_py.is_file():
        print(f"  FAIL: the brand toolkit is missing ({brand_py}). Install the brand-system skill "
              "next to this one, then run: brand.py inline <client.html>")
        return False
    proc = subprocess.run([sys.executable, str(brand_py), "inline", str(client.resolve())],
                          cwd=cfg.hub, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout).strip()[-600:]
        print(f"  FAIL: brand.py inline did not fill the BRAND block:\n    {tail}\n"
              "  If brand.css has not been built yet: brand.py build, then brand.py inline <client.html>.")
        return False
    return True


def main() -> int:
    utf8_stdio()
    parser = argparse.ArgumentParser(description="Scaffold a release note pair.")
    where = parser.add_mutually_exclusive_group(required=True)
    where.add_argument("--tag", help="release tag; the folder is found under releases.out")
    where.add_argument("--folder", help="an explicit release folder holding facts.json")
    parser.add_argument("--force-client", action="store_true",
                        help="re-scaffold client.html (e.g. after a template or design-system change)")
    parser.add_argument("--force-internal", action="store_true", help="re-scaffold internal.md")
    parser.add_argument("--overwrite-filled", action="store_true",
                        help="allow --force-* to discard a note that has already been written")
    parser.add_argument("--hub", help="hub root (default: walk up from the current directory)")
    args = parser.parse_args()

    cfg = Config(find_hub(args.hub))
    folder = Path(args.folder) if args.folder else find_folder(cfg, args.tag)
    facts_path = folder / "facts.json"
    if not facts_path.is_file():
        raise SystemExit(f"{facts_path} is missing - run gather-release-facts.py first")
    facts = json.loads(facts_path.read_text(encoding="utf-8"))
    tag = args.tag or facts.get("tag")
    # The label gather-release-facts settled on (a planned --label, or the
    # version label of the tag); the tag itself stays in the internal note.
    label = facts.get("versionLabel") or facts.get("label") or (version_label(cfg, tag) if tag else None)
    date = facts.get("releaseDate", "")
    if not tag or not label:
        raise SystemExit("facts.json names no tag or label - pass --tag")
    # A word prefix ("release-", "build_") is rarely meant to be read; "v" / "v-" is.
    if label == tag and not cfg.get("releases.version_regex", None) and re.match(r"^[A-Za-z]{2,}[-_]", tag):
        print(f"  hint: the version label is the raw tag {tag!r}. If the tag carries a prefix that "
              "is not part of the version, set releases.version_regex (one capture group), e.g. "
              f"\"^{tag.split('-')[0]}-(.+)$\".")

    locale, direction = cfg.client_locale, cfg.client_dir
    calendar = cfg.get("releases.client_note.calendar", "gregorian")
    product = cfg.get("releases.client_note.product_name", None) or cfg.product
    # A Latin product name inside RTL copy is an LTR island: isolate it.
    is_rtl_name = any(RTL_CHARS[0] <= ch <= RTL_CHARS[1] for ch in product)
    product_html = product if direction == "ltr" or is_rtl_name else f'<bdi dir="ltr">{product}</bdi>'

    def may_write(path: Path, forced: bool) -> bool:
        """Never silently discard authored copy.

        A file with no REPLACE slots left has been written by a person. Even an
        explicit --force-* refuses it without --overwrite-filled, because
        re-scaffolding after a template tweak is routine and losing a finished
        note to it is not recoverable - these files are untracked until the
        release is committed.
        """
        if not path.exists():
            return True
        if not forced:
            print(f"skip {path.name} (exists; pass --force-{path.stem.split('.')[0]} to re-scaffold)")
            return False
        filled = "REPLACE" not in path.read_text(encoding="utf-8")
        if filled and not args.overwrite_filled:
            print(f"REFUSING to overwrite {path.name}: it has no REPLACE slots left, so it has "
                  "already been written. Pass --overwrite-filled to discard it.")
            return False
        return True

    written, failed = [], False
    client = folder / "client.html"
    if may_write(client, args.force_client):
        markup, newline = read_text_keep(SKILL / "assets" / "client-note-template.html")
        chrome = CHROME.get(locale) or CHROME.get(locale.split("-")[0].lower())
        for key in ("VERSION", "EYEBROW", "NEW", "FIXED", "EXAMPLE", "SUPPORT"):
            if chrome:
                value = chrome[key].replace("{product}", product_html)
            else:
                value = f"REPLACE-LABEL-{key} ({CHROME['en'][key].format(product=product)} - in {locale})"
            markup = markup.replace(f"REPLACE-LABEL-{key}", value)
        markup = markup.replace("REPLACE-LOGO", logo_markup(cfg, product_html, product))
        markup = markup.replace("<title>REPLACE-PRODUCT", f"<title>{product}")
        markup = markup.replace("REPLACE-PRODUCT", product_html)
        markup = markup.replace("REPLACE-LOCALE", locale).replace("REPLACE-DIR", direction)
        markup = markup.replace("REPLACE-VERSION", label)
        if date and date != "unknown-date":
            markup = markup.replace("REPLACE-DATE-LOCAL", client_date(date, calendar, locale))
        write_text_keep(client, markup, newline)
        failed = not fill_brand(cfg, client)
        written.append(client)

    internal = folder / "internal.md"
    if may_write(internal, args.force_internal):
        text, newline = read_text_keep(SKILL / "assets" / "internal-note-template.md")
        ranges = []
        for repo in facts.get("repos", []):
            rng = repo.get("range") or {}
            if rng.get("to"):
                ranges.append(f"`{repo['id']} {rng.get('from') or '(first)'}..{rng['to']}`")
        tests = cfg.get("releases.tests", {})
        rows = [f"| {repo_id} | `{command}` | REPLACE | REPLACE |" for repo_id, command in tests.items()]
        if not rows:
            rows = ["| REPLACE | `REPLACE - no releases.tests configured` | REPLACE | REPLACE |"]
        text = text.replace("REPLACE-TEST-ROWS", "\n".join(rows))
        text = text.replace("REPLACE-RANGES", ", ".join(ranges) or "REPLACE")
        text = text.replace("REPLACE-PRODUCTION-BRANCH", cfg.get("releases.production_branch"))
        text = text.replace("REPLACE-TAG-REGEX", cfg.get("releases.tag_regex"))
        text = text.replace("REPLACE-PRODUCT", cfg.product)
        # Links in the citations table, relative to this release folder - the
        # hub decides where specs, decision records and the roadmap live.
        def rel_link(target: str | None, fallback: str) -> str:
            if not target:
                return fallback
            try:
                return Path(os.path.relpath(cfg.hub / target, folder.resolve())).as_posix()
            except ValueError:  # a different drive (a scratch folder): no relative path exists
                return (cfg.hub / target).resolve().as_posix()
        specs = cfg.get("releases.specs_dir", None) or cfg.get("roadmap.specs_dir", None)
        text = text.replace("REPLACE-SPECS-LINK",
                            rel_link(specs, "REPLACE-no-specs_dir-configured") + "/NNN-slug/spec.md")
        text = text.replace("REPLACE-ROADMAP-LINK",
                            rel_link(cfg.get("roadmap.out", None), "REPLACE-no-roadmap.out-configured"))
        text = text.replace("REPLACE-TAG", tag)
        text = text.replace("REPLACE-VERSION", label)
        text = text.replace("REPLACE-DATE", english_date(date) if date and date != "unknown-date" else "REPLACE-DATE")
        write_text_keep(internal, text, newline)
        written.append(internal)

    for path in written:
        print(f"wrote {shown(path, cfg.hub)} ({path.stat().st_size:,} bytes)")
    if written:
        print("\nBoth still carry REPLACE slots - fill them, then verify. The client note is "
              f"written in {locale} from the change itself, never translated from the internal note.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
