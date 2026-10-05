import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, type ParetoRow } from "../api";
import { useLang } from "../lib/i18n";

interface Props {
  refreshMs: number | false;
  onOpenDevice: (id: string) => void;
}

const SEVS = ["critical", "warn", "info"] as const;
const sevColor = (s: string) =>
  s === "critical" ? "var(--crit)" : s === "warn" ? "var(--warn)" : "var(--info)";

function agoShort(iso: string): string {
  const s = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 1000));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  return `${Math.floor(s / 3600)}h`;
}

export function Anomalies({ refreshMs, onOpenDevice }: Props) {
  const { t } = useLang();
  const { data: pareto = [] } = useQuery({ queryKey: ["pareto"], queryFn: api.pareto, refetchInterval: refreshMs });
  const { data: recent = [] } = useQuery({ queryKey: ["recent"], queryFn: () => api.recentAnomalies(30), refetchInterval: refreshMs });

  // fold the pareto rows into one row per type, stacked by severity
  const byType = new Map<string, Record<string, number | string>>();
  for (const r of pareto as ParetoRow[]) {
    const row = byType.get(r.type) ?? { type: t("ty_" + r.type), critical: 0, warn: 0, info: 0 };
    row[r.severity] = (Number(row[r.severity]) || 0) + r.total;
    byType.set(r.type, row);
  }
  const data = Array.from(byType.values()).sort(
    (a, b) =>
      Number(b.critical) + Number(b.warn) + Number(b.info) -
      (Number(a.critical) + Number(a.warn) + Number(a.info)),
  );

  return (
    <>
      <div className="head">
        <h1>{t("anom_title")}</h1>
        <p>{t("anom_sub")}</p>
      </div>
      <div className="anom-grid">
        <div className="panel">
          <div className="panel-h"><h3>{t("pareto_h")}</h3></div>
          <div className="pareto-box">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 8 }}>
                <CartesianGrid stroke="var(--border)" horizontal={false} />
                <XAxis type="number" allowDecimals={false} tick={{ fill: "var(--muted)", fontSize: 11 }} stroke="var(--border)" />
                <YAxis type="category" dataKey="type" width={92} tick={{ fill: "var(--muted)", fontSize: 11 }} stroke="var(--border)" />
                <Tooltip contentStyle={{ fontFamily: "var(--font-mono)", fontSize: 12, borderRadius: 10, border: "1px solid var(--border)" }} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                {SEVS.map((s) => (
                  <Bar key={s} dataKey={s} stackId="a" name={t("sev_" + s)} fill={sevColor(s)} radius={[2, 2, 2, 2]} barSize={22} isAnimationActive={false} />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="panel">
          <div className="panel-h"><h3>{t("recent_h")}</h3></div>
          <ul className="feed">
            {recent.map((a, i) => (
              <li key={i} onClick={() => onOpenDevice(a.external_id)}>
                <div style={{ minWidth: 0 }}>
                  <div className="fdid">
                    {a.external_id} <span className={"sev " + a.severity}>{t("sev_" + a.severity)}</span>
                  </div>
                  <div className="fmeta">
                    {t("ty_" + a.type)} · {a.resolved_at ? t("a_resolved") : t("a_open")}
                  </div>
                </div>
                <span className="ftime">{agoShort(a.detected_at)}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </>
  );
}
