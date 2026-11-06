"""Split a PDF or text file into per-chapter narration text, driven by a spec JSON.

    extract.py SPEC SOURCE WORK_DIR

Writes WORK_DIR/text/<NN - Title>.txt (paragraphs separated by blank lines; the first is
the spoken title) and WORK_DIR/book.json, which narrate.py and build_player.py read.
"""
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

PAGE_NUMBER = re.compile(r"^(\d{1,4}|[ivxlc]{1,7})$")
WORDS_PER_MINUTE = 165  # Kokoro af_heart at 1.0x, measured on a full-length book
TERMINAL = tuple('.!?:;"”’)…')

# Opt-in repairs for PDF text-layer artifacts; enable the ones inspect_source.py reports.
FIXES = {
    # "H arbor", "L ight": a capital split from its word. Skips real words A, I, O.
    "kerning": (re.compile(r"\b([B-HJ-NP-Z]) ([a-z]{2,})"), r"\1\2"),
    # Decorative letter-spaced labels like "s t u d y g u i d e".
    "letter_spaced": (re.compile(r"\b(?:[a-z’] ){3,}[a-z’]\b"), " "),
}


@dataclass
class Para:
    text: str
    page: int | None = None  # 1-based physical PDF page; None for text sources


class Cleaner:
    """Turns a block of source lines into one speakable paragraph, per the spec's rules."""

    def __init__(self, spec: dict):
        self.drop = [PAGE_NUMBER, *(re.compile(p) for p in spec.get("drop_lines", []))]
        self.replace = [(re.compile(a), b) for a, b in spec.get("replace", [])]
        unknown = set(spec.get("fixes", [])) - FIXES.keys()
        if unknown:
            sys.exit(f"unknown fixes {sorted(unknown)}; choose from {sorted(FIXES)}")
        self.replace = [FIXES[name] for name in spec.get("fixes", [])] + self.replace

    def __call__(self, lines: list[str]) -> str:
        kept = [strip_line_markup(line.strip()) for line in lines]
        text = join_lines([line for line in kept if not any(p.search(line) for p in self.drop)])
        text = strip_inline_markup(text)
        for pattern, repl in self.replace:
            text = pattern.sub(repl, text)
        return re.sub(r"\s+", " ", text).strip()


def strip_line_markup(line: str) -> str:
    line = re.sub(r"^#{1,6}\s+", "", line)  # markdown heading
    return re.sub(r"^(?:[-*+•●▪◦]\s+)", "", line)  # list bullet


def strip_inline_markup(text: str) -> str:
    text = text.replace("\u00ad", "")  # soft hyphen
    text = re.sub(r"[\x80-\x9f\ue000-\uf8ff•●▪◦]", " ", text)  # C1 controls, private-use dingbats, bullets
    text = re.sub(r"_{3,}", " ", text)  # fill-in blanks
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)  # markdown link
    text = re.sub(r"(\*\*|__)(.+?)\1", r"\2", text)  # bold
    return re.sub(r"(?<!\w)([*_])(\S(?:.*?\S)?)\1(?!\w)", r"\2", text)  # italic


def text_paragraphs(raw: str, clean: Cleaner) -> list[Para]:
    """Blank-line-separated paragraphs with hard-wrapped lines rejoined."""
    paras = (clean(block.splitlines()) for block in re.split(r"\n\s*\n", raw))
    return [Para(text) for text in paras if len(text) > 1]


def pdf_paragraphs(path: Path, clean: Cleaner) -> list[Para]:
    import pymupdf

    paras: list[Para] = []
    for number, page in enumerate(pymupdf.open(path), 1):
        for block in page.get_text("blocks", sort=True):
            if block[6] != 0:  # image block
                continue
            text = clean(block[4].splitlines())
            if len(text) <= 1:
                continue
            if paras and not paras[-1].text.endswith(TERMINAL) and text[:1].islower():
                paras[-1].text += " " + text  # paragraph continues across a page or column break
            else:
                paras.append(Para(text, number))
    return paras


def join_lines(lines: list[str]) -> str:
    joined = ""
    for line in (line.strip() for line in lines):
        if not line:
            continue
        if joined.endswith("-") and line[:1].islower():
            joined = joined[:-1] + line  # rejoin a word hyphenated across a line break
        else:
            joined = f"{joined} {line}" if joined else line
    return joined


def spoken_title(title: str) -> str:
    spoken = re.sub(r"\s+[–—-]\s+|:\s+", ". ", title).replace("&", "and")
    return spoken if spoken[-1:] in ".!?" else spoken + "."


def stem_for(number: int, title: str) -> str:
    safe = re.sub(r'[/\\:*?"<>|]', "-", title)
    return f"{number:02d} - {safe}"


def find(paras: list[Para], start: int, stop: int, pattern: str | None = None,
         min_page: int = 0, past_page: int | None = None) -> int | None:
    """First index in [start, stop) matching the pattern on or after min_page, or (with
    past_page) the first paragraph beyond that page."""
    regex = re.compile(pattern) if pattern else None
    for i in range(start, stop):
        page = paras[i].page or 0
        if past_page is not None:
            if page > past_page:
                return i
        elif page >= min_page and (regex is None or regex.search(paras[i].text)):
            return i
    return None


def chapter_bounds(paras: list[Para], chapters: list[dict]) -> list[tuple[int, int]]:
    """(start, end) paragraph indexes per chapter. A chapter runs until the next one starts,
    or until its own "end" pattern (exclusive) if that comes first."""
    starts, cursor = [], 0
    for chapter in chapters:
        if "start" not in chapter and "page" not in chapter:
            sys.exit(f"chapter {chapter['title']!r} needs \"start\" (pattern) or \"page\"")
        index = find(paras, cursor, len(paras), chapter.get("start"), chapter.get("page", 0))
        if index is None:
            where = {k: chapter[k] for k in ("start", "page") if k in chapter}
            sys.exit(f"chapter {chapter['title']!r}: nothing found for {where}")
        starts.append(index)
        cursor = index + 1
    bounds = []
    for chapter, start, limit in zip(chapters, starts, starts[1:] + [len(paras)], strict=True):
        ends = [limit]
        if "end" in chapter:
            ends.append(find(paras, start + 1, limit, chapter["end"]))
        if "end_page" in chapter:
            ends.append(find(paras, start + 1, limit, past_page=chapter["end_page"]))
        bounds.append((start, min(e for e in ends if e is not None)))
    return bounds


def extract(spec: dict, source: Path, work: Path) -> list[dict]:
    clean = Cleaner(spec)
    if source.suffix.lower() == ".pdf":
        paras = pdf_paragraphs(source, clean)
    else:
        paras = text_paragraphs(source.read_text(), clean)
    chapters = spec["chapters"]

    text_dir = work / "text"
    text_dir.mkdir(parents=True, exist_ok=True)
    entries, summary = [], []
    for number, (chapter, (start, end)) in enumerate(zip(chapters, chapter_bounds(paras, chapters),
                                                         strict=True), 1):
        stem = stem_for(number, chapter["title"])
        # "spoken": "" means the chapter's own first paragraph already announces it.
        title = chapter.get("spoken", spoken_title(chapter["title"]))
        body = [p.text for p in paras[start:end]]
        (text_dir / f"{stem}.txt").write_text("\n\n".join([title, *body] if title else body))
        entries.append({"stem": stem, "title": chapter["title"]})
        summary.append((stem, body, paras[start].page))
    stems = {entry["stem"] for entry in entries}
    for stale in [*text_dir.glob("*.txt"), *text_dir.glob("*.json")]:
        if stale.stem not in stems:
            stale.unlink()  # a chapter the new spec renamed or dropped
    (work / "book.json").write_text(json.dumps({"album": spec["album"], "chapters": entries},
                                               ensure_ascii=False, indent=2))
    return summary


def main() -> None:
    spec_path, source, work = (Path(arg) for arg in sys.argv[1:4])
    total = 0
    for stem, body, page in extract(json.loads(spec_path.read_text()), source, work):
        words = sum(len(p.split()) for p in body)
        total += words
        where = f"p{page} " if page else ""
        print(f"{stem}: {where}{words} words ~{words / WORDS_PER_MINUTE:.0f} min")
        print(f"    starts: {body[0][:90]!r}" if body else "    EMPTY")
        if body:
            print(f"    ends:   {body[-1][-90:]!r}")
    print(f"total ~{total / WORDS_PER_MINUTE:.0f} min of audio; text in {work / 'text'}")


if __name__ == "__main__":
    main()
