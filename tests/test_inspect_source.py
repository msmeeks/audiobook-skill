from inspect_source import heading_candidates, repeated_lines


def test_repeated_lines_flag_running_headers_with_page_numbers_normalised():
    pages = [["The Book 1", "Chapter One", "Body"], ["The Book 2", "Body"], ["The Book 3", "x"],
             ["Once", "Body"]]
    assert repeated_lines(pages, min_pages=3) == [("The Book #", 3), ("Body", 3)]


def test_heading_candidates_find_markdown_chapter_and_short_standalone_lines():
    text = ("# Title\n\nChapter 1\n\nA long paragraph of ordinary prose that goes on and on.\n"
            "still the same paragraph.\n\nPART TWO\n\nShort line\nwith a follower\n")
    assert heading_candidates(text) == [(1, "# Title"), (3, "Chapter 1"), (8, "PART TWO")]
