// Turning an /analyze result into what the screen shows. Pure functions, tested in results.test.ts.
import type { AnalyzeResult, DisplayPiece } from "./api.ts";
import { decompose, type JamoPart } from "./hangul.ts";

// For a RED Korean block: its letters, each marked red or not. null = nothing to break down
// (a green piece, or not a Hangul block, e.g. English letters).
export function jamoParts(piece: DisplayPiece): (JamoPart & { red: boolean })[] | null {
  if (piece.status !== "red") return null;
  const parts = decompose(piece.text);
  if (!parts) return null;
  return parts.map((p) => ({
    ...p,
    // Prefer the slot (onset/vowel/coda): 각 has ㄱ twice. Fall back to the letter if there are no slots.
    red: piece.red_slots ? piece.red_slots.includes(p.slot) : (piece.red_jamo ?? []).includes(p.jamo),
  }));
}

export function summarize(result: AnalyzeResult): { words: number; red: number } {
  return { words: result.words.length, red: result.words.filter((w) => w.status === "red").length };
}

// How a checked sound looks. Red = colour AND a straight underline, so it still reads for colour-blind users.
export const RED_STYLE = "text-red-600 underline decoration-2 underline-offset-[5px]";
export const GREEN_STYLE = "text-green-700";

// Every piece of a practice result is green or red, never plain: a sound with nothing found wrong
// ("unchecked" from the backend) shows green, so the sentence never mixes in confusing black letters.
export function pieceStyle(status: DisplayPiece["status"]): string {
  return status === "red" ? RED_STYLE : GREEN_STYLE;
}
