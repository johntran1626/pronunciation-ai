// The numbers behind the three charts on the Development page. Pure (no React), tested in writeup.test.ts
// (the baseline-vs-app counts are checked against results/listeners.json).
import type { L } from "./development.ts";

export type Count = { k: number; n: number };
export const rate = (c: Count) => (c.n ? c.k / c.n : 0);

/** A percentage with as many decimals as it needs, so 1 in 1,070 doesn't show as "0%". */
export function fmtPct(v: number): string {
  const p = 100 * v;
  if (p === 0) return "0%";
  const d = p < 1 ? 2 : p < 10 ? 1 : 0;
  return `${p.toFixed(d)}%`;
}

const s = (en: string, ko: string): L => ({ en, ko });

// R said as L, the 4 Korean speakers of L2-ARCTIC, human-marked timing: an early look, before tuning on other
// speakers. Flag when the L-like score beats the R-like score by more than the margin.
export const R_MARGIN_SWEEP = {
  title: s("What each margin catches for R said as L, and what it costs", "R을 L로 발음한 경우 마진마다 잡아내는 오류와 그 대가"),
  x: s("Margin (L score − R score)", "마진(L 점수 − R 점수)"),
  y: s("Share of sounds", "소리 비율"),
  caught: s("Real errors caught", "잡아낸 실제 오류"),
  falseAlarms: s("Correct R wrongly flagged", "잘못 표시된 올바른 R"),
  points: [
    { margin: -0.5, caught: { k: 12, n: 14 }, falseAlarms: { k: 241, n: 754 } },
    { margin: -0.25, caught: { k: 12, n: 14 }, falseAlarms: { k: 174, n: 754 } },
    { margin: 0, caught: { k: 10, n: 14 }, falseAlarms: { k: 7, n: 754 } },
    { margin: 0.25, caught: { k: 8, n: 14 }, falseAlarms: { k: 2, n: 754 } },
    { margin: 0.5, caught: { k: 7, n: 14 }, falseAlarms: { k: 1, n: 754 } },
  ],
};

// Correct sounds wrongly flagged on the Korean test speakers, for the four live English checks: the baseline
// (flag anything the recognizer transcribes differently) vs the app's tuned check on the fine-tuned listener.
export const BASELINE_VS_APP = {
  title: s("Correct sounds wrongly marked red", "빨간색으로 잘못 표시된 올바른 소리"),
  baseline: s("Baseline", "기준선"),
  app: s("This app", "이 앱"),
  rows: [
    { pair: "r_as_l", label: s("R said as L", "R을 L로"), app: { k: 1, n: 1070 }, baseline: { k: 127, n: 1070 } },
    { pair: "th_as_s", label: s("TH (think) said as S", "TH(think)를 S로"), app: { k: 0, n: 155 }, baseline: { k: 18, n: 155 } },
    { pair: "ih_as_iy", label: s("ship said as sheep", "ship을 sheep처럼"), app: { k: 6, n: 1401 }, baseline: { k: 102, n: 1401 } },
    { pair: "extra_vowel", label: s("Extra vowel (bus-eu)", "덧붙인 모음(bus-eu)"), app: { k: 9, n: 4151 }, baseline: { k: 60, n: 4151 } },
  ],
};

// Phone error rate on a fixed sample of 800 held-out dev recordings: before training (epoch 0), then after each
// of the 8 epochs. The last epoch was the best and is the checkpoint the app runs.
export const FINETUNE_PER = {
  title: s("Phone error rate on held-out speakers during fine-tuning", "미세 조정 중 학습에 쓰지 않은 화자의 음소 오류율"),
  x: s("Epoch (0 = before training)", "에포크(0 = 학습 전)"),
  y: s("Phone error rate", "음소 오류율"),
  points: [0.2948, 0.168, 0.1559, 0.1542, 0.146, 0.1422, 0.1417, 0.1408, 0.1394].map((per, epoch) => ({ epoch, per })),
};
