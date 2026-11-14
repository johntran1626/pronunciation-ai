"use client";
// One translation line + the small 존댓말 / 반말 switch. The switch only appears when there are
// two forms; its position is shared by the whole page, so it stays where the learner left it between sentences.
import FormalitySwitch from "@/components/FormalitySwitch";
import { hasBothForms, pickTranslation, type Translated } from "@/lib/translations";

type Props = { t: Translated; textLang: string; casual: boolean; onCasual: (v: boolean) => void };

export default function FormalityLine({ t, textLang, casual, onCasual }: Props) {
  const shown = pickTranslation(t, casual);
  if (!shown) return null;
  return (
    <div className="flex flex-wrap items-center gap-3 text-sm text-neutral-500">
      <span lang={textLang}>{shown.text}</span>
      {hasBothForms(t) && <FormalitySwitch casual={casual} onCasual={onCasual} />}
    </div>
  );
}
