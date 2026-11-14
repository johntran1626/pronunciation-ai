// Developer-only content (the /dev pages and the dev sentence packs) shows on a local `next dev` server and
// never in the public build. `next build` sets NODE_ENV to "production" and bakes the value into the bundle.

export function showDevContent(nodeEnv: string | undefined): boolean {
  return nodeEnv !== "production";
}

export const SHOW_DEV = showDevContent(process.env.NODE_ENV);

// The dev packs hold test sentences that are not learning content and have no pre-made native audio,
// so the public picker leaves them out. The backend still serves them for tests and evaluation.
export function pickerPacks<T extends { dev_only: boolean }>(packs: T[], showDev: boolean): T[] {
  return showDev ? packs : packs.filter((p) => !p.dev_only);
}
