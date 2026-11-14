// Talking to the Python backend (FastAPI). Every backend call goes through this file.

// Where the backend lives. Locally it's uvicorn on port 8000; at deploy we set
// NEXT_PUBLIC_API_URL to the hosted backend instead of editing code.
export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export type Lang = "ko" | "en"; // the language being LEARNED (and spoken in the recording)

export type Health = { ok: boolean };

// Matches content/packs/*.json (see backend/packs.py).
export type PackItem = {
  id: string;
  text: string;
  translation: string | null; // English packs: the 존댓말 (polite) Korean form
  translation_informal?: string | null; // English packs: the 반말 (casual) Korean form
  tags: string[];
};
type PackInfo = {
  id: string;
  lang: Lang;
  name: string;
  dev_only: boolean;
  reviewed: boolean;
  note: string;
  source: string;
  license: string;
};
export type PackSummary = PackInfo & { count: number };
export type Pack = PackInfo & { items: PackItem[] };

// GET a JSON reply, or throw an Error with a readable message.
async function getJSON<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  } catch {
    // fetch only throws when there is no usable reply at all: server down, wrong URL, or CORS blocked.
    throw new Error(`Can't reach the backend at ${API_BASE}. Is uvicorn running?`);
  }
  if (!res.ok) throw new Error(`Backend answered with HTTP ${res.status}`);
  return (await res.json()) as T;
}

export const checkHealth = () => getJSON<Health>("/health");
export const fetchPacks = (lang: Lang) => getJSON<PackSummary[]>(`/packs?lang=${lang}`);
export const fetchPack = (id: string) => getJSON<Pack>(`/packs/${encodeURIComponent(id)}`);

// ---------- /analyze ----------

// One colored piece of a written word (English letters, or a Korean syllable block). See backend/text_map.py.
export type Status = "green" | "red" | "unchecked"; // unchecked = no live check looked at it
export type DisplayPiece = {
  text: string;
  status: Status;
  red_jamo?: string[]; // Korean: which letters in the block were wrong
  red_slots?: ("onset" | "vowel" | "coda")[]; // ...and where (각 has ㄱ twice)
  start?: number;
  end?: number;
};
// One expected sound in a word (backend/scoring.py + match.py). A red one says which mistake (`pair`).
export type PhonemeResult = {
  ipa: string;
  status: Status;
  pair?: string; // e.g. "r_as_l", "extra_vowel", "word_not_heard" (keys of content/tips.json)
  produced?: string | null;
  start: number | null;
  end: number | null;
};
export type WordResult = {
  word: string;
  status: Status;
  not_heard?: boolean; // The word seems skipped or replaced
  start: number;
  end: number;
  display: DisplayPiece[];
  phonemes?: PhonemeResult[]; // Which sounds were red and why (the detail card reads this)
};
// What the recognizer actually heard, in order (backend/recognize.py), whatever the target was.
export type HeardSound = { symbol: string; start: number; end: number; conf: number };
export type AnalyzeResult = {
  text: string;
  lang: Lang;
  duration_s: number;
  matched: boolean; // False = the recording didn't sound like this sentence: show no colors
  reason: "no_speech" | "mismatch" | null;
  checks: string[]; // which checks were live (e.g. ["sentence_match", "word_heard", "r_as_l"])
  words: WordResult[];
  heard?: HeardSound[];
};

// Send a WAV recording + the sentence. Throws an Error with the backend's own message on a bad input.
export async function analyze(wav: Blob, text: string, lang: Lang): Promise<AnalyzeResult> {
  const form = new FormData();
  form.append("audio", wav, "recording.wav");
  form.append("text", text);
  form.append("lang", lang);
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/analyze`, { method: "POST", body: form });
  } catch {
    throw new Error(`Can't reach the backend at ${API_BASE}. Is uvicorn running?`);
  }
  if (!res.ok) {
    // FastAPI puts the reason in "detail", e.g. "recording is 16.2 s; the limit is 15 s".
    const body = await res.json().catch(() => null);
    const detail = typeof body?.detail === "string" ? body.detail : `HTTP ${res.status}`;
    throw new Error(`The backend couldn't analyze this: ${detail}`);
  }
  return (await res.json()) as AnalyzeResult;
}

// ---------- /articulation (Steps 30-31): how each sound is made ----------
export type ArticulationEntry = {
  kind: "consonant" | "vowel" | "diphthong" | "glide";
  place?: string;
  manner?: string;
  voicing: "voiced" | "voiceless";
  laryngeal: "plain" | "tense" | "aspirated" | null;
  height?: string;
  frontness?: string;
  rounded?: boolean;
  to?: string; // diphthongs: the sound it glides to
  lips: "closed" | "lip_to_teeth" | "rounded" | "spread" | "neutral";
  description: string;
  reviewed: boolean;
  svg: import("./mouth.ts").Svg;
};
export type ArticulationTable = { note: string; sources: string[]; sounds: Record<Lang, Record<string, ArticulationEntry>> };
export const fetchArticulation = () => getJSON<ArticulationTable>("/articulation");

// ---------- /tips (Steps 32-33): what went wrong + how to fix it, per confusion pair ----------
export type Tip = {
  target: string | null; // IPA of the sound we wanted (null: word_not_heard, extra_vowel)
  target_lang: Lang;
  target_label: string;
  produced: string | null; // IPA of what was probably said
  produced_lang: Lang; // can differ from the language learned: ㄹ said as an ENGLISH r
  produced_label: string | null;
  what_happened: string; // has one {word} slot
  tip: string;
  practice: string[];
  reviewed: boolean;
  needs_native_review?: boolean;
};
export type TipsTable = { note: string; tips: Record<Lang, Record<string, Tip>> };
export const fetchTips = () => getJSON<TipsTable>("/tips");

// Both tables, fetched once per page load and shared by every card.
let cardData: Promise<{ tips: TipsTable; articulation: ArticulationTable }> | null = null;
export function loadCardData() {
  cardData ??= Promise.all([fetchTips(), fetchArticulation()]).then(([tips, articulation]) => ({ tips, articulation }));
  cardData.catch(() => (cardData = null)); // a failed fetch can be retried by the next card
  return cardData;
}
// ---------- /tts: native reference audio ----------
// The browser only ever talks to OUR backend; the backend holds the Azure key and the cache.
export type Voice = "female" | "male";
export const SLOW_RATE = -30; // "slower" = 30% slower (backend allows 0 down to -50)

export function ttsUrl(text: string, lang: Lang, opts: { slow?: boolean; voice?: Voice } = {}): string {
  // URLSearchParams encodes & ? # and Korean, so the whole sentence arrives intact.
  const q = new URLSearchParams({
    text,
    lang,
    voice: opts.voice ?? "female",
    rate: String(opts.slow ? SLOW_RATE : 0),
  });
  return `${API_BASE}/tts?${q}`;
}

// Fetch the clip as a Blob (instead of <audio src>) so a 429/503 shows the backend's own message.
export async function fetchTts(text: string, lang: Lang, opts: { slow?: boolean; voice?: Voice } = {}): Promise<Blob> {
  return (await fetchNative(ttsUrl(text, lang, opts))).blob(); // fetchNative: below, shared with the timings
}

// ---------- /tts/timings: when each word / sound happens in the native clip ----------
export type NativePhoneme = { ipa: string; start: number; end: number; conf?: number };
export type NativeWord = { word: string; start: number; end: number; phonemes: NativePhoneme[] };
export type NativeTimings = { version: number; lang: Lang; duration_s: number; words: NativeWord[] };

// Same query as ttsUrl, so the backend times exactly the clip that ttsUrl plays.
export function ttsTimingsUrl(text: string, lang: Lang, opts: { slow?: boolean; voice?: Voice } = {}): string {
  return ttsUrl(text, lang, opts).replace("/tts?", "/tts/timings?");
}

// Shared by the clip and its timings: a 429 / 503 shows the backend's own message ("try again in 12 s").
async function fetchNative(url: string): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(url);
  } catch {
    throw new Error(`Can't reach the backend at ${API_BASE}. Is uvicorn running?`);
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail = typeof body?.detail === "string" ? body.detail : `HTTP ${res.status}`;
    throw new Error(`Couldn't get the native audio: ${detail}`);
  }
  return res;
}

export async function fetchNativeTimings(text: string, lang: Lang, opts: { slow?: boolean; voice?: Voice } = {}) {
  return (await (await fetchNative(ttsTimingsUrl(text, lang, opts))).json()) as NativeTimings;
}

// ---------- /custom: a typed sentence -> the words a native would SAY ----------
// "커피 2잔" -> "커피 두 잔", "Dr. Kim at 3:30" -> "Doctor Kim at three thirty". The reply's `text` is what we
// show, play (TTS) and score (/analyze), so all three agree.
export type CustomText = { text: string; typed: string; changed: boolean };

export function customUrl(text: string, lang: Lang): string {
  return `${API_BASE}/custom?${new URLSearchParams({ text, lang })}`;
}

// What a Custom sentence means (English -> Korean, Korean -> English), from the Claude API.
// `lang` = the language of `text`. The translation is a nice-to-have: any failure gives null, never an error,
// so a missing translation can't stop the learner from practising.
export function translateUrl(text: string, lang: Lang): string {
  return `${API_BASE}/translate?${new URLSearchParams({ text, lang })}`;
}

// English -> Korean: `translation` = 존댓말, `translation_informal` = 반말. Korean -> English: informal is null.
export type Translation = { translation: string; translation_informal: string | null };

export async function fetchTranslation(text: string, lang: Lang): Promise<Translation | null> {
  try {
    const res = await fetch(translateUrl(text, lang));
    if (!res.ok) return null;
    const body = await res.json();
    if (typeof body?.translation !== "string") return null;
    const informal = typeof body.translation_informal === "string" ? body.translation_informal : null;
    return { translation: body.translation, translation_informal: informal };
  } catch {
    return null;
  }
}

export async function fetchCustom(text: string, lang: Lang): Promise<CustomText> {
  let res: Response;
  try {
    res = await fetch(customUrl(text, lang), { cache: "no-store" });
  } catch {
    throw new Error(`Can't reach the backend at ${API_BASE}. Is uvicorn running?`);
  }
  if (!res.ok) {
    // A 400 "detail" is already written for the learner ("Keep it to 80 or fewer..."), so show it as is.
    const body = await res.json().catch(() => null);
    throw new Error(typeof body?.detail === "string" ? body.detail : `Backend answered with HTTP ${res.status}`);
  }
  return (await res.json()) as CustomText;
}
