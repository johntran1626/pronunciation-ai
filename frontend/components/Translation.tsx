"use client";
// The English meaning of a typed Korean sentence, under the sentence. Shows nothing if the translation fails.
import { useEffect, useState } from "react";
import { useUi } from "@/components/UiLang";
import { fetchTranslation, type Translation as Answer } from "@/lib/api";

export default function Translation({ text, className = "text-sm text-neutral-500" }: { text: string; className?: string }) {
  const { t } = useUi();
  // The text this answer belongs to, so an old answer is never shown for a new sentence.
  const [answer, setAnswer] = useState<{ text: string; result: Answer | null } | null>(null);

  useEffect(() => {
    let current = true; // false once the sentence changes: a late answer is dropped
    fetchTranslation(text, "ko").then((result) => {
      if (current) setAnswer({ text, result });
    });
    return () => {
      current = false;
    };
  }, [text]);

  if (!answer || answer.text !== text) return <p className={`${className} opacity-60`}>{t("translating")}</p>;
  if (!answer.result) return null;
  return <p lang="en" className={className}>{answer.result.translation}</p>;
}
