"use client";
// One card per mistake, shown under the results (every red word's cards at once, in sentence order).
// What happened + the mouth (target vs what you probably did) + how to fix it + practice words (tap to hear a native
// voice say each one) + compare your word with the native voice saying the same word on its own.

import MouthDiagram from "@/components/MouthDiagram";
import { useUi } from "@/components/UiLang";
import { descText } from "@/lib/i18n";
import type { ArticulationTable } from "@/lib/api";
import type { Card } from "@/lib/card";

export default function DetailCard({
  card,
  articulation,
  onPlayWord,
  onPlayNativeWord,
  onPlayPractice,
  playing,
  error,
}: {
  card: Card;
  articulation: ArticulationTable;
  onPlayWord?: () => void; // your whole word (absent: no recording, or the word wasn't heard)
  onPlayNativeWord?: () => void; // the native voice saying the word on its own (absent: dev page, no audio)
  onPlayPractice?: (word: string) => void; // a native voice says this practice word (absent: plain chips)
  playing?: string | null; // which practice word is playing, to highlight it
  error?: string; // a native clip that couldn't be fetched (e.g. the limit for new audio)
}) {
  const { ui, t } = useUi();
  const target = card.target && articulation.sounds[card.target.lang][card.target.sym];
  const produced = card.produced && articulation.sounds[card.produced.lang][card.produced.sym];
  const btn =
    "rounded-xl border-[2.5px] border-ink bg-white px-3 py-1.5 text-sm font-medium text-ink shadow-pop-xs transition-[transform,box-shadow] hover:bg-sky active:translate-x-[2px] active:translate-y-[2px] active:shadow-none";

  return (
    <article className="flex flex-col gap-4 rounded-[20px] border-[2.5px] border-ink bg-white p-4 shadow-pop lg:rounded-3xl lg:p-6">
      <h3 className="m-0 font-display text-xl lg:text-2xl">{card.whatHappened}</h3>

      {!card.simple && target && !produced && ( // a left-out sound: the correct mouth only
        <div className="grid grid-cols-1 gap-3 sm:max-w-[50%]">
          <MouthDiagram entry={target} title={t("targetTag")}
            description={descText(ui, card.target!.lang, card.target!.sym, target.description)} />
        </div>
      )}
      {!card.simple && target && produced && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <MouthDiagram entry={target} title={t("targetTag")}
            description={descText(ui, card.target!.lang, card.target!.sym, target.description)} />
          <MouthDiagram entry={produced} title={t("yoursTag")} tone="yours"
            description={descText(ui, card.produced!.lang, card.produced!.sym, produced.description)} />
        </div>
      )}
      <section>
        <h4 className="m-0 font-display text-lg">{t("howToFix")}</h4>
        <p>{card.tip}</p>
      </section>

      {card.practice.length > 0 && (
        <section>
          <h4 className="m-0 font-display text-lg">{t("practiceWords")}</h4>
          <ul lang={card.target?.lang} className="mt-1 flex flex-wrap gap-2 text-lg">
            {card.practice.map((w) => (
              <li key={w}>
                {onPlayPractice ? (
                  <button type="button" onClick={() => onPlayPractice(w)} aria-label={t("playWord", { w })}
                    className={`${btn} text-lg ${playing === w ? "bg-sky" : ""}`}>
                    ▶ {w}
                  </button>
                ) : (
                  <span className="block rounded-lg border-2 border-ink bg-tray px-2 py-0.5">{w}</span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {(onPlayWord || onPlayNativeWord) && (
        <section className="flex flex-col gap-2">
          <h4 className="m-0 font-display text-lg">{t("compare")}</h4>
          <div className="flex flex-wrap gap-2">
            {onPlayWord && (
              <button type="button" onClick={onPlayWord} className={btn}>
                {t("yourX", { x: `“${card.word}”` })}
              </button>
            )}
            {onPlayNativeWord && (
              <button type="button" onClick={onPlayNativeWord} className={btn}>
                {t("nativeX", { x: `“${card.word}”` })}
              </button>
            )}
          </div>
        </section>
      )}
      {error && <p className="m-0 text-sm text-red-600">{error}</p>}
      {(!card.reviewed || card.needsNativeReview) && (
        <p className="m-0 text-xs text-neutral-500">
          {!card.reviewed && t("draftTip")}
          {card.needsNativeReview && t("needsNative")}
        </p>
      )}
    </article>
  );
}
