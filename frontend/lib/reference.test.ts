// The "see a real speaker" link (Seeing Speech, CC BY-NC-ND: we only LINK to it).
import { test } from "node:test";
import assert from "node:assert/strict";
import { seeingSpeech } from "./reference.ts";

test("English R and L go to Seeing Speech's own R/L page", () => {
  assert.equal(seeingSpeech("en", "ɹ", "consonant").url, "https://www.seeingspeech.ac.uk/r-and-l-in-english/");
  assert.equal(seeingSpeech("en", "l", "consonant").url, "https://www.seeingspeech.ac.uk/r-and-l-in-english/");
});

test("other consonants -> consonant chart, vowels -> vowel chart, with the symbol to tap", () => {
  const t = seeingSpeech("ko", "ɾ", "consonant");
  assert.equal(t.url, "https://www.seeingspeech.ac.uk/ipa-charts/?chart=1&datatype=1&speaker=1");
  assert.equal(t.tap, "ɾ");
  const v = seeingSpeech("ko", "ʌ", "vowel");
  assert.equal(v.url, "https://www.seeingspeech.ac.uk/ipa-charts/?chart=4&datatype=1&speaker=1");
  assert.equal(v.tap, "ʌ");
  assert.equal(seeingSpeech("en", "iː", "vowel").tap, "i"); // length mark isn't on the chart
});

test("Korean tense and aspirated stops point at plain [p] and say why", () => {
  for (const s of ["p͈", "pʰ"]) {
    const r = seeingSpeech("ko", s, "consonant");
    assert.equal(r.tap, "p");
    assert.match(r.note!, /throat|air/i); // the difference is in the throat and airflow, which MRI of the mouth doesn't show
  }
});
