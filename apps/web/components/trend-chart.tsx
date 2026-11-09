"use client";

import { useState } from "react";
import type { ChartPoint } from "@/lib/benchmark";

type Series = { name: string; color: string };

type Props = {
  title: string;
  points: ChartPoint[];
  series: Series[];
  /** A name, not a function: server components can't pass functions to client components. */
  format: "percent" | "usd";
  /** Fixed top of the y scale (1 for percentages); otherwise fit to the data. */
  max?: number;
};

const WIDTH = 640;
const HEIGHT = 220;
const PAD = { top: 16, right: 72, bottom: 28, left: 44 };

/**
 * A small line chart in plain SVG: one y axis, 2px lines, 8px markers, a legend plus direct
 * labels at the last point, and a hover crosshair with a tooltip.
 */
const FORMATS = {
  percent: (value: number) => `${Math.round(value * 100)}%`,
  // Runs often cost cents: show three decimals below $1 so axis ticks don't all read "$0.01".
  usd: (value: number) => `$${value.toFixed(value < 1 ? 3 : 2)}`,
};

export function TrendChart({ title, points, series, format: formatName, max }: Props) {
  const format = FORMATS[formatName];
  const [hover, setHover] = useState<number | null>(null);
  const top = max ?? Math.max(...points.flatMap((p) => p.values), 0.01) * 1.15;
  const innerW = WIDTH - PAD.left - PAD.right;
  const innerH = HEIGHT - PAD.top - PAD.bottom;
  const x = (i: number) => PAD.left + (points.length === 1 ? innerW / 2 : (i / (points.length - 1)) * innerW);
  const y = (v: number) => PAD.top + innerH - (v / top) * innerH;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => t * top);
  const last = points.length - 1;

  const onMove = (event: React.MouseEvent<SVGSVGElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const px = ((event.clientX - box.left) / box.width) * WIDTH;
    let nearest = 0;
    points.forEach((_, i) => {
      if (Math.abs(x(i) - px) < Math.abs(x(nearest) - px)) nearest = i;
    });
    setHover(nearest);
  };

  return (
    <figure className="grid gap-3 rounded-xl border p-4">
      <figcaption className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-medium">{title}</span>
        {series.length > 1 && (
          <span className="flex gap-4 text-sm text-muted-foreground">
            {series.map((s) => (
              <span key={s.name} className="flex items-center gap-1.5">
                <span className="size-2.5 rounded-full" style={{ background: s.color }} aria-hidden />
                {s.name}
              </span>
            ))}
          </span>
        )}
      </figcaption>
      <div className="relative">
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="w-full overflow-visible"
          role="img"
          aria-label={`${title}: ${points.map((p) => `${p.label} ${p.values.map(format).join(" / ")}`).join(", ")}`}
          onMouseMove={onMove}
          onMouseLeave={() => setHover(null)}
        >
          {ticks.map((tick) => (
            <g key={tick}>
              <line x1={PAD.left} x2={WIDTH - PAD.right} y1={y(tick)} y2={y(tick)} className="stroke-border" strokeWidth={1} />
              <text x={PAD.left - 8} y={y(tick)} dy="0.32em" textAnchor="end" className="fill-muted-foreground text-[11px]">
                {format(tick)}
              </text>
            </g>
          ))}
          {points.map((point, i) => (
            <text key={i} x={x(i)} y={HEIGHT - 8} textAnchor="middle" className="fill-muted-foreground font-mono text-[10px]">
              {point.label}
            </text>
          ))}
          {hover !== null && (
            <line x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={PAD.top + innerH} className="stroke-muted-foreground" strokeDasharray="3 3" />
          )}
          {series.map((s, si) => (
            <g key={s.name}>
              {points.length > 1 && (
                <polyline
                  fill="none"
                  stroke={s.color}
                  strokeWidth={2}
                  strokeLinejoin="round"
                  strokeLinecap="round"
                  points={points.map((p, i) => `${x(i)},${y(p.values[si])}`).join(" ")}
                />
              )}
              {points.map((p, i) => (
                <circle key={i} cx={x(i)} cy={y(p.values[si])} r={4} fill={s.color} className="stroke-background" strokeWidth={2} />
              ))}
              {last >= 0 && (
                <text x={x(last) + 10} y={y(points[last].values[si])} dy="0.32em" className="fill-foreground text-[11px] font-medium">
                  {series.length > 1 ? `${s.name} ${format(points[last].values[si])}` : format(points[last].values[si])}
                </text>
              )}
            </g>
          ))}
        </svg>
        {hover !== null && (
          <div
            className="pointer-events-none absolute top-0 rounded-md border bg-popover px-2.5 py-1.5 text-xs text-popover-foreground shadow-sm"
            style={{ left: `${(x(hover) / WIDTH) * 100}%`, transform: hover > last / 2 ? "translateX(-105%)" : "translateX(5%)" }}
          >
            <p className="font-mono">{points[hover].label}</p>
            <p className="text-muted-foreground">{new Date(points[hover].date).toLocaleString()}</p>
            {series.map((s, si) => (
              <p key={s.name} className="flex items-center gap-1.5">
                <span className="size-2 rounded-full" style={{ background: s.color }} aria-hidden />
                {s.name}: <span className="font-medium tabular-nums">{format(points[hover].values[si])}</span>
              </p>
            ))}
          </div>
        )}
      </div>
    </figure>
  );
}
