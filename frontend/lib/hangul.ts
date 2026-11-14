// Split a Hangul syllable block into its letters (jamo). Same arithmetic as backend/g2p.py.
//
// Unicode stores every possible block in order from 가 (U+AC00):
//   index = (onset * 21 + vowel) * 28 + coda       19 onsets x 21 vowels x 28 codas (0 = none) = 11,172 blocks
const FIRST = 0xac00;
const COUNT = 11172;
const ONSETS = [..."ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"];
const VOWELS = [..."ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"];
const CODAS = ["", ..."ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"];

export type Slot = "onset" | "vowel" | "coda";
export type JamoPart = { jamo: string; slot: Slot };

export function decompose(block: string): JamoPart[] | null {
  if ([...block].length !== 1) return null;
  const index = block.codePointAt(0)! - FIRST;
  if (index < 0 || index >= COUNT) return null; // not a Hangul block (Latin, digit, a lone ㄱ, ...)
  const coda = index % 28;
  const vowel = Math.floor(index / 28) % 21;
  const onset = Math.floor(index / 28 / 21);
  const parts: JamoPart[] = [
    { jamo: ONSETS[onset], slot: "onset" },
    { jamo: VOWELS[vowel], slot: "vowel" },
  ];
  if (coda) parts.push({ jamo: CODAS[coda], slot: "coda" });
  return parts;
}
