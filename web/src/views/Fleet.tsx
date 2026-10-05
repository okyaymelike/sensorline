import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type FleetRow, type Status } from "../api";
import { useLang } from "../lib/i18n";
import { ago, fmtValue, STATUS_RANK } from "../lib/format";

type GroupBy = "location" | "kind";

const uniq = (xs: string[]) => Array.from(new Set(xs));

interface Props {
  live: boolean;
  setLive: (v: boolean) => void;
  refreshMs: number | false;
  onOpenDevice: (id: string) => void;
}

export function Fleet({ live, setLive, refreshMs, onOpenDevice }: Props) {
  const { t, tN, kindLabel } = useLang();
  const [groupBy, setGroupBy] = useState<GroupBy>("location");
  const [fLoc, setFLoc] = useState("");
  const [fKind, setFKind] = useState("");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["fleet"],
    queryFn: api.fleet,
    refetchInterval: refreshMs,
  });

  const rows = data ?? [];
  const locations = uniq(rows.map((r) => r.location ?? "—"));
  const kinds = uniq(rows.map((r) => r.kind));
  const filtered = rows.filter(
    (r) => (!fLoc || (r.location ?? "—") === fLoc) && (!fKind || r.kind === fKind),
  );

  const online = filtered.filter((r) => r.status === "online").length;
  const stale = filtered.filter((r) => r.status === "stale").length;
  const offline = filtered.filter((r) => r.status === "offline").length;
  const openTotal = filtered.reduce((a, r) => a + r.open_anomalies, 0);

  const groupKey = (r: FleetRow) => (groupBy === "location" ? r.location ?? "—" : r.kind);
  const groups = uniq(filtered.map(groupKey));

  return (
    <>
      <div className="preview-tag">
        <span className="pt-dot" />
        {t("preview")}
      </div>
      <div className="head">
        <h1>{t("fleet_title")}</h1>
        <p>{t("fleet_sub")}</p>
      </div>

      <div className="summary">
        <SumCard k={t("k_groups")} v={groups.length} />
        <SumCard k={tN("k_devices", online)} v={filtered.length} />
        <SumCard k={t("k_stale")} v={`${stale} / ${offline}`} color={stale + offline ? "var(--warn)" : undefined} />
        <SumCard k={t("k_open2")} v={openTotal} color={openTotal ? "var(--crit)" : undefined} />
      </div>

      <div className="toolbar">
        <div className="fgrp">
          <span className="ov">{t("groupby")}</span>
          <div className="seg" role="group" aria-label="Group by">
            <button type="button" aria-pressed={groupBy === "location"} onClick={() => setGroupBy("location")}>
              {t("g_location")}
            </button>
            <button type="button" aria-pressed={groupBy === "kind"} onClick={() => setGroupBy("kind")}>
              {t("g_type")}
            </button>
          </div>
        </div>
        <div className="fgrp">
          <span className="ov">{t("f_location")}</span>
          <select value={fLoc} onChange={(e) => setFLoc(e.target.value)}>
            <option value="">{t("all_locations")}</option>
            {locations.map((l) => (
              <option key={l} value={l}>{l}</option>
            ))}
          </select>
        </div>
        <div className="fgrp">
          <span className="ov">{t("f_type")}</span>
          <select value={fKind} onChange={(e) => setFKind(e.target.value)}>
            <option value="">{t("all_types")}</option>
            {kinds.map((k) => (
              <option key={k} value={k}>{kindLabel(k)}</option>
            ))}
          </select>
        </div>
        <div className="refresh">
          <label className="sw-wrap">
            <input type="checkbox" checked={live} onChange={(e) => setLive(e.target.checked)} />
            <span className="sw" />
            {t("autorefresh")}
          </label>
          <span className={"rstat" + (live ? " on" : "")}>
            <span className="beat" />
            {live ? t("live_in").replace("{n}", "5") : t("paused")}
          </span>
        </div>
      </div>

      {isLoading ? (
        <div className="state">{t("loading")}</div>
      ) : isError ? (
        <div className="state err">{t("error")}</div>
      ) : (
        <div className="zones">
          {filtered.length === 0 ? (
            <div className="empty">{t("no_match")}</div>
          ) : (
            groups.map((g) => {
              const gd = filtered.filter((r) => groupKey(r) === g);
              const worst = gd.reduce<Status>(
                (a, r) => (STATUS_RANK[r.status] > STATUS_RANK[a] ? r.status : a),
                "online",
              );
              const openCount = gd.reduce((a, r) => a + r.open_anomalies, 0);
              const label = groupBy === "kind" ? kindLabel(g) : g;
              return (
                <div className="zone" key={g}>
                  <div className="zone-h">
                    <div className="zt">
                      <span className={"zdot " + worst} />
                      {label}
                    </div>
                    <div className="zmeta">
                      <span><b>{gd.length}</b> {t("z_dev")}</span>
                      <span style={{ color: openCount ? "var(--crit)" : undefined }}>
                        <b style={{ color: "inherit" }}>{openCount}</b> {t("z_open")}
                      </span>
                    </div>
                  </div>
                  <div className="zbody">
                    {gd.map((r) => (
                      <div className="tile" key={r.external_id} onClick={() => onOpenDevice(r.external_id)}>
                        <span className={"st " + r.status} />
                        <div className="mid">
                          <div>
                            <div className="id">{r.external_id}</div>
                            <div className="sub">{kindLabel(r.kind)}{r.metric ? ` · ${r.metric}` : ""}</div>
                          </div>
                        </div>
                        <div className="right">
                          {r.open_anomalies > 0 && (
                            <span className="abadge">{tN("t_open", r.open_anomalies)}</span>
                          )}
                          <span className="val">{fmtValue(r.last_value, r.unit)}</span>
                          <span className="seen">{ago(r.staleness_s, t("live"))}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}
    </>
  );
}

function SumCard({ k, v, color }: { k: string; v: number | string; color?: string }) {
  return (
    <div className="sm">
      <div className="sv" style={color ? { color } : undefined}>{v}</div>
      <div className="sk">{k}</div>
    </div>
  );
}
