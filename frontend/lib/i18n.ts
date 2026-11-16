// The ENG / 한 switch: site text, tips and sound descriptions in English or Korean. It switches the words around
// the app, never the language of the sentence being practised. Pure (no React), tested in i18n.test.ts.
import { MAX_CUSTOM_CHARS } from "./custom.ts";
import { DESC_KO, PHRASE_KO, TIP_KO } from "./i18nKo.ts";

export type Ui = "en" | "ko";
export const DEFAULT_UI: Ui = "en";

const s = (en: string, ko: string) => ({ en, ko });
export const UI = {
  brand: s("Pronunciation coach", "발음 코치"),
  byline: s("by John Tran", "John Tran 제작"),
  mascotLabel: s("Blueberry, the mascot", "마스코트 블루베리"),
  githubLink: s("John Tran on GitHub (opens in a new tab)", "GitHub의 John Tran (새 탭에서 열림)"),
  linkedinLink: s("John Tran on LinkedIn (opens in a new tab)", "LinkedIn의 John Tran (새 탭에서 열림)"),
  typewriterLabel: s("Blueberry in round glasses, typing on a typewriter", "동그란 안경을 쓰고 타자기를 치는 블루베리"),
  typingSoundOn: s("Typing sounds are on. Tap Blueberry to turn them off.", "타자 소리가 켜져 있어요. 블루베리를 누르면 꺼져요."),
  typingSoundOff: s("Typing sounds are off. Tap Blueberry to turn them on.", "타자 소리가 꺼져 있어요. 블루베리를 누르면 켜져요."),
  infoAbout: s("What {name} does", "{name} 설명"),
  autoplayInfo: s("Plays the animation and audio automatically once it loads.", "불러오면 애니메이션과 음성이 바로 재생돼요."),
  placementInfo: s("Highlights the key spot for each sound.", "소리마다 중요한 입 부분을 강조해 보여 줘요."),
  placeholder: s("Type here to get your pronunciation animation", "여기에 입력하면 발음 애니메이션을 보여 드려요"),
  boxLabel: s("Type a sentence in English or Korean", "영어나 한국어 문장을 입력하세요"),
  langEn: s("English", "영어"),
  langKo: s("Korean · 한국어", "한국어"),
  langEither: s("English, Korean, or both", "영어, 한국어, 또는 둘 다"),
  langMix: s("English + Korean", "영어 + 한국어"),
  animate: s("Animate", "애니메이션 보기"),
  loading: s("Loading…", "불러오는 중…"),
  loadingLabel: s("Getting your animation ready", "애니메이션 준비 중"),
  poseNerd: s("Blueberry in glasses, typing on a laptop", "안경 쓴 블루베리가 노트북으로 타자 치는 중"),
  poseDetective: s("Blueberry as a detective with a magnifying glass", "돋보기를 든 탐정 블루베리"),
  posePencil: s("Blueberry writing ㅎㅇ on a notepad with a floating pencil", "블루베리가 떠다니는 연필로 메모장에 ㅎㅇ을 쓰는 중"),
  posePainter: s("Blueberry painting 한들 on an easel, with a palette", "블루베리가 팔레트를 들고 이젤에 한들을 그리는 중"),
  poseReader: s("Blueberry in a monocle, speed-reading a book", "외알 안경을 쓴 블루베리가 책을 빠르게 읽는 중"),
  poseSweeper: s("Blueberry sweeping with a floating broom", "블루베리가 떠다니는 빗자루로 청소하는 중"),
  translating: s("Translating…", "번역 중…"),
  errNoLang: s("Type a sentence in English or Korean.", "영어나 한국어로 문장을 입력하세요."),
  errEmpty: s("Type a sentence first.", "먼저 문장을 입력하세요."),
  errTooLong: s("That's {n} characters. Keep it to {max} or fewer (one short sentence).", "{n}자예요. {max}자 이하로 줄여 주세요(짧은 문장 하나)."),
  numbersNote: s("Numbers and short forms are written out the way they're said.", "숫자와 줄임말은 읽는 대로 풀어 썼어요."),
  youTyped: s("You typed:", "입력한 문장:"),
  practice: s("Practice it yourself!", "직접 연습해 보세요!"),
  animateAnother: s("Animate another", "다른 문장 보기"),
  practiceHint: s("Say the sentence out loud, then see which sounds need work.", "문장을 소리 내어 말하면 어떤 소리를 고쳐야 할지 알려 드려요."),
  practiceHintKo: s(
    "Record yourself. Korean grading is new: so far it checks ㅜ and plain ㅂ ㄷ ㄱ; other sounds stay plain text.",
    "녹음해 보세요. 한국어 채점은 이제 시작이라 지금은 ㅜ와 예사소리 ㅂ ㄷ ㄱ만 확인하고, 다른 소리는 색 없이 보여 드려요.",
  ),
  practiceMixed: s("Practice works for one language at a time. Type the sentence all in English or all in Korean to record it.",
    "연습은 한 번에 한 언어만 돼요. 녹음하려면 문장을 영어로만, 또는 한국어로만 입력해 주세요."),
  autoplay: s("Autoplay", "자동 재생"),
  switchLabel: s("Site language", "사이트 언어"),
  home: s("Home", "홈"),
  // the Development tab and its page
  tabsLabel: s("Pages", "페이지"),
  tabDevelopment: s("Development", "개발 과정"),
  devTitle: s("Development", "개발 과정"),
  onThisPage: s("On this page", "이 페이지 목차"),
  showNumbers: s("Show the numbers", "숫자로 보기"),
  // the native mouth player
  mouthLoading: s("Loading the native mouth…", "원어민 입 모양을 불러오는 중…"),
  tryAgain: s("Try again", "다시 시도"),
  play: s("Play", "재생"),
  pause: s("Pause", "일시정지"),
  replay: s("Replay", "다시 보기"),
  speed: s("Speed", "속도"),
  frame: s("Position in the timeline", "타임라인 위치"),
  noSounds: s("(no sounds)", "(소리 없음)"),
  placementTips: s("Placement tips", "발음 위치 팁"),
  mouthView: s("Mouth view", "입 보기 방향"),
  viewSide: s("Side", "옆"),
  viewFront: s("Front", "앞"),
  soundOn: s("Sound on", "소리 켜기"),
  soundOff: s("Sound off", "소리 끄기"),
  // recording
  record: s("Record", "녹음"),
  recordAgain: s("Record again", "다시 녹음"),
  stop: s("Stop", "멈춤"),
  preparing: s("Preparing audio…", "오디오 준비 중…"),
  analyzing: s("Analyzing…", "분석 중…"),
  recordingStop: s("Recording… Press to STOP", "녹음 중… 누르면 멈춰요"),
  countdownLabel: s("Get ready: recording starts in {n}", "준비하세요: {n}초 뒤 녹음 시작"),
  emptyShort: s("That was too short! Press Practice it yourself and say the whole sentence.", "너무 짧았어요! 직접 연습해 보세요를 누르고 문장 전체를 말해 보세요."),
  emptySilent: s("I couldn't hear any audio. Check your microphone and try again.", "소리가 들리지 않았어요. 마이크를 확인하고 다시 해 보세요."),
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
    "These sounds can't be graded yet.",
    "이 소리들은 아직 채점할 수 없어요.",
  ),
  notHeardTitle: s("This word wasn't heard. Skipped, or said as a different word?", "이 단어가 들리지 않았어요. 건너뛰었거나 다른 단어로 말했나요?"),
  tapWord: s("Tap a word to hear how you said it", "단어를 누르면 내가 말한 소리를 들을 수 있어요"),
  tapSyllable: s("Tap a syllable to hear how you said it", "음절을 누르면 내가 말한 소리를 들을 수 있어요"),
  playYour: s("Play your “{w}”", "내 “{w}” 듣기"),
  tipsError: s("Couldn't load the tips: {e}", "팁을 불러오지 못했어요: {e}"),
  green: s("Green", "초록"),
  greenMeans: s(" = no problem found · ", " = 문제를 찾지 못한 소리 · "),
  red: s("red", "빨강"),
  redMeans: s(" = needs work or not heard. Results are estimated from your audio.", " = 연습이 필요하거나 들리지 않은 소리. 결과는 내 음성으로 추정한 거예요."),
  // detail card
  close: s("Close", "닫기"),
  targetTag: s("TARGET", "목표"),
  yoursTag: s("WHAT YOU SAID", "내가 낸 소리"),
  // cards of the every-sound check (any English sound swapped or left out)
  swapHappened: s("In “{w}”, your [{x}] sounded like [{y}], as in “{ex}”.", "“{w}”에서 [{x}] 소리가 “{ex}”의 [{y}]처럼 들렸어요."),
  swapHappenedPlain: s("In “{w}”, your [{x}] sounded like [{y}].", "“{w}”에서 [{x}] 소리가 [{y}]처럼 들렸어요."),
  missingHappened: s("In “{w}”, the [{x}] sound (as in “{ex}”) seems to be missing.", "“{w}”에서 [{x}] 소리(“{ex}”의 소리)가 빠진 것 같아요."),
  missingHappenedPlain: s("In “{w}”, the [{x}] sound seems to be missing.", "“{w}”에서 [{x}] 소리가 빠진 것 같아요."),
  swapTip: s(
    "Make [{x}] like the green picture: {how}. Say the practice words slowly, then “{w}”.",
    "초록 그림처럼 [{x}] 소리를 내 보세요: {how}. 연습 단어를 천천히 말한 다음 “{w}” 전체를 말해 보세요.",
  ),
  swapTipPlain: s(
    "Make [{x}] like the green picture. Say the practice words slowly, then “{w}”.",
    "초록 그림처럼 [{x}] 소리를 내 보세요. 연습 단어를 천천히 말한 다음 “{w}” 전체를 말해 보세요.",
  ),
  missingTip: s(
    "Don't skip [{x}]: {how}. Say “{w}” slowly so every sound is there, then speed up.",
    "[{x}] 소리를 빼먹지 마세요: {how}. 모든 소리가 들리도록 “{w}” 전체를 천천히 말한 다음 빠르게 말해 보세요.",
  ),
  missingTipPlain: s(
    "Don't skip [{x}]. Say “{w}” slowly so every sound is there, then speed up.",
    "[{x}] 소리를 빼먹지 마세요. 모든 소리가 들리도록 “{w}” 전체를 천천히 말한 다음 빠르게 말해 보세요.",
  ),
  hoverHint: s("Click to see what to fix.", "누르면 고칠 점을 볼 수 있어요."),
  howToFix: s("How to fix it", "고치는 방법"),
  practiceWords: s("Practice words", "연습 단어"),
  compare: s("Compare", "비교해 듣기"),
  yourX: s("▶ Your {x}", "▶ 내 {x}"),
  nativeX: s("▶ Native {x}", "▶ 원어민 {x}"),
  playWord: s("Hear “{w}”", "“{w}” 듣기"),
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

/** The two quick checks on a typed sentence before it goes to the backend (same limits as lib/custom.ts). */
export function problemText(ui: Ui, typed: string): string | null {
  const t = typed.trim();
  if (!t) return tr(ui, "errEmpty");
  if (t.length > MAX_CUSTOM_CHARS) return tr(ui, "errTooLong", { n: t.length, max: MAX_CUSTOM_CHARS });
  return null;
}
