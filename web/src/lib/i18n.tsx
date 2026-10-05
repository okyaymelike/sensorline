import { createContext, useContext, useState, type ReactNode } from "react";

export type Lang = "en" | "de";

type Dict = Record<string, string>;

const STR: Record<Lang, Dict> = {
  en: {
    nav_fleet: "Fleet", nav_investigate: "Investigate", nav_anomalies: "Anomalies",
    preview: "live telemetry · simulated fleet",
    fleet_title: "Hangar · fleet",
    fleet_sub: "Filter by location or type, group them, and watch the stream live.",
    groupby: "Group by", f_location: "Location", f_type: "Type",
    g_location: "Location", g_type: "Type",
    all_locations: "All locations", all_types: "All types",
    autorefresh: "Auto-refresh · 5s", paused: "paused", live_in: "live · refresh in {n}s",
    k_groups: "groups", k_devices: "devices · {n} online", k_stale: "stale / offline", k_open2: "open anomalies",
    z_dev: "dev", z_open: "open", t_open: "{n} open", live: "live", no_match: "No devices match these filters.",
    leg_reading: "Reading", leg_baseline: "Baseline ±band", leg_warn: "Warn", leg_crit: "Critical",
    gen_title: "Reading genealogy", gen_flagged: "flagged at the evaluated stage", gen_passed: "passed every stage",
    gen_hint: "click a flagged point to trace it", gen_none: "No reading selected yet.",
    s_ingested: "ingested", s_validated: "validated", s_enriched: "enriched", s_evaluated: "evaluated",
    anom_title: "Anomalies", anom_sub: "Where failures concentrate, and the live feed.",
    pareto_h: "Pareto — type & severity", recent_h: "Recent anomalies",
    a_open: "open", a_resolved: "resolved",
    sev_critical: "critical", sev_warn: "warn", sev_info: "info",
    ty_drift: "drift", ty_spike: "spike", ty_offline_gap: "offline gap", ty_out_of_range: "out of range", ty_flatline: "flatline",
    loading: "loading…", error: "could not reach the API",
  },
  de: {
    nav_fleet: "Flotte", nav_investigate: "Untersuchen", nav_anomalies: "Anomalien",
    preview: "Live-Telemetrie · simulierte Flotte",
    fleet_title: "Hangar · Flotte",
    fleet_sub: "Nach Standort oder Typ filtern, gruppieren und den Stream live verfolgen.",
    groupby: "Gruppieren nach", f_location: "Standort", f_type: "Typ",
    g_location: "Standort", g_type: "Typ",
    all_locations: "Alle Standorte", all_types: "Alle Typen",
    autorefresh: "Auto-Aktualisierung · 5s", paused: "pausiert", live_in: "live · Aktualisierung in {n}s",
    k_groups: "Gruppen", k_devices: "Geräte · {n} online", k_stale: "veraltet / offline", k_open2: "offene Anomalien",
    z_dev: "Ger.", z_open: "offen", t_open: "{n} offen", live: "live", no_match: "Keine Geräte entsprechen diesen Filtern.",
    leg_reading: "Messwert", leg_baseline: "Basislinie ±Band", leg_warn: "Warnung", leg_crit: "Kritisch",
    gen_title: "Messwert-Herkunft", gen_flagged: "in der Auswertung markiert", gen_passed: "alle Stufen bestanden",
    gen_hint: "markierten Punkt anklicken zum Nachverfolgen", gen_none: "Noch kein Messwert gewählt.",
    s_ingested: "aufgenommen", s_validated: "validiert", s_enriched: "angereichert", s_evaluated: "ausgewertet",
    anom_title: "Anomalien", anom_sub: "Wo sich Fehler häufen, plus Live-Feed.",
    pareto_h: "Pareto — Typ & Schwere", recent_h: "Aktuelle Anomalien",
    a_open: "offen", a_resolved: "behoben",
    sev_critical: "kritisch", sev_warn: "Warnung", sev_info: "Info",
    ty_drift: "Drift", ty_spike: "Spitze", ty_offline_gap: "Offline-Lücke", ty_out_of_range: "außerhalb", ty_flatline: "Flatline",
    loading: "lädt…", error: "API nicht erreichbar",
  },
};

const KIND_DE: Dict = {
  "temp-probe": "Temperatursonde", vibration: "Vibration", humidity: "Feuchtigkeit",
  pressure: "Druck", flow: "Durchfluss", current: "Strom", "motor-speed": "Motordrehzahl",
  "air-quality": "Luftqualität",
};

interface LangCtx {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: string) => string;
  tN: (key: string, n: number | string) => string;
  kindLabel: (k: string) => string;
}

const Ctx = createContext<LangCtx | null>(null);

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>("en");
  const t = (key: string) => STR[lang][key] ?? STR.en[key] ?? key;
  const tN = (key: string, n: number | string) => t(key).replace("{n}", String(n));
  const kindLabel = (k: string) => (lang === "de" && KIND_DE[k]) || k;
  return <Ctx.Provider value={{ lang, setLang, t, tN, kindLabel }}>{children}</Ctx.Provider>;
}

export function useLang(): LangCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useLang outside LangProvider");
  return ctx;
}
