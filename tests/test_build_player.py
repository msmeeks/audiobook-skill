import json

import pytest

from build_player import build, build_html


def test_embeds_player_data_without_breaking_out_of_the_script_tag():
    template = '<script id="data" type="application/json">__PLAYER_DATA__</script>'
    html = build_html(template, {"album": "A </script><b>", "chapters": []})
    assert html.count("</script>") == 1
    payload = html.removeprefix('<script id="data" type="application/json">').removesuffix("</script>")
    assert json.loads(payload)["album"] == "A </script><b>"


def narrated_book(tmp_path, finished):
    """book.json with three chapters, of which the numbers in `finished` have audio + timing."""
    work, out = tmp_path / "work", tmp_path / "out"
    (work / "text").mkdir(parents=True)
    (out / "audio").mkdir(parents=True)
    chapters = [{"stem": f"0{n} - Part {n}", "title": f"Part {n}: Go"} for n in (1, 2, 3)]
    (work / "book.json").write_text(json.dumps({"album": "Album", "chapters": chapters}))
    for n in finished:
        stem = chapters[n - 1]["stem"]
        para = [[{"text": f"Part {n}.", "start": 0.05, "end": 1.0}]]
        (work / "text" / f"{stem}.json").write_text(json.dumps({"key": "k", "paragraphs": para}))
        (out / "audio" / f"{stem}.m4a").write_bytes(b"m4a")
    return work, out


def player_data(out):
    html = (out / "Audio Player.html").read_text()
    payload = html.split('<script id="data" type="application/json">', 1)[1].split("</script>", 1)[0]
    return json.loads(payload.replace("<\\/", "</"))


def test_player_lists_every_chapter_with_its_audio_path_and_timing(tmp_path):
    work, out = narrated_book(tmp_path, finished=[1, 2, 3])
    build(work, out)
    data = player_data(out)
    assert data["album"] == "Album"
    assert [c["title"] for c in data["chapters"]] == ["Part 1: Go", "Part 2: Go", "Part 3: Go"]
    assert data["chapters"][1]["audio"] == "audio/02 - Part 2.m4a"
    assert data["chapters"][1]["paragraphs"][0][0]["text"] == "Part 2."


def test_unfinished_chapters_fail_the_build_unless_partial(tmp_path):
    work, out = narrated_book(tmp_path, finished=[1, 3])
    with pytest.raises(SystemExit, match="02 - Part 2"):
        build(work, out)
    build(work, out, partial=True)
    assert [c["title"] for c in player_data(out)["chapters"]] == ["Part 1: Go", "Part 3: Go"]


def test_build_reports_audio_files_no_chapter_uses(tmp_path, capsys):
    work, out = narrated_book(tmp_path, finished=[1, 2, 3])
    (out / "audio" / "01 - Renamed Away.m4a").write_bytes(b"m4a")
    build(work, out)
    assert "01 - Renamed Away.m4a" in capsys.readouterr().out
