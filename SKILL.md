---
name: audiobook
description: Turn a PDF, Markdown or plain-text file into a narrated audiobook — one tagged .m4a per chapter (local Kokoro TTS, no cloud) plus a single-file "Audio Player.html" with chapter select, synced scrolling text, subtle sentence/word highlight, and a 0.5–3.5× speed slider. Use when the user wants a document read aloud, turned into audio, or given an audio player.
---

# Audiobook

The scripts do the mechanical work. Your job is the judgment: where chapters break, which
lines are page furniture, and whether the extracted text reads cleanly aloud.

```bash
S=~/.claude/skills/audiobook/scripts
PY=~/.cache/audiobook/venv/bin/python
```

## 1. Setup

Run `bash $S/setup.sh` every time. It is idempotent and quick once set up. The first run takes about a minute and does three things:
- creates the venv in `~/.cache/audiobook/`
- clones or downloads the 340 MB Kokoro models, verified against sha256
- checks for ffmpeg

## 2. Choose folders

- **OUT**, the deliverable folder. Ends up holding the source file, `Audio Player.html`, and `audio/`.
  - Use the folder the user names.
  - If they name none, create a folder next to the source, named after the book.
  - macOS may block writes to `~/Documents` and `~/Downloads` until the user grants the terminal access. If a write fails with "Operation not permitted", ask the user to grant access or pick another place, such as the Desktop.
- **WORK**, `~/.cache/audiobook/work/<book-slug>/`. Holds the spec, the extracted text and the timing files.
  - It must outlive this session, so that re-runs resume and the player can be rebuilt.

## 3. Inspect the source

```bash
$PY $S/inspect_source.py SOURCE                # overview
$PY $S/inspect_source.py SOURCE --from 40 --to 60 --lines 5
$PY $S/inspect_source.py SOURCE --dump 4       # one PDF page in full, e.g. the contents page
```

- **PDF:** the report shows:
  - the outline, if there is one
  - repeated lines, which are candidates for running headers and footers
  - text-layer artifacts
  - the first lines of every page
- **Text and Markdown:** the report shows heading candidates with their line numbers.
- **Page numbers:** `p14` means physical PDF page 14, counting from 1. Printed page numbers are usually offset from this. Work out the offset from the contents page and one known chapter opener.
- **Scanned PDFs:** if there are many pages at 0 words with images, the PDF has no text layer. Tell the user it needs OCR first, for example `ocrmypdf`. Don't guess.

## 4. Write `WORK/spec.json`

```json
{
  "album": "Book Title: Subtitle",
  "chapters": [
    {"title": "Introduction", "page": 6},
    {"title": "Lesson 1 – First Steps", "page": 14},
    {"title": "Chapter 2", "page": 30, "start": "^Chapter 2$", "spoken": ""},
    {"title": "Epilogue", "start": "^Epilogue$", "end": "^Acknowledgments$", "end_page": 210}
  ],
  "drop_lines": ["^The Book Title$", "^\\d+ \\| Chapter \\d+$"],
  "fixes": ["kerning", "letter_spaced"],
  "replace": [["\\[(\\d+) min\\]", "(\\1 minutes)"]]
}
```

### Chapter fields

- **Where a chapter starts.** Each chapter needs `page`, `start`, or both.
  - `page` starts the chapter at the first paragraph on that PDF page.
  - `start` is a regex that starts it at the first matching paragraph.
  - With both, the chapter starts at the first match on or after that page, which handles chapters that begin mid-page.
  - Text sources have no pages, so they always use `start`.
  - `start` and `end` match the cleaned paragraph, after `drop_lines`, `fixes` and `replace` have run. A line removed by `drop_lines` can't be matched.
- **Where a chapter ends.** By default a chapter runs until the next one starts.
  - `end` is a regex. It ends the chapter at the first matching paragraph, which is excluded.
  - `end_page` drops everything after that page.
  - Use these to cut back matter, or anything that sits between chapters.
- **Order.** Chapters must be listed in reading order. Each search begins after the previous chapter's start.
- **`title`** is shown in the player and used in file names and tags. Use an en dash: "Lesson 1 – Name".
- **`spoken`** is read aloud before the chapter.
  - It defaults to the title, with dashes and colons turned into periods and `&` into "and".
  - Set it to `""` when the chapter's first paragraph already announces the chapter, which is typical when `start` matches a heading. Otherwise the listener hears the title twice.

### What counts as a chapter

A chapter is a unit a listener would want as a track: the introduction, each chapter or lesson, and an epilogue.

By default, skip the cover, copyright, contents, index, bibliography, endnotes and answer keys. Mention what you skipped.

If the source has no headings, split it into parts of about 15–30 minutes at natural breaks, and name them "Part 1" and so on.

### Cleanup fields

- **`drop_lines`** is a list of regexes matched against single lines, before lines are joined into paragraphs.
  - Use them for running headers and footers, section-number graphics, and similar page furniture.
  - Bare page numbers, and lowercase roman numerals up to 7 characters, are always dropped.
  - Do **not** drop repeated lines that are real content, such as recurring section headings like "Big Idea" or "Discussion".
- **`fixes`** turns on optional repairs for the artifacts the inspector reports:
  - `kerning`: "H arbor" → "Harbor"
  - `letter_spaced`: removes decorative labels like "s t u d y g u i d e"
  - Enable a fix only if the inspector's samples look like errors.
- **`replace`** is a list of `[regex, replacement]` pairs, applied in order after cleanup. Use it for speakable forms and for book-specific glitches.
  - Python `re` syntax: refer to groups as `\\1` in the JSON.
  - Keep replacements narrow, because they apply to the whole book.
- **Always applied:**
  - de-hyphenation across line breaks
  - bullet, soft-hyphen and fill-in-blank removal
  - private-use glyph removal
  - Markdown stripping
  - merging of paragraphs broken across pages

## 5. Extract and spot-check

```bash
$PY $S/extract.py WORK/spec.json SOURCE WORK
```

For every chapter, the output shows the start page, the word count, an estimated duration, and the first and last ~90 characters.

**Check every boundary.** Each chapter should start at its heading and end at the end of the chapter, not at the start of the next one.

Then read at least the first chapter's `.txt` and skim the others. Look for:
- headers or page numbers caught mid-paragraph
- figure captions, footnote markers, and garbled glyphs
- tables or forms that read badly aloud

Fix the spec and re-run until the text is clean. Extraction is cheap; narration is not.

## 6. Narrate in the background

```bash
$PY $S/narrate.py WORK OUT [--voice af_heart] [--speed 1.0] [--only 1,2]
```

Run it with `run_in_background` and don't poll.

- **Duration.** Narration runs about 3–4× faster than real time on Apple Silicon. Tell the user the estimate up front: total minutes ÷ 3.5.
- **Re-runs.** A re-run only redoes chapters whose text or voice settings changed. It's safe to fix one chapter's spec and re-run.
- **Voice.** The default is `af_heart`, a warm US female voice. Other voices:
  - US: `af_bella`, `af_nicole`, `am_michael`, `am_adam`, `am_eric`
  - UK, with `--lang en-gb`: `bf_emma`, `bf_isabella`, `bm_george`, `bm_lewis`, `bm_daniel`
- **Speed.** Leave `--speed` at 1.0. The player has its own speed control.
- **Preview.** For a long book, run `--only 1` first if the user wants to hear the voice before committing to a long job.

While it runs, once chapter 1 is done, build a preview with `$PY $S/build_player.py WORK OUT --partial` and verify the player as in step 8.

## 7. Build the player

```bash
$PY $S/build_player.py WORK OUT
cp SOURCE OUT/     # unless it is already there
```

The build fails if any chapter has no audio. It warns about audio in `OUT/audio/` that no chapter uses. That audio is left over from renamed chapters: delete it.

## 8. Verify in the browser pane

The pane can't open `file://` pages, and audio seeking needs HTTP Range support. Start the bundled server in the background:

```bash
$PY $S/serve.py OUT 8765
```

Open `http://127.0.0.1:8765/Audio%20Player.html` and check:
- The chapter list is complete.
- Play: the text scrolls and the highlight follows the voice.
- Seeking past the middle doesn't jump back to 0:00.
- The speed slider runs from 0.5 to 3.5.
- There are no console errors.

Stop the server afterwards.

## 9. Report

Tell the user:
- the OUT path
- the number of chapters and the total audio time
- the voice used
- anything you skipped or couldn't clean up

How the player works for them:
- They double-click `Audio Player.html`. It works offline.
- The whole folder can be zipped and shared.
- Position and speed are saved per browser.
- The `.m4a` files are tagged, so they also work in any music or podcast app.

## Development

- `tests/`:
  - pytest: `$PY -m pytest` in the skill directory
  - node tests for the player's logic: `node --test tests/player.test.mjs`
- Lint with `uvx ruff check .`.
- `player.html` is the template. `build_player.py` replaces `__PLAYER_DATA__` with the book's JSON.
