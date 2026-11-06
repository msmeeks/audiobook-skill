import json

import numpy as np

from narrate import SR, narrate_book, narrate_chapter, split_sentences, voiced_span


def test_splits_paragraph_into_sentences():
    text = "We do the same thing. Why? Because we forget!"
    assert split_sentences(text) == ["We do the same thing.", "Why?", "Because we forget!"]


def test_keeps_scripture_references_and_abbreviations_intact():
    text = ("“Those whom I love I rebuke” (Rev. 3:19). Orphans vs. Children is next. "
            "Fear, anger, etc. all show up. See 1 Cor. 13 for more.")
    assert split_sentences(text) == [
        "“Those whom I love I rebuke” (Rev. 3:19).",
        "Orphans vs. Children is next.",
        "Fear, anger, etc. all show up.",
        "See 1 Cor. 13 for more.",
    ]


def test_closing_quote_stays_with_its_sentence():
    assert split_sentences("He said, “Repent.” Then he left.") == ["He said, “Repent.”", "Then he left."]


def test_list_markers_and_initials_stay_with_following_text():
    assert split_sentences("II. Article Read it together. 3. Feeling and goal: Talk.") == [
        "II. Article Read it together.", "3. Feeling and goal: Talk."]
    assert split_sentences("Translated by J. Theodore Mueller. Done.") == [
        "Translated by J. Theodore Mueller.", "Done."]


def test_voiced_span_ignores_leading_and_trailing_silence():
    speech = 0.3 * np.sin(np.linspace(0, 400 * np.pi, SR))  # 1 s tone
    clip = np.concatenate([np.zeros(SR // 4), speech, np.zeros(SR // 2)]).astype(np.float32)
    start, end = voiced_span(clip)
    assert abs(start - 0.25) < 0.03
    assert abs(end - 1.25) < 0.03


def test_voiced_span_of_silent_clip_is_whole_clip():
    assert voiced_span(np.zeros(SR, dtype=np.float32)) == (0.0, 1.0)


def fake_synth(text: str) -> np.ndarray:
    """Stand-in for Kokoro: 0.1 s silence, 10 ms of tone per character, 0.2 s silence."""
    tone = 0.3 * np.sin(np.linspace(0, 40 * np.pi * len(text), SR * len(text) // 100))
    return np.concatenate([np.zeros(SR // 10), tone, np.zeros(SR // 5)]).astype(np.float32)


def test_narrated_chapter_has_ordered_sentence_timings_within_audio():
    paragraphs = ["Lesson 1. First Steps.", "We forget. Why? Because we drift.", "Pray together."]
    audio, timing = narrate_chapter(paragraphs, fake_synth)

    assert [[s["text"] for s in para] for para in timing] == [
        ["Lesson 1. First Steps."], ["We forget.", "Why?", "Because we drift."], ["Pray together."]]
    flat = [s for para in timing for s in para]
    for prev, cur in zip(flat, flat[1:], strict=False):
        assert prev["end"] < cur["start"]
    for s in flat:
        spoken = len(s["text"]) / 100
        assert abs((s["end"] - s["start"]) - spoken) < 0.02  # timing tracks voiced audio only
    assert flat[-1]["end"] <= len(audio) / SR


def make_book(work, chapters):
    (work / "text").mkdir(parents=True)
    entries = []
    for stem, text in chapters.items():
        (work / "text" / f"{stem}.txt").write_text(text)
        entries.append({"stem": stem, "title": stem.split(" - ", 1)[1]})
    (work / "book.json").write_text(json.dumps({"album": "Album", "chapters": entries}))


class FakeEncoder:
    def __init__(self):
        self.calls = []

    def __call__(self, audio, target, tags):
        self.calls.append((target.name, tags))
        target.write_bytes(b"m4a")


def test_book_narration_writes_tagged_audio_and_timing_then_skips_unchanged(tmp_path):
    work, out = tmp_path / "work", tmp_path / "out"
    make_book(work, {"01 - One": "One.\n\nHello there.", "02 - Two": "Two.\n\nBye now."})
    encode = FakeEncoder()

    assert narrate_book(work, out, fake_synth, encode) == ["01 - One", "02 - Two"]
    assert encode.calls[1] == ("02 - Two.m4a", {"title": "Two", "album": "Album", "track": "2/2",
                                                "genre": "Audiobook"})
    assert (out / "audio" / "01 - One.m4a").exists()
    timing = json.loads((work / "text" / "01 - One.json").read_text())
    assert [s["text"] for para in timing["paragraphs"] for s in para] == ["One.", "Hello there."]

    assert narrate_book(work, out, fake_synth, encode) == []
    (work / "text" / "02 - Two.txt").write_text("Two.\n\nEdited after a chapter-break fix.")
    assert narrate_book(work, out, fake_synth, encode) == ["02 - Two"]


def test_book_narration_can_be_limited_to_chosen_chapters(tmp_path):
    work, out = tmp_path / "work", tmp_path / "out"
    make_book(work, {"01 - One": "One.", "02 - Two": "Two.", "03 - Three": "Three."})
    assert narrate_book(work, out, fake_synth, FakeEncoder(), only={2}) == ["02 - Two"]
