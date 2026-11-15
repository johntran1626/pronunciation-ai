// The ENG / 한 switch: site text, tips and sound descriptions in English or Korean. It switches the words around
// the app, never the language of the sentence being practised. Pure (no React), tested in i18n.test.ts.
import { MAX_CUSTOM_CHARS } from "./custom.ts";
import { CHECK_KO, DESC_KO, PHRASE_KO, TIP_KO } from "./i18nKo.ts";
import { describeChecks } from "./results.ts";

export type Ui = "en" | "ko";
export const DEFAULT_UI: Ui = "en";

const s = (en: string, ko: string) => ({ en, ko });
export const UI = {
  brand: s("Pronunciation coach", "발음 코치"),
  placeholder: s("Type here to get your pronunciation animation", "여기에 입력하면 발음 애니메이션을 보여 드려요"),
  boxLabel: s("Type a sentence in English or Korean", "영어나 한국어 문장을 입력하세요"),
  langEn: s("English", "영어"),
  langKo: s("Korean · 한국어", "한국어"),
  langEither: s("English or Korean", "영어 또는 한국어"),
  langMix: s("English + Korean", "영어 + 한국어"),
  animate: s("Animate →", "애니메이션 보기 →"),
  loading: s("Loading…", "불러오는 중…"),
  translating: s("Translating…", "번역 중…"),
  errNoLang: s("Type a sentence in English or Korean.", "영어나 한국어로 문장을 입력하세요."),
  errEmpty: s("Type a sentence first.", "먼저 문장을 입력하세요."),
  errTooLong: s("That's {n} characters. Keep it to {max} or fewer (one short sentence).", "{n}자예요. {max}자 이하로 줄여 주세요(짧은 문장 하나)."),
  numbersNote: s("Numbers and short forms are written out the way they're said.", "숫자와 줄임말은 읽는 대로 풀어 썼어요."),
  youTyped: s("You typed:", "입력한 문장:"),
  practice: s("Practice it yourself", "직접 연습하기"),
  practiceHint: s("Record yourself and see which sounds need work.", "녹음하면 어떤 소리를 더 연습해야 하는지 보여 드려요."),
  practiceHintUngraded: s(
    "Korean grading isn't ready yet: you can record yourself and replay each syllable, but nothing will be marked green or red.",
    "한국어 채점은 아직 준비 중이에요. 녹음하고 음절마다 다시 들을 수는 있지만, 초록색이나 빨간색 표시는 없어요.",
  ),
  practiceMixed: s("Practice works for one language at a time. Type the sentence all in English or all in Korean to record it.",
    "연습은 한 번에 한 언어만 돼요. 녹음하려면 문장을 영어로만, 또는 한국어로만 입력해 주세요."),
  autoplay: s("Autoplay", "자동 재생"),
  switchLabel: s("Site language", "사이트 언어"),
  // the native mouth player
  mouthLoading: s("Loading the native mouth…", "원어민 입 모양을 불러오는 중…"),
  tryAgain: s("Try again", "다시 시도"),
  play: s("Play", "재생"),
  pause: s("Pause", "일시정지"),
  replay: s("Replay", "다시 보기"),
  noSounds: s("(no sounds)", "(소리 없음)"),
  placementTips: s("Placement tips", "발음 위치 팁"),
  soundOn: s("Sound on", "소리 켜기"),
  soundOff: s("Sound off", "소리 끄기"),
  // recording
  record: s("Record", "녹음"),
  recordAgain: s("Record again", "다시 녹음"),
  stop: s("Stop", "멈춤"),
  preparing: s("Preparing audio…", "오디오 준비 중…"),
  analyzing: s("Analyzing…", "분석 중…"),
  micDenied: s("Microphone permission was denied. Allow it (icon in the address bar) and try again.", "마이크 권한이 거부되었어요. 주소창의 아이콘에서 허용한 뒤 다시 해 보세요."),
  micMissing: s("No microphone found. Plug one in or check System Settings → Sound → Input.", "마이크를 찾을 수 없어요. 마이크를 연결하거나 시스템 설정 → 사운드 → 입력을 확인하세요."),
  cantRecord: s("This browser can't record here. Open the page in Chrome or Safari.", "이 브라우저에서는 녹음할 수 없어요. Chrome이나 Safari에서 열어 주세요."),
  // results
  noSpeech: s("We couldn't hear any speech. Check that the right microphone is selected, then try again.", "말소리가 들리지 않았어요. 올바른 마이크가 선택되어 있는지 확인하고 다시 해 보세요."),
  mismatch: s("This didn't sound like the sentence. Try reading it again, word for word.", "문장과 다르게 들렸어요. 한 단어씩 다시 읽어 보세요."),
  estimated: s("(Estimated from your audio.)", "(내 음성으로 추정한 결과예요.)"),
  headlineOne: s("{red} of {words} words has something to work on{nh}.", "{words}개 단어 중 {red}개에 연습할 부분이 있어요{nh}."),
  headlineMany: s("{red} of {words} words have something to work on{nh}.", "{words}개 단어 중 {red}개에 연습할 부분이 있어요{nh}."),
  notHeardCount: s(" ({n} not heard)", " ({n}개는 들리지 않았어요)"),
  noProblems: s("No problems found in what we checked.", "확인한 부분에서는 문제가 없어요."),
  heardAll: s("We heard every word. None of these sounds can be checked yet.", "모든 단어가 들렸어요. 이 소리들은 아직 확인할 수 없어요."),
  nothingGraded: s(
    "These sounds can't be graded yet, so nothing is marked green or red.",
    "이 소리들은 아직 채점할 수 없어서 초록색이나 빨간색으로 표시하지 않았어요.",
  ),
  notHeardTitle: s("This word wasn't heard. Skipped, or said as a different word?", "이 단어가 들리지 않았어요. 건너뛰었거나 다른 단어로 말했나요?"),
  tapWord: s("Tap a word to hear how you said it", "단어를 누르면 내가 말한 소리를 들을 수 있어요"),
  tapSyllable: s("Tap a syllable to hear how you said it", "음절을 누르면 내가 말한 소리를 들을 수 있어요"),
  tapRed: s(". Tap a red one to see what to fix (its card has the replay buttons).", ". 빨간 부분을 누르면 고칠 점을 볼 수 있어요(카드에 다시 듣기 버튼이 있어요)."),
  showFix: s("Show what to fix in “{w}”", "“{w}”에서 고칠 점 보기"),
  playYour: s("Play your “{w}”", "내 “{w}” 듣기"),
  tipsError: s("Couldn't load the tips: {e}", "팁을 불러오지 못했어요: {e}"),
  green: s("Green", "초록"),
  greenMeans: s(" = this sound passed a check · ", " = 확인을 통과한 소리 · "),
  red: s("red", "빨강"),
  redMeans: s(" = needs work or not heard. Results are estimated from your audio.", " = 연습이 필요하거나 들리지 않은 소리. 결과는 내 음성으로 추정한 거예요."),
  // detail card
  cardEstimated: s("Estimated from your audio. The app can't see your mouth.", "내 음성으로 추정한 결과예요. 앱은 입 안을 볼 수 없어요."),
  close: s("Close", "닫기"),
  targetIs: s("Target: {x}", "목표: {x}"),
  yoursIs: s("What you probably did: {x}", "아마 이렇게 했어요: {x}"),
  drawings: s(
    "Drawings show the textbook position (based on public-domain diagrams by R. Wright & D. McCloy), not your mouth.",
    "그림은 교과서적인 위치예요(R. Wright & D. McCloy의 퍼블릭 도메인 도식 기반). 내 입 모양이 아니에요.",
  ),
  seeReal: s("See a real mouth:", "실제 입 안 보기:"),
  mriLink: s("MRI on Seeing Speech (Univ. of Glasgow)", "Seeing Speech의 MRI 영상(글래스고 대학교)"),
  thenTap: s(", then tap [{x}]", ", 그다음 [{x}] 누르기"),
  howToFix: s("How to fix it", "고치는 방법"),
  practiceWords: s("Practice words", "연습 단어"),
  compare: s("Compare", "비교해 듣기"),
  yourX: s("▶ Your {x}", "▶ 내 {x}"),
  nativeX: s("▶ Native {x}", "▶ 원어민 {x}"),
  nativeLoading: s("▶ Native: loading…", "▶ 원어민: 불러오는 중…"),
  nativeNote: s(
    "Native = computer voice (Azure), cut at the times our aligner found (edges can be a little off).",
    "원어민 = 컴퓨터 음성(Azure)이고, 정렬기가 찾은 시간에 맞춰 잘랐어요(경계가 조금 어긋날 수 있어요).",
  ),
  draftTip: s(" Draft tip, not reviewed yet.", " 초안 팁이에요. 아직 검토 전이에요."),
  needsNative: s(" Not yet checked by a native Korean speaker.", " 아직 한국어 원어민이 확인하지 않았어요."),
  // footer
} as const;
export type Key = keyof typeof UI;

/** A site string in the chosen language, with its {slots} filled in. */
export function tr(ui: Ui, key: Key, vars: Record<string, string | number> = {}): string {
  return UI[key][ui].replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m));
}

/** A translator for the short English phrases in the mouth pictures (unknown phrases stay English). */
export const say = (ui: Ui) => (english: string) => (ui === "ko" ? PHRASE_KO[english] ?? english : english);

type TipFields = { target_label: string; produced_label: string | null; what_happened: string; tip: string };
/** A tip's words in the chosen language. English = exactly what tips.json says. */
export function tipText<T extends TipFields>(ui: Ui, lang: "en" | "ko", id: string, t: T): T {
  const k = ui === "ko" ? TIP_KO[lang]?.[id] : undefined;
  return k ? { ...t, ...k } : t;
}

/** A sound's plain-words description in the chosen language. */
export const descText = (ui: Ui, lang: "en" | "ko", ipa: string, english: string) =>
  (ui === "ko" ? DESC_KO[lang]?.[ipa] : undefined) ?? english;

/** The honesty line under a result: which checks this version runs. */
export function describeChecksIn(ui: Ui, checks: string[]): string {
  if (ui === "en") return describeChecks(checks);
  if (checks.length === 0) return "아직 켜진 확인 항목이 없어서 채점하지 않았어요.";
  return `이 버전이 확인하는 것: ${checks.map((c) => CHECK_KO[c] ?? c).join(", ")}. 일반 글자 = 아직 확인하지 않는 부분.`;
}

/** The two quick checks on a typed sentence before it goes to the backend (same limits as lib/custom.ts). */
export function problemText(ui: Ui, typed: string): string | null {
  const t = typed.trim();
  if (!t) return tr(ui, "errEmpty");
  if (t.length > MAX_CUSTOM_CHARS) return tr(ui, "errTooLong", { n: t.length, max: MAX_CUSTOM_CHARS });
  return null;
}
