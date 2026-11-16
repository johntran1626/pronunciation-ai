"use client";
// The card that opens when you tap a red word or syllable.
// What happened + the mouth (target vs what you probably did) + how to fix it + practice words + replay.

import MouthDiagram from "@/components/MouthDiagram";
import { useUi } from "@/components/UiLang";
import { descText, say } from "@/lib/i18n";
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
  const { ui, t } = useUi();
  const target = card.target && articulation.sounds[card.target.lang][card.target.sym];
  const produced = card.produced && articulation.sounds[card.produced.lang][card.produced.sym];
  const real = card.target && target ? seeingSpeech(card.target.lang, card.target.sym, target.kind) : null;
  const btn =
    "rounded-xl border-[2.5px] border-ink bg-white px-3 py-1.5 text-sm font-medium text-ink shadow-pop-xs transition-[transform,box-shadow] hover:bg-sky active:translate-x-[2px] active:translate-y-[2px] active:shadow-none";

  return (
    <article className="flex flex-col gap-4 rounded-[20px] border-[2.5px] border-ink bg-white p-4 shadow-pop lg:rounded-3xl lg:p-6">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h3 className="m-0 font-display text-xl lg:text-2xl">{card.whatHappened}</h3>
          <p className="m-0 text-sm text-neutral-600">{t("cardEstimated")}</p>
        </div>
        {onClose && (
          <button type="button" onClick={onClose} aria-label={t("close")} className={btn}>
            ✕
          </button>
        )}
      </header>

      {!card.simple && target && !produced && ( // a left-out sound: the correct mouth only
        <div className="grid grid-cols-1 gap-3 sm:max-w-[50%]">
          <MouthDiagram entry={target} title={t("targetIs", { x: card.targetLabel })}
            description={descText(ui, card.target!.lang, card.target!.sym, target.description)} />
        </div>
      )}
      {!card.simple && target && produced && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <MouthDiagram entry={target} title={t("targetIs", { x: card.targetLabel })}
            description={descText(ui, card.target!.lang, card.target!.sym, target.description)} />
          <MouthDiagram entry={produced} title={t("yoursIs", { x: card.producedLabel ?? "" })} tone="yours"
            description={descText(ui, card.produced!.lang, card.produced!.sym, produced.description)} />
        </div>
      )}
      {!card.simple && target && (
        <p className="text-xs text-neutral-500">
          {t("drawings")}
          {real && (
            <>
              {" "}
              {t("seeReal")}{" "}
              <a href={real.url} target="_blank" rel="noopener noreferrer" className="underline">
                {t("mriLink")}
              </a>
              {real.url.includes("ipa-charts") && t("thenTap", { x: real.tap })}. {real.note && say(ui)(real.note)}
            </>
          )}
        </p>
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
              <li key={w} className="rounded-lg border-2 border-ink bg-tray px-2 py-0.5">
                {w}
              </li>
            ))}
          </ul>
        </section>
      )}

      {(onPlaySound || onPlayWord || nativeStatus) && (
        <section className="flex flex-col gap-2">
          <h4 className="m-0 font-display text-lg">{t("compare")}</h4>
          {card.sound && (onPlaySound || onPlayNativeSound) && (
            <div className="flex flex-wrap gap-2">
              {onPlaySound && (
                <button type="button" onClick={onPlaySound} className={btn}>
                  {t("yourX", { x: card.targetLabel })}
                </button>
              )}
              {onPlayNativeSound && (
                <button type="button" onClick={onPlayNativeSound} className={btn}>
                  {t("nativeX", { x: card.targetLabel })}
                </button>
              )}
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            {onPlayWord && (
              <button type="button" onClick={onPlayWord} className={btn}>
                {t("yourX", { x: `“${card.word}”` })}
              </button>
            )}
            {onPlayNativeWord ? (
              <button type="button" onClick={onPlayNativeWord} className={btn}>
                {t("nativeX", { x: `“${card.word}”` })}
              </button>
            ) : (
              nativeStatus === "loading" && (
                <button type="button" disabled className={`${btn} opacity-50`}>
                  {t("nativeLoading")}
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
        {nativeStatus && t("nativeNote")}
        {!card.reviewed && t("draftTip")}
        {card.needsNativeReview && t("needsNative")}
      </p>
    </article>
  );
}
