// Developer-only content (the /dev pages and the debug panel) shows on a local `next dev` server and
// never in the public build. `next build` sets NODE_ENV to "production" and bakes the value into the bundle.

export function showDevContent(nodeEnv: string | undefined): boolean {
  return nodeEnv !== "production";
}

export const SHOW_DEV = showDevContent(process.env.NODE_ENV);
