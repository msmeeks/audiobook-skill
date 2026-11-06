"""Survey a PDF or text file so chapter breaks and junk lines can be chosen for the spec.

    inspect_source.py SOURCE [--from N] [--to M] [--lines 3] [--dump N]

PDF: outline (TOC), repeated lines (running headers/footers), text-layer artifacts, and the
first lines of each page. Text: size and heading candidates with line numbers.
--dump N prints page N's text blocks in full.
"""
import argparse
import re
from collections import Counter
from pathlib import Path

from extract import FIXES, WORDS_PER_MINUTE


def repeated_lines(pages: list[list[str]], min_pages: int = 3) -> list[tuple[str, int]]:
    """Lines (digits normalised to #) on at least min_pages pages; most common first, ties in
    order of first appearance."""
    counts = Counter()
    for lines in pages:
        normalised = (re.sub(r"\d+", "#", line.strip()) for line in lines if line.strip())
        counts.update(list(dict.fromkeys(normalised)))  # once per page, in page order
    return [(line, n) for line, n in counts.most_common() if n >= min_pages]


def heading_candidates(text: str) -> list[tuple[int, str]]:
    """(line number, line) for standalone short lines without sentence-ending punctuation."""
    lines = text.splitlines()
    found = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        alone = (i == 0 or not lines[i - 1].strip()) and (i + 1 == len(lines) or not lines[i + 1].strip())
        if alone and 0 < len(stripped) <= 60 and not stripped.endswith((".", ",", ";", "?", "!")):
            found.append((i + 1, stripped))
    return found


def artifact_counts(text: str) -> dict[str, list[str]]:
    """Samples of what each optional extract fix would change."""
    return {name: [m.group(0) for m in pattern.finditer(text)][:5] for name, (pattern, _) in FIXES.items()}


def inspect_pdf(path: Path, first: int, last: int | None, show: int, dump: int | None) -> None:
    import pymupdf

    doc = pymupdf.open(path)
    if dump:
        for block in doc[dump - 1].get_text("blocks", sort=True):
            kind = "image" if block[6] else "text"
            print(f"--- {kind} block y={block[1]:.0f}\n{block[4].rstrip()}")
        return
    page_lines = [page.get_text().splitlines() for page in doc]
    words = sum(len(" ".join(lines).split()) for lines in page_lines)
    print(f"{path.name}: {len(doc)} pages, {words} words (~{words / WORDS_PER_MINUTE:.0f} min audio)")
    if doc.metadata.get("title"):
        print(f"metadata title: {doc.metadata['title']}")
    toc = doc.get_toc()
    print("\nOUTLINE (level, pdf page, title):" if toc else "\nOUTLINE: none")
    for level, title, page in toc:
        print(f"  {'  ' * (level - 1)}p{page} {title}")
    print("\nREPEATED LINES (# = any number; candidates for drop_lines):")
    for line, n in repeated_lines(page_lines)[:25]:
        print(f"  {n:4d} pages  {line!r}")
    print("\nTEXT-LAYER ARTIFACTS (enable in spec \"fixes\" if these look wrong):")
    for name, samples in artifact_counts("\n".join(" ".join(lines) for lines in page_lines)).items():
        print(f"  {name}: {samples or 'none'}")
    print(f"\nPAGES (pdf page [words]: first {show} lines):")
    for number in range(first, (last or len(doc)) + 1):
        lines = [line.strip() for line in page_lines[number - 1] if line.strip()]
        images = sum(1 for b in doc[number - 1].get_text("blocks") if b[6])
        head = " | ".join(line[:60] for line in lines[:show]) or "(no text)"
        tag = f" +{images} img" if images else ""
        print(f"  p{number} [{len(' '.join(lines).split())}w{tag}] {head}")


def inspect_text(path: Path) -> None:
    text = path.read_text()
    words = len(text.split())
    print(f"{path.name}: {len(text.splitlines())} lines, {words} words "
          f"(~{words / WORDS_PER_MINUTE:.0f} min audio)")
    print("\nHEADING CANDIDATES (line: text):")
    for number, line in heading_candidates(text)[:300]:
        print(f"  {number:6d}: {line}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", type=Path)
    parser.add_argument("--from", dest="first", type=int, default=1)
    parser.add_argument("--to", dest="last", type=int)
    parser.add_argument("--lines", type=int, default=3)
    parser.add_argument("--dump", type=int, help="print one PDF page's blocks in full")
    args = parser.parse_args()
    if args.source.suffix.lower() == ".pdf":
        inspect_pdf(args.source, args.first, args.last, args.lines, args.dump)
    else:
        inspect_text(args.source)


if __name__ == "__main__":
    main()
