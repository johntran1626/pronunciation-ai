"use client";
// One translation line + the small 존댓말 / 반말 switch. The switch only appears when there are
// two forms; its position is shared by the whole page, so it stays where the learner left it between sentences.
// `big`: the translation is the main thing shown ("Translate to KR"). `switchOnly`: the text is already on screen
// (the animated Korean), so only the switch is drawn.
import FormalitySwitch from "@/components/FormalitySwitch";
import { hasBothForms, pickTranslation, type Translated } from "@/lib/translations";

type Props = { t: Translated; textLang: string; casual: boolean; onCasual: (v: boolean) => void; big?: boolean; switchOnly?: boolean };

export default function FormalityLine({ t, textLang, casual, onCasual, big = false, switchOnly = false }: Props) {
  const shown = pickTranslation(t, casual);
  if (!shown) return null;
  if (switchOnly) return hasBothForms(t) ? <div><FormalitySwitch casual={casual} onCasual={onCasual} /></div> : null;
  return (
    <div className={`flex flex-wrap items-center gap-3 ${big ? "text-xl text-neutral-900 dark:text-neutral-100" : "text-sm text-neutral-500"}`}>
      <span lang={textLang}>{shown.text}</span>
      {hasBothForms(t) && <FormalitySwitch casual={casual} onCasual={onCasual} />}
    </div>
  );
}
