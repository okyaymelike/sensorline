import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, type DeviceAnomaly } from "../api";
import { useLang } from "../lib/i18n";

interface Props {
  deviceId: string | null;
  refreshMs: number | false;
}

const RANGES = [
  { label: "1m", limit: 30 },
  { label: "2m", limit: 60 },
  { label: "4m", limit: 120 },
];

function sevColor(sev: string): string {
  if (sev === "critical") return "var(--crit)";
  if (sev === "warn") return "var(--warn)";
  return "var(--info)";
}
const hhmmss = (t: number) =>
  new Date(t).toLocaleTimeString([], { hour12: false });

export function Investigate({ deviceId, refreshMs }: Props) {
  const { t, kindLabel } = useLang();
  const { data: fleet = [] } = useQuery({ queryKey: ["fleet"], queryFn: api.fleet, refetchInterval: refreshMs });

  const [dev, setDev] = useState<string | null>(deviceId);
  const [limit, setLimit] = useState(60);
  const [readingId, setReadingId] = useState<number | null>(null);

  useEffect(() => {
    if (deviceId) setDev(deviceId);
  }, [deviceId]);
  useEffect(() => {
    if (!dev && fleet.length) setDev(fleet[0].external_id);
  }, [dev, fleet]);

  const meta = fleet.find((d) => d.external_id === dev);

  const { data: series } = useQuery({
    queryKey: ["series", dev, limit],
    queryFn: () => api.series(dev!, undefined, limit),
    enabled: !!dev,
    refetchInterval: refreshMs,
  });
  const { data: anomalies = [] } = useQuery({
    queryKey: ["devanom", dev],
    queryFn: () => api.deviceAnomalies(dev!),
    enabled: !!dev,
    refetchInterval: refreshMs,
  });

  const points = series?.points ?? [];
  const chartData = useMemo(() => {
    const vals = points.map((p) => p.value);
    if (!vals.length) return [];
    const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
    const sd = Math.sqrt(vals.reduce((a, b) => a + (b - mean) ** 2, 0) / vals.length);
    const band = Math.max(sd * 1.5, Math.abs(mean) * 0.01 + 0.2);
    return points.map((p) => {
      const base = p.rolling_mean_10;
      return {
        t: Date.parse(p.sampled_at),
        value: p.value,
        band: base != null ? [base - band, base + band] : null,
      };
    });
  }, [points]);

  const flagged = anomalies.filter((a) => a.reading_id != null);
  const markers = anomalies.filter((a) => a.reading_sampled_at && a.reading_value != null);

  // default-select the most recent flagged reading
  useEffect(() => {
    if (readingId == null && flagged.length) setReadingId(flagged[0].reading_id);
  }, [readingId, flagged]);
  useEffect(() => {
    setReadingId(null);
  }, [dev]);

  return (
    <>
      <div className="inv-head">
        <span className="did">{dev ?? "—"}</span>
        <select value={dev ?? ""} onChange={(e) => setDev(e.target.value)}>
          {fleet.map((d) => (
            <option key={d.external_id} value={d.external_id}>
              {d.external_id} · {d.location ?? "—"}
            </option>
          ))}
        </select>
        <div className="seg" role="group" aria-label="Range" style={{ marginLeft: "auto" }}>
          {RANGES.map((r) => (
            <button key={r.limit} type="button" aria-pressed={limit === r.limit} onClick={() => setLimit(r.limit)}>
              {r.label}
            </button>
          ))}
        </div>
      </div>
      <div className="inv-sub">
        {meta && <span className="tag">{kindLabel(meta.kind)}</span>}
        {meta?.location} {meta?.metric ? `· ${meta.metric}` : ""}
        {meta?.unit ? <> &nbsp;·&nbsp; <span className="mono">{meta.unit}</span></> : null}
      </div>

      <div className="inv-grid">
        <div className="panel chart-card">
          <div className="chart-legend">
            <span className="lg"><i style={{ background: "var(--accent)" }} />{t("leg_reading")}</span>
            <span className="lg"><i className="band" style={{ background: "var(--accent)" }} />{t("leg_baseline")}</span>
            <span className="lg"><span className="mk" style={{ background: "var(--warn)" }} />{t("leg_warn")}</span>
            <span className="lg"><span className="mk" style={{ background: "var(--crit)" }} />{t("leg_crit")}</span>
          </div>
          <div className="chart-box">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartData} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
                <CartesianGrid stroke="var(--border)" vertical={false} />
                <XAxis
                  dataKey="t"
                  type="number"
                  domain={["dataMin", "dataMax"]}
                  tickFormatter={hhmmss}
                  tick={{ fill: "var(--muted)", fontSize: 11 }}
                  stroke="var(--border)"
                  minTickGap={48}
                />
                <YAxis
                  domain={["auto", "auto"]}
                  tick={{ fill: "var(--muted)", fontSize: 11 }}
                  stroke="var(--border)"
                  width={46}
                  unit={meta?.unit ? ` ${meta.unit}` : ""}
                />
                <Tooltip
                  labelFormatter={(v) => hhmmss(Number(v))}
                  contentStyle={{ fontFamily: "var(--font-mono)", fontSize: 12, borderRadius: 10, border: "1px solid var(--border)" }}
                />
                <Area dataKey="band" stroke="none" fill="var(--accent)" fillOpacity={0.14} isAnimationActive={false} connectNulls={false} />
                <Line dataKey="value" stroke="var(--accent)" strokeWidth={2} dot={false} isAnimationActive={false} connectNulls={false} />
                {markers.map((a) => (
                  <ReferenceDot
                    key={a.id}
                    x={Date.parse(a.reading_sampled_at!)}
                    y={a.reading_value!}
                    r={6}
                    fill={sevColor(a.severity)}
                    stroke="#fff"
                    strokeWidth={1.5}
                  />
                ))}
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <p className="note">
            {flagged.length
              ? `${flagged.length} flagged reading(s) on this device.`
              : `${dev ?? "device"} is healthy across this window.`}
          </p>
        </div>

        <div className="panel" style={{ padding: 16 }}>
          <Genealogy readingId={readingId} flagged={flagged} onSelect={setReadingId} />
        </div>
      </div>
    </>
  );
}

function Genealogy({
  readingId,
  flagged,
  onSelect,
}: {
  readingId: number | null;
  flagged: DeviceAnomaly[];
  onSelect: (id: number) => void;
}) {
  const { t } = useLang();
  const { data: rows = [] } = useQuery({
    queryKey: ["gen", readingId],
    queryFn: () => api.genealogy(readingId!),
    enabled: readingId != null,
  });

  return (
    <div className="gen">
      <h4>{t("gen_title")}</h4>
      {flagged.length === 0 ? (
        <div className="hint">{t("gen_passed")}</div>
      ) : (
        <>
          <div className="seg" style={{ flexWrap: "wrap", marginBottom: 10 }}>
            {flagged.slice(0, 6).map((a) => (
              <button
                key={a.id}
                type="button"
                aria-pressed={readingId === a.reading_id}
                onClick={() => a.reading_id != null && onSelect(a.reading_id)}
              >
                #{a.reading_id}
              </button>
            ))}
          </div>
          <div className="hint">{t("gen_hint")}</div>
        </>
      )}
      {readingId != null && rows.length > 0 && (
        <ul className="stages">
          {rows.map((s, i) => (
            <li className={"stage " + s.status} key={i}>
              <span className="dot" />
              <div style={{ minWidth: 0 }}>
                <div style={{ display: "flex", gap: 9, alignItems: "center" }}>
                  <span className="sname">{t("s_" + s.stage) !== "s_" + s.stage ? t("s_" + s.stage) : s.stage}</span>
                  <span className="sstatus">{s.status}</span>
                </div>
                <div className="sdetail">{JSON.stringify(s.detail)}</div>
                <div className="stime">{new Date(s.at).toLocaleTimeString([], { hour12: false })}</div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
