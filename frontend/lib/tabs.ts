// The text tab in the header (beside Home). Pure (no React), tested in writeup.test.ts.
import type { Key } from "./i18n.ts";

export const TABS: { href: string; label: Key }[] = [
  { href: "/development", label: "tabDevelopment" },
];

/** The tab whose page is open (a trailing slash is ignored), or null on any other page. */
export function activeTab(pathname: string): string | null {
  const path = pathname.replace(/\/+$/, "") || "/";
  return TABS.find((t) => t.href === path)?.href ?? null;
}
