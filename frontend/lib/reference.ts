// "see it on a real speaker". Seeing Speech (University of Glasgow) has real MRI of each IPA sound,
// licensed CC BY-NC-ND 4.0, so we only LINK to it (never copy or trace). Its videos open in a pop-up, so there is
// no link to a single sound: we link the right chart and say which symbol to tap.

const BASE = "https://www.seeingspeech.ac.uk";
const CHART = (n: number) => `${BASE}/ipa-charts/?chart=${n}&datatype=1&speaker=1`; // datatype 1 = MRI
const TENSE = "͈";

export type Reference = { url: string; tap: string; note?: string };

export function seeingSpeech(lang: string, sym: string, kind: string): Reference {
  if (lang === "en" && (sym === "ɹ" || sym === "l")) return { url: `${BASE}/r-and-l-in-english/`, tap: sym };
  const vowel = kind === "vowel" || kind === "diphthong";
  let tap = sym.replace("ː", "").replace(TENSE, "").replace("ʰ", "");
  let note: string | undefined;
  if (sym.includes(TENSE))
    note = "Korean tense sounds aren't on the chart. Watch the lips and tongue; the difference is a tight throat and no puff of air, which an MRI of the mouth doesn't show.";
  else if (sym.includes("ʰ") && lang === "ko")
    note = "Watch the lips and tongue; the difference from the plain sound is the big puff of air, which an MRI of the mouth doesn't show.";
  if (kind === "diphthong") {
    tap = tap[0];
    note = "This sound glides; the chart shows where it starts.";
  }
  return { url: CHART(vowel ? 4 : 1), tap, note };
}
