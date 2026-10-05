// Typed client for the read API. Paths are relative; Vite proxies /api to :8080.

export type Status = "online" | "stale" | "offline";

export interface FleetRow {
  external_id: string;
  kind: string;
  location: string | null;
  metric: string | null;
  last_value: number | null;
  unit: string | null;
  last_reading: string | null;
  last_seen_at: string | null;
  staleness_s: number | null;
  open_anomalies: number;
  status: Status;
}

export interface Device {
  external_id: string;
  kind: string;
  location: string | null;
  firmware: string | null;
  metrics: string[];
}

export interface SeriesPoint {
  sampled_at: string;
  value: number;
  rolling_mean_10: number | null;
}

export interface SeriesResponse {
  external_id: string;
  metric: string;
  points: SeriesPoint[];
}

export interface DeviceAnomaly {
  id: number;
  reading_id: number | null;
  type: string;
  severity: string;
  detail: Record<string, unknown>;
  detected_at: string;
  resolved_at: string | null;
  reading_sampled_at: string | null;
  reading_value: number | null;
}

export interface GenealogyRow {
  reading_id: number;
  external_id: string;
  metric: string;
  value: number;
  sampled_at: string;
  stage: string;
  status: string;
  detail: Record<string, unknown>;
  at: string;
}

export interface ParetoRow {
  type: string;
  severity: string;
  total: number;
  still_open: number;
  devices_affected: number;
}

export interface RecentAnomaly {
  external_id: string;
  type: string;
  severity: string;
  detected_at: string;
  resolved_at: string | null;
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText} on ${path}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  fleet: () => get<FleetRow[]>("/api/fleet"),
  devices: () => get<Device[]>("/api/devices"),
  series: (id: string, metric?: string, limit = 120) =>
    get<SeriesResponse>(
      `/api/devices/${encodeURIComponent(id)}/series?limit=${limit}` +
        (metric ? `&metric=${encodeURIComponent(metric)}` : ""),
    ),
  deviceAnomalies: (id: string) =>
    get<DeviceAnomaly[]>(`/api/devices/${encodeURIComponent(id)}/anomalies`),
  genealogy: (readingId: number) =>
    get<GenealogyRow[]>(`/api/readings/${readingId}/genealogy`),
  pareto: () => get<ParetoRow[]>("/api/anomalies/pareto"),
  recentAnomalies: (limit = 20) =>
    get<RecentAnomaly[]>(`/api/anomalies/recent?limit=${limit}`),
};
