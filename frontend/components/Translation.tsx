"use client";
// The meaning of a Custom sentence, under "We'll check: ...". Shows nothing if the translation fails.
// English -> Korean comes in two forms; FormalityLine shows 존댓말 by default with a small switch to 반말.
import { useEffect, useState } from "react";
import FormalityLine from "@/components/FormalityLine";
import { useUi } from "@/components/UiLang";
import { fetchTranslation, type Lang, type Translation as Answer } from "@/lib/api";

type Props = { text: string; lang: Lang; casual: boolean; onCasual: (v: boolean) => void };

export default function Translation({ text, lang, casual, onCasual }: Props) {
  const { t } = useUi();
  // The text this answer belongs to, so an old answer is never shown for a new sentence.
  const [answer, setAnswer] = useState<{ text: string; result: Answer | null } | null>(null);

  useEffect(() => {
    let current = true; // false once the sentence changes or the card closes: a late answer is dropped
    fetchTranslation(text, lang).then((result) => {
      if (current) setAnswer({ text, result });
    });
    return () => {
      current = false;
    };
  }, [text, lang]);

  if (!answer || answer.text !== text) return <p className="text-sm text-neutral-400">{t("translating")}</p>;
  if (!answer.result) return null;
  return <FormalityLine t={answer.result} textLang={lang === "en" ? "ko" : "en"} casual={casual} onCasual={onCasual} />;
}
