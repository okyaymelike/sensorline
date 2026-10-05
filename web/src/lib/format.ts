import type { Status } from "../api";

export function fmtValue(v: number | null, unit: string | null): string {
  if (v === null) return "—";
  const n = v >= 1000 ? Math.round(v).toLocaleString() : Number(v.toFixed(2)).toString();
  return unit ? `${n} ${unit}` : n;
}

export function ago(stalenessS: number | null, liveWord: string): string {
  if (stalenessS === null) return "—";
  const s = Math.max(0, Math.round(stalenessS));
  if (s <= 1) return liveWord;
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const r = s % 60;
  return r ? `${m}m${r}s` : `${m}m`;
}

export const STATUS_RANK: Record<Status, number> = { offline: 3, stale: 2, online: 1 };

// sparkline path over a value array (nulls break the line)
export function sparkPath(values: number[], w = 84, h = 28, pad = 3): string[] {
  const nums = values.filter((v) => Number.isFinite(v));
  if (!nums.length) return [];
  const mn = Math.min(...nums);
  const mx = Math.max(...nums);
  const rng = mx - mn || 1;
  const segs: string[] = [];
  let cur = "";
  values.forEach((v, i) => {
    if (!Number.isFinite(v)) {
      if (cur) segs.push(cur);
      cur = "";
      return;
    }
    const x = pad + (i / Math.max(1, values.length - 1)) * (w - pad * 2);
    const y = h - pad - ((v - mn) / rng) * (h - pad * 2);
    cur += (cur ? " L" : "M") + x.toFixed(1) + " " + y.toFixed(1);
  });
  if (cur) segs.push(cur);
  return segs;
}
