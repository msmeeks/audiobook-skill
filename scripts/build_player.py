"""Write the self-contained "Audio Player.html" for a narrated book.

    build_player.py WORK_DIR OUT_DIR [--partial]

Embeds book.json plus every chapter's timing into player.html. --partial includes only the
chapters narrated so far (for previewing while narration runs).
"""
import argparse
import json
import sys
from pathlib import Path

TEMPLATE = Path(__file__).with_name("player.html")
PLACEHOLDER = "__PLAYER_DATA__"
PLAYER_NAME = "Audio Player.html"


def build_html(template: str, data: dict) -> str:
    # "<\/" is still valid JSON but can't close the surrounding <script> element.
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return template.replace(PLACEHOLDER, payload)


def build(work: Path, out: Path, partial: bool = False) -> Path:
    book = json.loads((work / "book.json").read_text())
    chapters, missing = [], []
    for chapter in book["chapters"]:
        stem = chapter["stem"]
        audio, timing = f"audio/{stem}.m4a", work / "text" / f"{stem}.json"
        if not (out / audio).exists() or not timing.exists():
            missing.append(stem)
            continue
        paragraphs = json.loads(timing.read_text())["paragraphs"]
        chapters.append({"title": chapter["title"], "audio": audio, "paragraphs": paragraphs})
    if missing and not partial:
        sys.exit(f"not narrated yet: {missing} (use --partial to build without them)")
    if not chapters:
        sys.exit("no narrated chapters to build")
    used = {f"{c['stem']}.m4a" for c in book["chapters"]}
    for orphan in sorted((out / "audio").glob("*.m4a")):
        if orphan.name not in used:
            print(f"warning: {orphan} belongs to no chapter (renamed or dropped?); delete it")
    target = out / PLAYER_NAME
    html = build_html(TEMPLATE.read_text(), {"album": book["album"], "chapters": chapters})
    target.write_text(html)
    print(f"wrote {target} ({len(chapters)}/{len(book['chapters'])} chapters, {len(html) // 1024} KB)")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("work", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--partial", action="store_true")
    args = parser.parse_args()
    build(args.work, args.out, args.partial)


if __name__ == "__main__":
    main()
