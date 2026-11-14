"use client";
// DEV ONLY: /dev/cards shows the detail card for EVERY tip in content/tips.json, to check them by eye.
// Real use can only turn a few pairs red today (the rest wait for their detectors), so this is the only place
// most cards can be seen. Not linked from the app.

import { useEffect, useState } from "react";
import DetailCard from "@/components/DetailCard";
import { loadCardData, type ArticulationTable, type Lang, type TipsTable, type WordResult } from "@/lib/api";
import { buildCard } from "@/lib/card";

// A stand-in word: the first practice word (or "now" for the not-heard card).
function fakeWord(practice: string[]): WordResult {
  return { word: practice[0] ?? "now", status: "red", start: 0, end: 0, display: [] };
}

export default function DevCards() {
  const [data, setData] = useState<{ tips: TipsTable; articulation: ArticulationTable } | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    loadCardData().then(setData, (e: Error) => setError(e.message));
  }, []);

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-8 px-4 py-10">
      <p className="rounded bg-amber-100 p-3 text-amber-900 dark:bg-amber-900 dark:text-amber-100">
        DEV ONLY: every detail card, with a practice word standing in for the red word. Review status per tip
        is in content/build_tips.py (REVIEWED); unreviewed cards say &quot;Draft tip&quot;.
      </p>
      {error && <p className="text-red-600">{error}</p>}
      {data &&
        (["en", "ko"] as Lang[]).map((lang) => (
          <section key={lang} className="flex flex-col gap-6">
            <h2 className="text-xl font-semibold">{lang === "en" ? "Learning English" : "Learning Korean"}</h2>
            {Object.entries(data.tips.tips[lang]).map(([pair, t]) => {
              const card = buildCard({ pair, ipa: t.target ?? "", index: 0, start: null, end: null }, fakeWord(t.practice), data.tips, lang);
              return (
                card && (
                  <div key={pair} id={pair}>
                    <p className="mb-1 font-mono text-xs text-neutral-500">{pair}</p>
                    <DetailCard card={card} articulation={data.articulation} />
                  </div>
                )
              );
            })}
          </section>
        ))}
    </main>
  );
}
