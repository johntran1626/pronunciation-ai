"use client";

import { useEffect, useState } from "react";
import { useUi } from "@/components/UiLang";
import { API_BASE, checkHealth } from "@/lib/api";

// The three things the status line can be.
type Status = { kind: "checking" } | { kind: "connected" } | { kind: "error"; message: string };

// A small "is the backend up?" line, shown at the bottom of the page.
export default function BackendStatus() {
  const { t } = useUi();
  const [status, setStatus] = useState<Status>({ kind: "checking" });
  const [attempt, setAttempt] = useState(0); // bumping this re-runs the check

  useEffect(() => {
    let ignore = false; // set when the page closes or a newer check starts, so a late reply is dropped
    checkHealth().then(
      (health) => {
        if (!ignore) setStatus(health.ok ? { kind: "connected" } : { kind: "error", message: "Backend said ok: false" });
      },
      (e: Error) => {
        if (!ignore) setStatus({ kind: "error", message: e.message });
      },
    );
    return () => {
      ignore = true;
    };
  }, [attempt]);

  const dot = status.kind === "connected" ? "bg-green-600" : status.kind === "error" ? "bg-red-600" : "bg-neutral-400";

  return (
    <p className="flex flex-wrap items-center gap-2 text-sm text-neutral-500">
      <span aria-hidden className={`inline-block h-2.5 w-2.5 rounded-full ${dot}`} />
      {status.kind === "checking" && t("backendChecking")}
      {status.kind === "connected" && t("backendConnected", { url: API_BASE })}
      {status.kind === "error" && t("backendDown", { msg: status.message })}
      <button
        onClick={() => {
          setStatus({ kind: "checking" });
          setAttempt((n) => n + 1);
        }}
        className="underline hover:text-neutral-800 dark:hover:text-neutral-200"
      >
        {t("checkAgain")}
      </button>
    </p>
  );
}
