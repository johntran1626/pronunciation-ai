"use client";
// The three charts on the Development page, drawn from lib/devCharts.ts. Line charts are SVG drawn at the measured
// width (so text stays readable on a phone), with a crosshair + tooltip on hover or tap; the bar chart is plain
// HTML bars with the value at each bar's tip. Every chart has a "Show the numbers" table under it.

import { useEffect, useRef, useState, type ReactNode } from "react";
import { useUi } from "@/components/UiLang";
import { BASELINE_VS_APP, FINETUNE_PER, R_MARGIN_SWEEP, fmtPct, rate } from "@/lib/devCharts";
import type { ChartId, L } from "@/lib/development";

const BLUE = "#2F6BFF";
const PINK = "#FF85B8";
const GRID = "#E6E6E6";
const MUTED = "#555555";

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [w, setW] = useState(640);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.round(e.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}

function Legend({ items }: { items: { color: string; label: string }[] }) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-neutral-700">
      {items.map((it) => (
        <span key={it.label} className="flex items-center gap-1.5">
          <span aria-hidden="true" className="inline-block h-2.5 w-4 rounded-sm" style={{ background: it.color }} />
          {it.label}
        </span>
      ))}
    </div>
  );
}

function Numbers({ head, rows }: { head: string[]; rows: (string | number)[][] }) {
  const { t } = useUi();
  return (
    <details className="mt-3 text-sm">
      <summary className="cursor-pointer font-medium text-blue">{t("showNumbers")}</summary>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full border-collapse text-left">
          <thead><tr>{head.map((h) => <th key={h} className="border-b-2 border-ink py-1 pr-4 font-semibold">{h}</th>)}</tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>{r.map((c, j) => <td key={j} className="border-b border-neutral-200 py-1 pr-4 tabular-nums">{c}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

type Series = { label: string; color: string; ys: number[]; tip: (i: number) => string };

function LineChart({ title, xLabel, xs, xFmt, series, yMax, yTicks, yFmt, legend }: {
  title: string; xLabel: string; xs: number[]; xFmt: (x: number) => string; series: Series[];
  yMax: number; yTicks: number[]; yFmt: (y: number) => string; legend: boolean;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const H = width < 500 ? 230 : 270;
  const m = { l: 46, r: 18, t: 12, b: 40 };
  const iw = Math.max(10, width - m.l - m.r);
  const ih = H - m.t - m.b;
  const x0 = xs[0], x1 = xs[xs.length - 1];
  const X = (x: number) => m.l + ((x - x0) / (x1 - x0)) * iw;
  const Y = (y: number) => m.t + ih - (y / yMax) * ih;
  function pick(clientX: number, el: SVGSVGElement) {
    const px = clientX - el.getBoundingClientRect().left;
    let best = 0;
    xs.forEach((x, i) => { if (Math.abs(X(x) - px) < Math.abs(X(xs[best]) - px)) best = i; });
    setHover(best);
  }
  const tipLeft = hover === null ? 0 : Math.min(Math.max(X(xs[hover]) - 90, 0), width - 180);
  return (
    <div>
      <p className="m-0 mb-2 font-semibold">{title}</p>
      {legend && <Legend items={series.map((s) => ({ color: s.color, label: s.label }))} />}
      <div ref={ref} className="relative mt-2">
        <svg width={width} height={H} role="img" aria-label={title} className="block touch-none select-none"
          onPointerMove={(e) => pick(e.clientX, e.currentTarget)} onPointerDown={(e) => pick(e.clientX, e.currentTarget)}
          onPointerLeave={() => setHover(null)}>
          {yTicks.map((y) => (
            <g key={y}>
              <line x1={m.l} x2={m.l + iw} y1={Y(y)} y2={Y(y)} stroke={GRID} strokeWidth={1} />
              <text x={m.l - 8} y={Y(y)} dy="0.32em" textAnchor="end" fontSize={12} fill={MUTED}>{yFmt(y)}</text>
            </g>
          ))}
          {xs.map((x) => (
            <text key={x} x={X(x)} y={m.t + ih + 18} textAnchor="middle" fontSize={12} fill={MUTED}>{xFmt(x)}</text>
          ))}
          <text x={m.l + iw / 2} y={H - 4} textAnchor="middle" fontSize={12} fill={MUTED}>{xLabel}</text>
          {hover !== null && <line x1={X(xs[hover])} x2={X(xs[hover])} y1={m.t} y2={m.t + ih} stroke="#111111" strokeWidth={1} />}
          {series.map((s) => (
            <g key={s.label}>
              <polyline points={xs.map((x, i) => `${X(x)},${Y(s.ys[i])}`).join(" ")} fill="none" stroke={s.color}
                strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
              {xs.map((x, i) => (
                <circle key={x} cx={X(x)} cy={Y(s.ys[i])} r={hover === i ? 5.5 : 4} fill={s.color} stroke="#ffffff" strokeWidth={2} />
              ))}
            </g>
          ))}
        </svg>
        {hover !== null && (
          <div className="pointer-events-none absolute top-0 w-[180px] rounded-xl border-2 border-ink bg-white px-3 py-2 text-xs shadow-pop-xs"
            style={{ left: tipLeft }}>
            <div className="mb-1 font-semibold">{xLabel.split(/\s*\(/)[0]} {xFmt(xs[hover])}</div>
            {series.map((s) => (
              <div key={s.label} className="flex items-start gap-1.5">
                <span aria-hidden="true" className="mt-1 inline-block size-2 shrink-0 rounded-full" style={{ background: s.color }} />
                <span>{series.length > 1 && <span className="block text-neutral-600">{s.label}</span>}{s.tip(hover)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function MarginSweep() {
  const { ui } = useUi();
  const c = R_MARGIN_SWEEP;
  const pts = c.points;
  const tx = (l: L) => l[ui];
  const sign = (m: number) => (m > 0 ? `+${m}` : `${m}`);
  return (
    <>
      <LineChart title={tx(c.title)} xLabel={tx(c.x)} xs={pts.map((p) => p.margin)} xFmt={sign} legend
        yMax={1} yTicks={[0, 0.25, 0.5, 0.75, 1]} yFmt={(y) => `${y * 100}%`}
        series={[
          { label: tx(c.caught), color: BLUE, ys: pts.map((p) => rate(p.caught)), tip: (i) => `${pts[i].caught.k}/${pts[i].caught.n} (${fmtPct(rate(pts[i].caught))})` },
          { label: tx(c.falseAlarms), color: PINK, ys: pts.map((p) => rate(p.falseAlarms)), tip: (i) => `${pts[i].falseAlarms.k}/${pts[i].falseAlarms.n} (${fmtPct(rate(pts[i].falseAlarms))})` },
        ]} />
      <Numbers head={[tx(c.x).split(/\s*\(/)[0], tx(c.caught), tx(c.falseAlarms)]}
        rows={pts.map((p) => [sign(p.margin), `${p.caught.k}/${p.caught.n} (${fmtPct(rate(p.caught))})`, `${p.falseAlarms.k}/${p.falseAlarms.n} (${fmtPct(rate(p.falseAlarms))})`])} />
    </>
  );
}

function FinetuneCurve() {
  const { ui } = useUi();
  const c = FINETUNE_PER;
  const tx = (l: L) => l[ui];
  return (
    <>
      <LineChart title={tx(c.title)} xLabel={tx(c.x)} xs={c.points.map((p) => p.epoch)} xFmt={(x) => `${x}`} legend={false}
        yMax={0.3} yTicks={[0, 0.1, 0.2, 0.3]} yFmt={(y) => y.toFixed(1)}
        series={[{ label: tx(c.y), color: BLUE, ys: c.points.map((p) => p.per), tip: (i) => `${tx(c.y)} ${c.points[i].per.toFixed(3)}` }]} />
      <Numbers head={[tx(c.x).split(/\s*\(/)[0], tx(c.y)]} rows={c.points.map((p) => [p.epoch, p.per.toFixed(4)])} />
    </>
  );
}

function BaselineBars() {
  const { ui } = useUi();
  const c = BASELINE_VS_APP;
  const tx = (l: L) => l[ui];
  const max = 0.15; // the axis runs 0-15%: the largest bar is 12%
  const [hover, setHover] = useState<string | null>(null);
  const bar = (key: string, color: string, v: number, k: number, n: number) => (
    <div className="flex items-center gap-2" onPointerEnter={() => setHover(key)} onPointerLeave={() => setHover(null)}
      onPointerDown={() => setHover(key)}>
      <div className="h-3 rounded-r-[4px]" style={{ width: `${Math.max((v / max) * 78, 0.6)}%`, background: color, opacity: hover && hover !== key ? 0.45 : 1 }} />
      <span className="text-xs whitespace-nowrap tabular-nums text-ink">
        {fmtPct(v)}{hover === key && <span className="text-neutral-600"> ({k.toLocaleString()}/{n.toLocaleString()})</span>}
      </span>
    </div>
  );
  return (
    <>
      <p className="m-0 mb-2 font-semibold">{tx(c.title)}</p>
      <Legend items={[{ color: PINK, label: tx(c.baseline) }, { color: BLUE, label: tx(c.app) }]} />
      <div className="mt-3 flex flex-col gap-3.5">
        {c.rows.map((r) => (
          <div key={r.pair}>
            <div className="mb-1 text-sm font-medium">{tx(r.label)}</div>
            <div className="flex flex-col gap-[2px]">
              {bar(`${r.pair}:b`, PINK, rate(r.baseline), r.baseline.k, r.baseline.n)}
              {bar(`${r.pair}:a`, BLUE, rate(r.app), r.app.k, r.app.n)}
            </div>
          </div>
        ))}
      </div>
      <Numbers head={["", tx(c.baseline), tx(c.app)]}
        rows={c.rows.map((r) => [tx(r.label), `${r.baseline.k.toLocaleString()}/${r.baseline.n.toLocaleString()} (${fmtPct(rate(r.baseline))})`, `${r.app.k}/${r.app.n.toLocaleString()} (${fmtPct(rate(r.app))})`])} />
    </>
  );
}

const CHARTS: Record<ChartId, () => ReactNode> = {
  rMarginSweep: MarginSweep,
  finetunePer: FinetuneCurve,
  baselineVsApp: BaselineBars,
};

export default function DevChart({ chart }: { chart: ChartId }) {
  const C = CHARTS[chart];
  return <C />;
}
