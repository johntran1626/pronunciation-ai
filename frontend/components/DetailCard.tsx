"use client";
// The card that opens when you tap a red word or syllable.
// What happened + the mouth (target vs what you probably did) + how to fix it + practice words + replay.

import MouthDiagram from "@/components/MouthDiagram";
import type { ArticulationTable } from "@/lib/api";
import type { Card } from "@/lib/card";
import { seeingSpeech } from "@/lib/reference";

export default function DetailCard({
  card,
  articulation,
  onPlaySound,
  onPlayWord,
  onPlayNativeSound,
  onPlayNativeWord,
  nativeStatus,
  onClose,
}: {
  card: Card;
  articulation: ArticulationTable;
  onPlaySound?: () => void; // just the bad sound in your recording (absent: no audio, or nothing to play)
  onPlayWord?: () => void; // your whole word
  onPlayNativeSound?: () => void; // The same sound in the native clip (absent: not loaded / not found)
  onPlayNativeWord?: () => void; // the same word in the native clip
  nativeStatus?: string; // "loading", "ready", or an error message (absent: no native audio for this card, e.g. dev page)
  onClose?: () => void;
}) {
  const target = card.target && articulation.sounds[card.target.lang][card.target.sym];
  const produced = card.produced && articulation.sounds[card.produced.lang][card.produced.sym];
  const real = card.target && target ? seeingSpeech(card.target.lang, card.target.sym, target.kind) : null;
  const btn =
    "rounded-lg border border-neutral-300 px-3 py-1.5 text-sm hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800";

  return (
    <article className="flex flex-col gap-4 rounded-xl border-2 border-red-300 bg-white p-4 dark:border-red-900 dark:bg-neutral-950">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold">{card.whatHappened}</h3>
          <p className="text-sm text-neutral-500">Estimated from your audio. The app can&apos;t see your mouth.</p>
        </div>
        {onClose && (
          <button type="button" onClick={onClose} aria-label="Close" className={btn}>
            ✕
          </button>
        )}
      </header>

      {!card.simple && target && produced && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <MouthDiagram entry={target} title={`Target: ${card.targetLabel}`} />
          <MouthDiagram entry={produced} title={`What you probably did: ${card.producedLabel}`} tone="yours" />
        </div>
      )}
      {!card.simple && target && (
        <p className="text-xs text-neutral-500">
          Drawings show the textbook position (based on public-domain diagrams by R. Wright &amp; D. McCloy), not your
          mouth.
          {real && (
            <>
              {" "}
              See a real mouth:{" "}
              <a href={real.url} target="_blank" rel="noopener noreferrer" className="underline">
                MRI on Seeing Speech (Univ. of Glasgow)
              </a>
              {real.url.includes("ipa-charts") && <>, then tap [{real.tap}]</>}. {real.note}
            </>
          )}
        </p>
      )}

      <section>
        <h4 className="font-medium">How to fix it</h4>
        <p>{card.tip}</p>
      </section>

      {card.practice.length > 0 && (
        <section>
          <h4 className="font-medium">Practice words</h4>
          <ul lang={card.target?.lang} className="mt-1 flex flex-wrap gap-2 text-lg">
            {card.practice.map((w) => (
              <li key={w} className="rounded bg-neutral-100 px-2 py-0.5 dark:bg-neutral-800">
                {w}
              </li>
            ))}
          </ul>
        </section>
      )}

      {(onPlaySound || onPlayWord || nativeStatus) && (
        <section className="flex flex-col gap-2">
          <h4 className="font-medium">Compare</h4>
          {card.sound && (onPlaySound || onPlayNativeSound) && (
            <div className="flex flex-wrap gap-2">
              {onPlaySound && (
                <button type="button" onClick={onPlaySound} className={btn}>
                  ▶ Your {card.targetLabel}
                </button>
              )}
              {onPlayNativeSound && (
                <button type="button" onClick={onPlayNativeSound} className={btn}>
                  ▶ Native {card.targetLabel}
                </button>
              )}
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            {onPlayWord && (
              <button type="button" onClick={onPlayWord} className={btn}>
                ▶ Your “{card.word}”
              </button>
            )}
            {onPlayNativeWord ? (
              <button type="button" onClick={onPlayNativeWord} className={btn}>
                ▶ Native “{card.word}”
              </button>
            ) : (
              nativeStatus === "loading" && (
                <button type="button" disabled className={`${btn} opacity-50`}>
                  ▶ Native: loading…
                </button>
              )
            )}
          </div>
          {nativeStatus && nativeStatus !== "loading" && nativeStatus !== "ready" && (
            <p className="text-sm text-red-600 dark:text-red-400">{nativeStatus}</p>
          )}
        </section>
      )}
      <p className="text-xs text-neutral-500">
        {nativeStatus && "Native = computer voice (Azure), cut at the times our aligner found (edges can be a little off)."}
        {!card.reviewed && " Draft tip, not reviewed yet."}
        {card.needsNativeReview && " Not yet checked by a native Korean speaker."}
      </p>
    </article>
  );
}
