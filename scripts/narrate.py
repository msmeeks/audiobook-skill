"""Narrate each chapter with Kokoro: tagged .m4a audio plus per-sentence timing .json.

    narrate.py WORK_DIR OUT_DIR [--voice af_heart] [--speed 1.0] [--only 1,2]

Reads WORK_DIR/book.json and text/*.txt from extract.py. Writes OUT_DIR/audio/<stem>.m4a and
WORK_DIR/text/<stem>.json. Re-runs skip chapters whose text and voice settings are unchanged.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from collections.abc import Callable, Container
from pathlib import Path

import numpy as np

MODELS = Path(os.environ.get("AUDIOBOOK_HOME", Path.home() / ".cache" / "audiobook")) / "models"
SR = 24000
PAD = 0.05  # breath kept around each trimmed sentence clip (s)
GAP_SENTENCE, GAP_PARAGRAPH, GAP_TITLE = 0.25, 0.55, 0.9

# A boundary is terminal punctuation (plus closing quotes/brackets), whitespace, then
# something that can open a sentence. Digits and lowercase can't, which keeps
# "Rev. 3:19" and "etc. all" together; a "3. " list marker can.
_SENTENCE_END = re.compile(r"[.!?…][”\"’)\]]*\s+(?=[A-Z“\"‘(\[]|\d+\.\s)")
_ABBREVIATIONS = {"vs.", "Mr.", "Mrs.", "Dr.", "St.", "e.g.", "i.e.", "cf.", "etc."}
# "3." / "IV." list markers and "J." initials belong to the text that follows.
_MARKER_OR_INITIAL = re.compile(r"^(\d+|[IVXivx]+|[A-Z])\.$")


def split_sentences(text: str) -> list[str]:
    sentences, start = [], 0
    for m in _SENTENCE_END.finditer(text):
        last_word = text[start:m.start() + 1].split()[-1]
        if last_word in _ABBREVIATIONS or _MARKER_OR_INITIAL.match(last_word):
            continue
        sentences.append(text[start:m.end()].strip())
        start = m.end()
    tail = text[start:].strip()
    return sentences + [tail] if tail else sentences


def voiced_span(samples: np.ndarray, threshold: float = 0.02) -> tuple[float, float]:
    """Seconds where speech starts and ends, so highlights don't lead or lag the voice."""
    loud = np.flatnonzero(np.abs(samples) > threshold)
    if loud.size == 0:
        return 0.0, len(samples) / SR
    return loud[0] / SR, (loud[-1] + 1) / SR


def silence(seconds: float) -> np.ndarray:
    return np.zeros(int(SR * seconds), dtype=np.float32)


def narrate_chapter(
    paragraphs: list[str], synth: Callable[[str], np.ndarray]
) -> tuple[np.ndarray, list[list[dict]]]:
    """Synthesize sentence by sentence; return audio and [[{text, start, end}]] per paragraph.

    Each clip is trimmed to its voiced span (plus PAD) and joined with fixed gaps, so pacing
    is even and every timing marks when the voice is actually speaking.
    """
    parts: list[np.ndarray] = []
    timing: list[list[dict]] = []
    cursor = 0  # samples
    for p_idx, para in enumerate(paragraphs):
        sentences = split_sentences(para)
        para_timing = []
        for s_idx, sentence in enumerate(sentences):
            clip = synth(sentence)
            v_start, v_end = voiced_span(clip)
            a, b = max(0, int((v_start - PAD) * SR)), min(len(clip), int((v_end + PAD) * SR))
            clip = clip[a:b]
            para_timing.append({
                "text": sentence,
                "start": round((cursor + int(v_start * SR) - a) / SR, 3),
                "end": round((cursor + int(v_end * SR) - a) / SR, 3),
            })
            last_in_para = s_idx == len(sentences) - 1
            gap = silence(GAP_TITLE if p_idx == 0 and last_in_para
                          else GAP_PARAGRAPH if last_in_para else GAP_SENTENCE)
            parts += [clip, gap]
            cursor += len(clip) + len(gap)
        timing.append(para_timing)
    return np.concatenate(parts), timing


Synth = Callable[[str], np.ndarray]
Encoder = Callable[[np.ndarray, Path, dict], None]


def narrate_book(work: Path, out: Path, synth: Synth, encode: Encoder,
                 only: Container[int] | None = None, settings: str = "") -> list[str]:
    """Narrate each chapter in book.json; return the stems actually (re)narrated.

    A chapter is skipped when its audio exists and its timing file records the same text and
    settings, so fixing one chapter's breaks and re-running only redoes what changed.
    """
    book = json.loads((work / "book.json").read_text())
    chapters = book["chapters"]
    (out / "audio").mkdir(parents=True, exist_ok=True)
    narrated = []
    for track, chapter in enumerate(chapters, 1):
        if only is not None and track not in only:
            continue
        stem = chapter["stem"]
        text = (work / "text" / f"{stem}.txt").read_text()
        key = hashlib.sha256(f"{settings}\n{text}".encode()).hexdigest()
        target, timing_path = out / "audio" / f"{stem}.m4a", work / "text" / f"{stem}.json"
        if target.exists() and timing_path.exists() and json.loads(timing_path.read_text())["key"] == key:
            continue
        started = time.time()
        audio, timing = narrate_chapter([p for p in text.split("\n\n") if p.strip()], synth)
        tags = {"title": chapter["title"], "album": book["album"],
                "track": f"{track}/{len(chapters)}", "genre": "Audiobook"}
        encode(audio, target, tags)
        timing_path.write_text(json.dumps({"key": key, "paragraphs": timing}, ensure_ascii=False))
        narrated.append(stem)
        print(f"done {stem}: {len(audio) / SR / 60:.1f} min audio in "
              f"{(time.time() - started) / 60:.1f} min", flush=True)
    return narrated


def encode_m4a(audio: np.ndarray, target: Path, tags: dict) -> None:
    """AAC 64k in an .m4a. Written under a temp name so a killed run never leaves a
    truncated file that looks finished."""
    import soundfile as sf

    wav, partial = target.with_suffix(".wav"), target.with_suffix(".part.m4a")
    sf.write(wav, audio, SR)
    metadata = [arg for k, v in tags.items() for arg in ("-metadata", f"{k}={v}")]
    try:
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(wav), "-c:a", "aac",
                        "-b:a", "64k", *metadata, str(partial)], check=True)
        partial.replace(target)
    finally:
        wav.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("work", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--voice", default="af_heart", help="Kokoro voice, e.g. am_michael, bf_emma")
    parser.add_argument("--speed", type=float, default=1.0, help="baked-in speed; the player adds more")
    parser.add_argument("--lang", default="en-us")
    parser.add_argument("--only", help="comma-separated chapter numbers, e.g. 1 for a preview")
    args = parser.parse_args()

    from kokoro_onnx import Kokoro

    kokoro = Kokoro(str(MODELS / "kokoro-v1.0.onnx"), str(MODELS / "voices-v1.0.bin"))

    def synth(text: str) -> np.ndarray:
        samples, rate = kokoro.create(text, voice=args.voice, speed=args.speed, lang=args.lang)
        assert rate == SR, rate
        return samples.astype(np.float32)

    only = {int(n) for n in args.only.split(",")} if args.only else None
    settings = f"{args.voice}|{args.speed}|{args.lang}"
    narrate_book(args.work, args.out, synth, encode_m4a, only, settings)


if __name__ == "__main__":
    main()
