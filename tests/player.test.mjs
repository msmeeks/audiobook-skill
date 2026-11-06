// Tests the pure player logic embedded in player.html (the <script id="core"> block).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const html = readFileSync(new URL("../scripts/player.html", import.meta.url), "utf8");
const core = html.match(/<script id="core">([\s\S]*?)<\/script>/)[1];
const ctx = {};
vm.runInNewContext(core + "\nthis.Core = Core;", ctx);
const { Core } = ctx;

test("speed snaps to 0.25 steps within 0.5–3.5", () => {
  assert.equal(Core.clampSpeed(1.1), 1);
  assert.equal(Core.clampSpeed(1.13), 1.25);
  assert.equal(Core.clampSpeed(0.1), 0.5);
  assert.equal(Core.clampSpeed(9), 3.5);
  assert.equal(Core.clampSpeed(NaN), 1);
});

test("word times tile the sentence span in order, weighted by length and pauses", () => {
  const words = Core.wordTimes({ text: "Grace, abundantly given.", start: 10, end: 12 });
  assert.deepEqual(Array.from(words, (w) => w.word), ["Grace,", "abundantly", "given."]);
  assert.equal(words[0].start, 10);
  assert.ok(Math.abs(words.at(-1).end - 12) < 1e-9);
  for (let i = 1; i < words.length; i++) assert.equal(words[i].start, words[i - 1].end);
  const dur = (w) => w.end - w.start;
  assert.ok(dur(words[1]) > dur(words[2]), "longer word gets more time");
  assert.ok(dur(words[0]) > dur(words[2]) * 0.9, "comma pause adds weight to 'Grace,'");
});

test("active item is the last one started at time t; -1 before the first", () => {
  const items = [{ start: 0.2, end: 1 }, { start: 1.3, end: 2 }, { start: 2.5, end: 3 }];
  assert.equal(Core.findActive(items, 0), -1);
  assert.equal(Core.findActive(items, 0.2), 0);
  assert.equal(Core.findActive(items, 1.1), 0, "gap keeps the previous sentence");
  assert.equal(Core.findActive(items, 1.3), 1);
  assert.equal(Core.findActive(items, 99), 2);
  assert.equal(Core.findActive([], 5), -1);
});

test("times format as m:ss, or h:mm:ss past an hour", () => {
  assert.equal(Core.formatTime(0), "0:00");
  assert.equal(Core.formatTime(65.9), "1:05");
  assert.equal(Core.formatTime(3725), "1:02:05");
  assert.equal(Core.formatTime(NaN), "0:00");
});

test("short unpunctuated one-sentence paragraphs read as headings", () => {
  const p = (...texts) => texts.map((text) => ({ text }));
  assert.equal(Core.isHeading(p("About the Author")), true);
  assert.equal(Core.isHeading(p("Discussion (10 minutes)")), true);
  assert.equal(Core.isHeading(p("Pray together.")), false);
  assert.equal(Core.isHeading(p("Why do we hide?")), false);
  assert.equal(Core.isHeading(p("Read", "Then talk.")), false);
  assert.equal(Core.isHeading(p("x".repeat(90))), false);
});

test("audio paths keep folder separators but escape each name", () => {
  assert.equal(Core.audioUrl("audio/02 - Lesson 2 - Pretending & Performing.m4a"),
    "audio/02%20-%20Lesson%202%20-%20Pretending%20%26%20Performing.m4a");
  assert.equal(Core.audioUrl("a#b?.m4a"), "a%23b%3F.m4a");
});
