# audiobook-skill

A [Claude Code](https://claude.com/claude-code) skill that turns a PDF, Markdown or plain-text file into a narrated audiobook. Everything runs locally, with no cloud TTS.

```
/audiobook ~/Desktop/Some Book.pdf
```

> [!IMPORTANT]
> **For personal use only.** Audiobooks made with this tool are not meant for publication.
> Most books, guides and articles are copyrighted, and narrating one is creating a derivative
> work. Before you share any output, including the audio files, the player or the extracted
> text, make sure you have permission from the rights holder.

You get a folder like this:

```
Some Book/
  Some Book.pdf
  Audio Player.html          # single file, works offline
  audio/
    01 - Introduction.m4a    # tagged: title, album, track n/total
    02 - Chapter 1 – ….m4a
    …
```

## The player

`Audio Player.html` is self-contained. Double-click it; no server is needed. It has:

- a chapter picker, with previous and next buttons
- the chapter text, which scrolls along with the audio
- a subtle highlight on the current sentence, and a lighter one on the current word
- click-to-seek on any sentence
- a playback-speed slider from 0.5× to 3.5× in 0.25 steps
- ±15 s skip buttons
- keyboard shortcuts
- per-browser memory of position and speed
- light and dark themes

The `.m4a` files are ordinary tagged AAC, so they also work in any music or podcast app.

## How it works

The scripts do the mechanical work. Claude handles what needs judgment: where chapters break, which lines are running headers, and whether the text reads cleanly aloud.

| Step | Script | What it does |
|---|---|---|
| Setup | `scripts/setup.sh` | Creates a venv in `~/.cache/audiobook/` and downloads the Kokoro v1.0 models (~340 MB, sha256-verified). Idempotent. |
| Inspect | `scripts/inspect_source.py` | Prints the PDF outline, repeated lines (header and footer candidates), text-layer artifacts and each page's first lines. For text files, it lists heading candidates. |
| Spec | *(Claude)* | Writes `spec.json`: chapter starts by page and/or regex, lines to drop, optional fixes, and text replacements. |
| Extract | `scripts/extract.py` | Applies the spec to produce clean per-chapter text. Prints each chapter's first and last lines for spot-checking. |
| Narrate | `scripts/narrate.py` | Synthesises each sentence with [Kokoro](https://github.com/thewh1teagle/kokoro-onnx), trims silence, records per-sentence timing and encodes AAC. Re-runs skip chapters whose text and voice settings haven't changed. |
| Build | `scripts/build_player.py` | Embeds the chapter list and timing into the `scripts/player.html` template. |
| Verify | `scripts/serve.py` | Starts a localhost static server with HTTP Range support, so Claude can check the player in a browser. |

[`SKILL.md`](SKILL.md) is the full procedure Claude follows, including the spec format.

Narration runs about 3–4× faster than real time on Apple Silicon. A 4-hour book takes a little over an hour.

## Install

Requirements:
- Claude Code
- Python 3.10 or later ([uv](https://docs.astral.sh/uv/) is used if present)
- ffmpeg, for example `brew install ffmpeg`
- ~1 GB of disk for the venv and models

Developed on macOS; Linux should work.

```bash
git clone https://github.com/msmeeks/audiobook-skill.git ~/Code/audiobook-skill
```

```bash
ln -s ~/Code/audiobook-skill ~/.claude/skills/audiobook
```

Restart Claude Code, then run `/audiobook <file>`. The first run sets up the venv and models, which takes about a minute.

## Using the scripts directly

The skill directory works without Claude too:

```bash
S=~/Code/audiobook-skill/scripts
```

```bash
bash $S/setup.sh
```

```bash
PY=~/.cache/audiobook/venv/bin/python
```

```bash
$PY $S/inspect_source.py book.pdf
```

Write `work/spec.json` (see the example in [SKILL.md](SKILL.md#4-write-workspecjson)), then:

```bash
$PY $S/extract.py work/spec.json book.pdf work
```

```bash
$PY $S/narrate.py work out --voice af_heart
```

```bash
$PY $S/build_player.py work out
```

### Voices

- **US English:** `af_heart` (default), `af_bella`, `af_nicole`, `am_michael`, `am_adam`, `am_eric`
- **UK English** (pass `--lang en-gb`): `bf_emma`, `bf_isabella`, `bm_george`, `bm_lewis`, `bm_daniel`

## Limitations

- Scanned PDFs have no text layer. Run them through OCR first, for example with `ocrmypdf`.
- Word highlighting is estimated from word length within each sentence's measured timing, so it can drift slightly within long sentences.
- Tables, forms and footnotes read awkwardly aloud. The spec's `drop_lines` and `replace` help, but heavily formatted books need hand cleanup.

## Development

```bash
~/.cache/audiobook/venv/bin/python -m pytest
```

```bash
node --test tests/player.test.mjs
```

```bash
uvx ruff check .
```

## License

MIT; see [LICENSE](LICENSE).

Dependencies are installed by `setup.sh`, not bundled:
- Kokoro model weights: Apache-2.0
- kokoro-onnx: MIT
- PyMuPDF: AGPL-3.0
