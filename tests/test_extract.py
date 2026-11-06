import json

from extract import extract

BOOK = """# My Book

Chapter 1: Beginnings

It was a dark
and stormy night.

The end of the first
chapter.

Chapter 2: Middles & Ends

Second chapter text.
"""


def write(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(content)
    return path


def test_text_source_splits_on_start_patterns_and_unwraps_lines(tmp_path):
    source = write(tmp_path, "book.txt", BOOK)
    spec = {"album": "My Book", "chapters": [
        {"title": "Beginnings", "start": "^Chapter 1"},
        {"title": "Middles & Ends", "start": "^Chapter 2"},
    ]}
    work = tmp_path / "work"
    extract(spec, source, work)

    book = json.loads((work / "book.json").read_text())
    assert book == {"album": "My Book", "chapters": [
        {"stem": "01 - Beginnings", "title": "Beginnings"},
        {"stem": "02 - Middles & Ends", "title": "Middles & Ends"},
    ]}
    first = (work / "text" / "01 - Beginnings.txt").read_text().split("\n\n")
    assert first == ["Beginnings.", "Chapter 1: Beginnings", "It was a dark and stormy night.",
                     "The end of the first chapter."]
    second = (work / "text" / "02 - Middles & Ends.txt").read_text().split("\n\n")
    assert second[0] == "Middles and Ends."


def chapter_text(work, stem):
    return (work / "text" / f"{stem}.txt").read_text().split("\n\n")


def test_cleanup_rules_drop_lines_apply_replacements_and_strip_markdown(tmp_path):
    source = write(tmp_path, "book.md", (
        "## Part One\n\n"
        "Running Header 12\n"
        "Some **bold** and _italic_ text with a [link](http://x.y).\n\n"
        "- a bullet item\n\n"
        "Fill in: ________ then [5 min] break.\n\n"
        "Tick \uf06f the box.\n"))
    spec = {"album": "A", "chapters": [{"title": "Part One", "start": "Part One", "spoken": ""}],
            "drop_lines": ["^Running Header \\d+$"],
            "replace": [["\\[(\\d+) min\\]", "(\\1 minutes)"]]}
    extract(spec, source, tmp_path / "w")
    assert chapter_text(tmp_path / "w", "01 - Part One") == [
        "Part One",
        "Some bold and italic text with a link.",
        "a bullet item",
        "Fill in: then (5 minutes) break.",
        "Tick the box.",
    ]


def test_end_pattern_excludes_trailing_matter_and_spoken_override_is_used(tmp_path):
    source = write(tmp_path, "b.txt", "Intro\n\nHello.\n\nNotes\n\nskip me\n\nOne\n\nBody.\n\nIndex\n\nzzz\n")
    spec = {"album": "A", "chapters": [
        {"title": "Intro", "start": "^Intro$", "end": "^Notes$"},
        {"title": "One", "start": "^One$", "end": "^Index$", "spoken": "Chapter one."},
    ]}
    extract(spec, source, tmp_path / "w")
    assert chapter_text(tmp_path / "w", "01 - Intro") == ["Intro.", "Intro", "Hello."]
    assert chapter_text(tmp_path / "w", "02 - One") == ["Chapter one.", "One", "Body."]


def test_unknown_start_pattern_names_the_chapter(tmp_path):
    import pytest
    source = write(tmp_path, "b.txt", "Hello.\n")
    with pytest.raises(SystemExit, match="Missing"):
        extract({"album": "A", "chapters": [{"title": "Missing", "start": "^Nope"}]}, source, tmp_path)


def make_pdf(path, pages):
    """Each page is a list of text blocks, laid out top to bottom far enough apart to stay separate."""
    import pymupdf
    doc = pymupdf.open()
    for blocks in pages:
        page = doc.new_page()
        for i, text in enumerate(blocks):
            page.insert_textbox(pymupdf.Rect(72, 60 + i * 120, 540, 170 + i * 120), text, fontsize=11)
    doc.save(path)
    return path


def test_pdf_chapters_by_page_drop_running_headers_and_page_numbers(tmp_path):
    source = make_pdf(tmp_path / "b.pdf", [
        ["Cover Title"],
        ["Book Header", "Chapter One", "First page text that runs on", "2"],
        ["Book Header", "onto the next page.", "3"],
        ["Book Header", "Chapter Two", "Second chapter.", "4"],
        ["Book Header", "Index stuff", "5"],
    ])
    spec = {"album": "B", "drop_lines": ["^Book Header$"], "chapters": [
        {"title": "One", "page": 2},
        {"title": "Two", "page": 4, "end_page": 4},
    ]}
    extract(spec, source, tmp_path / "w")
    assert chapter_text(tmp_path / "w", "01 - One") == [
        "One.", "Chapter One", "First page text that runs on onto the next page."]
    assert chapter_text(tmp_path / "w", "02 - Two") == ["Two.", "Chapter Two", "Second chapter."]


def test_pdf_start_pattern_can_begin_mid_page(tmp_path):
    source = make_pdf(tmp_path / "b.pdf", [["Intro text.", "Part 2", "Body two."]])
    spec = {"album": "B", "chapters": [
        {"title": "Intro", "page": 1}, {"title": "Two", "page": 1, "start": "^Part 2$", "spoken": ""}]}
    extract(spec, source, tmp_path / "w")
    assert chapter_text(tmp_path / "w", "01 - Intro") == ["Intro.", "Intro text."]
    assert chapter_text(tmp_path / "w", "02 - Two") == ["Part 2", "Body two."]


def test_optional_fixes_repair_pdf_kerning_and_letter_spaced_labels(tmp_path):
    source = write(tmp_path, "b.txt", "Start\n\nThe H arbor of L ight s t u d y g u i d e is here.\n")
    spec = {"album": "A", "fixes": ["kerning", "letter_spaced"],
            "chapters": [{"title": "S", "start": "^Start$", "spoken": ""}]}
    extract(spec, source, tmp_path / "w")
    assert chapter_text(tmp_path / "w", "01 - S")[1] == "The Harbor of Light is here."
    del spec["fixes"]
    extract(spec, source, tmp_path / "w")
    assert chapter_text(tmp_path / "w", "01 - S")[1].startswith("The H arbor")


def test_rerun_with_new_breaks_removes_text_and_timing_of_dropped_chapters(tmp_path):
    source = write(tmp_path, "book.txt", BOOK)
    work = tmp_path / "work"
    spec = {"album": "A", "chapters": [{"title": "Old", "start": "^Chapter 1"}]}
    extract(spec, source, work)
    (work / "text" / "01 - Old.json").write_text("{}")
    spec["chapters"] = [{"title": "New", "start": "^Chapter 1"}]
    extract(spec, source, work)
    assert sorted(p.name for p in (work / "text").iterdir()) == ["01 - New.txt"]
