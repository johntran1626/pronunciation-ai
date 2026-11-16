"use client";
// The Development page behind the header tab: the long write-up (contents list, sections, figures and charts).
// Text comes from lib/development.ts in the chosen site language.

import Image from "next/image";
import { Fragment, type ReactNode } from "react";
import DevChart from "@/components/DevChart";
import SiteHeader from "@/components/SiteHeader";
import { UiLangProvider, useUi } from "@/components/UiLang";
import { SECTIONS, type Block } from "@/lib/development";

/** `**bold**` and `*italic*` inside a paragraph. */
function Rich({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g);
  return (
    <>
      {parts.map((p, i) =>
        p.startsWith("**") ? <strong key={i} className="font-semibold">{p.slice(2, -2)}</strong>
          : p.startsWith("*") && p.length > 2 ? <em key={i}>{p.slice(1, -1)}</em>
            : <Fragment key={i}>{p}</Fragment>)}
    </>
  );
}

function Shell({ children }: { children: ReactNode }) {
  return (
    <UiLangProvider>
      <main className="flex min-h-dvh w-full flex-col px-4 pt-5 pb-16 sm:px-[22px] lg:px-10 lg:pt-7">
        <SiteHeader />
        {children}
      </main>
    </UiLangProvider>
  );
}

function BlockView({ b }: { b: Block }) {
  const { ui } = useUi();
  if (b.kind === "p") return <p className="my-4 text-[17px] leading-[1.75] text-[#222222]"><Rich text={b.text[ui]} /></p>;
  if (b.kind === "list") {
    return (
      <ul className="my-4 flex list-disc flex-col gap-2 pl-6 text-[17px] leading-[1.7] text-[#222222] marker:text-blue">
        {b.items.map((it, i) => <li key={i}><Rich text={it[ui]} /></li>)}
      </ul>
    );
  }
  const card = "my-7 rounded-2xl border-[2.5px] border-ink bg-white p-3 shadow-pop-sm sm:p-4";
  if (b.kind === "figure") {
    return (
      <figure className={`${card} xl:mr-[-140px]`}>
        <a href={b.src} target="_blank" rel="noopener noreferrer" className="block">
          <Image src={b.src} width={b.width} height={b.height} alt={b.alt[ui]} sizes="(min-width: 1024px) 860px, 100vw"
            className="h-auto w-full rounded-lg" />
        </a>
        <figcaption className="mt-3 text-sm leading-[1.6] text-neutral-700">{b.caption[ui]}</figcaption>
      </figure>
    );
  }
  return (
    <figure className={card}>
      <DevChart chart={b.chart} />
      <figcaption className="mt-3 text-sm leading-[1.6] text-neutral-700">{b.caption[ui]}</figcaption>
    </figure>
  );
}

function Development() {
  const { ui, t } = useUi();
  return (
    <div className="mx-auto mt-8 flex w-full max-w-[1160px] gap-12 lg:mt-12">
      {/* desktop: a contents list that stays in view while reading */}
      <nav aria-label={t("onThisPage")} className="sticky top-6 hidden h-fit w-[220px] shrink-0 break-keep lg:block">
        <p className="m-0 mb-2 font-display text-lg">{t("onThisPage")}</p>
        <ol className="m-0 flex list-none flex-col gap-1.5 p-0 text-sm">
          {SECTIONS.map((s) => (
            <li key={s.id}><a href={`#${s.id}`} className="text-neutral-700 hover:text-blue hover:underline">{s.heading[ui]}</a></li>
          ))}
        </ol>
      </nav>
      <article className="min-w-0 max-w-[720px] flex-1 break-keep" lang={ui}>
        <h1 className="m-0 font-display text-[34px] leading-[1.1] font-normal lg:text-[48px]">{t("devTitle")}</h1>
        {/* phone: the contents list folds away at the top */}
        <details className="mt-6 rounded-2xl border-[2.5px] border-ink bg-tray px-4 py-3 lg:hidden">
          <summary className="cursor-pointer font-display text-lg">{t("onThisPage")}</summary>
          <ol className="mt-2 mb-1 flex flex-col gap-1.5 pl-5 text-[15px]">
            {SECTIONS.map((s) => <li key={s.id}><a href={`#${s.id}`} className="text-ink underline-offset-2 hover:underline">{s.heading[ui]}</a></li>)}
          </ol>
        </details>
        {SECTIONS.map((s) => (
          <section key={s.id} id={s.id} className="mt-12 scroll-mt-6">
            <h2 className="m-0 font-display text-[26px] leading-[1.2] font-normal lg:text-[30px]">{s.heading[ui]}</h2>
            {s.blocks.map((b, i) => <BlockView key={i} b={b} />)}
          </section>
        ))}
      </article>
    </div>
  );
}

export const DevelopmentPage = () => <Shell><Development /></Shell>;
