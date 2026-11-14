"use client";
// DEV ONLY: /dev/mouth shows the mouth diagram for every MVP confusion pair (target vs what was probably said),
// to check the drawings by eye. Not linked from the app.

import { useEffect, useState } from "react";
import MouthDiagram from "@/components/MouthDiagram";
import { fetchArticulation, type ArticulationTable, type Lang } from "@/lib/api";

// [label, target (lang, symbol), what the learner probably said (lang, symbol)]
const PAIRS: [string, [Lang, string], [Lang, string]][] = [
  ["English R said like L", ["en", "ɹ"], ["en", "l"]],
  ["English F said like P", ["en", "f"], ["en", "p"]],
  ["English V said like B", ["en", "v"], ["en", "b"]],
  ["English TH said like S", ["en", "θ"], ["en", "s"]],
  ["English TH (this) said like D", ["en", "ð"], ["en", "d"]],
  ["ship said like sheep", ["en", "ɪ"], ["en", "iː"]],
  ["ㅓ said like ㅗ", ["ko", "ʌ"], ["ko", "o"]],
  ["ㅡ said like ㅜ", ["ko", "ɯ"], ["ko", "u"]],
  ["ㅐ vs ㅔ (often merged)", ["ko", "ɛ"], ["ko", "e"]],
  ["ㄹ tap said like English R", ["ko", "ɾ"], ["en", "ɹ"]],
  ["ㅃ said like ㅂ", ["ko", "p͈"], ["ko", "p"]],
  ["ㅍ said like ㅂ", ["ko", "pʰ"], ["ko", "p"]],
];

// Korean symbols are hard to read on their own (the tense mark in p͈ is nearly invisible), so name the letter too.
const JAMO: Record<string, string> = {
  ʌ: "ㅓ", o: "ㅗ", ɯ: "ㅡ", u: "ㅜ", ɛ: "ㅐ", e: "ㅔ", ɾ: "ㄹ", p: "ㅂ", "p͈": "ㅃ", pʰ: "ㅍ",
};
const name = (lang: Lang, sym: string) => (lang === "ko" && JAMO[sym] ? `${JAMO[sym]} [${sym}]` : `[${sym}]`);

export default function DevMouth() {
  const [table, setTable] = useState<ArticulationTable | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    fetchArticulation().then(setTable, (e: Error) => setError(e.message));
  }, []);

  return (
    <main className="mx-auto flex w-full max-w-4xl flex-col gap-8 px-4 py-10">
      <p className="rounded bg-amber-100 p-3 text-amber-900 dark:bg-amber-900 dark:text-amber-100">
        DEV ONLY: textbook target articulations (content/articulation.json, not yet reviewed). Not a picture of anyone&apos;s
        mouth.
      </p>
      {error && <p className="text-red-600">{error}</p>}
      {table &&
        PAIRS.map(([label, [tl, ts], [yl, ys]]) => (
          <section key={label} className="flex flex-col gap-3">
            <h2 className="text-lg font-semibold">{label}</h2>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <MouthDiagram entry={table.sounds[tl][ts]} title={`Target: ${name(tl, ts)}`} />
              <MouthDiagram entry={table.sounds[yl][ys]} title={`What you probably did: ${name(yl, ys)}`} tone="yours" />
            </div>
          </section>
        ))}
    </main>
  );
}
