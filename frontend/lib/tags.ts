// Human names for the target-sound tags in the packs (tag ids come from content/build_dev_pack.py).
export const TAG_LABELS: Record<string, string> = {
  // learning English
  r_as_l: "R",
  l_as_r: "L",
  f_as_p: "F",
  v_as_b: "V",
  th_as_s: "TH (thin)",
  dh_as_d: "TH (this)",
  ih_as_iy: "short i (ship)",
  iy_as_ih: "long ee (sheep)",
  // learning Korean
  eo_vs_o: "ㅓ / ㅗ",
  eu: "ㅡ",
  ae_vs_e: "ㅐ / ㅔ",
  tap_r: "ㄹ tap",
  p_stops: "ㅂ ㅃ ㅍ",
};

export const tagLabel = (tag: string) => TAG_LABELS[tag] ?? tag;
