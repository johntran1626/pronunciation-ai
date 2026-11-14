// Custom mode helpers (no React here, so node --test can check them).
import type { CustomText } from "./api.ts";

// Same limit as backend/custom.py MAX_CHARS: about what fits in the 15 s recording limit.
// The backend is the real judge; this only saves a round trip for the two obvious cases.
export const MAX_CUSTOM_CHARS = 80;

export function typedProblem(typed: string): string | null {
  const t = typed.trim();
  if (!t) return "Type a sentence first.";
  if (t.length > MAX_CUSTOM_CHARS)
    return `That's ${t.length} characters. Keep it to ${MAX_CUSTOM_CHARS} or fewer (one short sentence).`;
  return null;
}

// What we show above the recorder: the sentence we'll actually score, and why it may look different.
export function checkLine(r: CustomText): { text: string; note: string | null } {
  return {
    text: r.text,
    note: r.changed ? "Numbers and short forms are written out the way they're said." : null,
  };
}
