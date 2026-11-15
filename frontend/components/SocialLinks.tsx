"use client";
// Two small icon links in the top-left corner: GitHub and LinkedIn. Quiet on purpose (outlined, no text), so they
// don't pull attention from the box. Both open in a new tab.

import type { ReactNode } from "react";
import { useUi } from "@/components/UiLang";
import { GITHUB_URL, LINKEDIN_URL } from "@/lib/home";

function IconLink({ href, label, children }: { href: string; label: string; children: ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" aria-label={label} title={label}
      className="grid size-8 place-items-center rounded-xl border-2 border-ink bg-white text-ink transition hover:-translate-y-px hover:bg-sky hover:shadow-pop-xs lg:size-9">
      {children}
    </a>
  );
}

export default function SocialLinks() {
  const { t } = useUi();
  return (
    <nav className="flex items-center gap-2" data-testid="social">
      <IconLink href={GITHUB_URL} label={t("githubLink")}>
        {/* the GitHub mark */}
        <svg viewBox="0 0 24 24" className="size-[18px] lg:size-5" fill="currentColor" aria-hidden="true">
          <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12" />
        </svg>
      </IconLink>
      {LINKEDIN_URL && (
        <IconLink href={LINKEDIN_URL} label={t("linkedinLink")}>
          {/* "in", drawn as shapes: the dot, the i's stem, and the n */}
          <svg viewBox="0 0 24 24" className="size-[18px] lg:size-5" fill="currentColor" aria-hidden="true">
            <circle cx="5.2" cy="5.2" r="2.3" />
            <rect x="3.2" y="9" width="4" height="12" rx="0.6" />
            <path d="M9.6 9h3.8v1.7c.7-1.2 2.1-2 3.9-2 3 0 4.3 1.9 4.3 5.1V21h-4v-6.4c0-1.6-.6-2.5-1.9-2.5-1.4 0-2.1 1-2.1 2.5V21h-4z" />
          </svg>
        </IconLink>
      )}
    </nav>
  );
}
