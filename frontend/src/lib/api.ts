const API_BASE = "/civbro/api";

interface SearchParams {
  query?: string;
  modelType?: string[];
  baseModel?: string[];
  nsfw?: boolean;
  tag?: string;
  sort?: string;
  period?: string;
  page?: number;
  limit?: number;
  cursor?: string;
  source?: string;
}

async function fetchApi<T>(
  endpoint: string,
  options?: RequestInit,
  retries = 1
): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const res = await fetch(url, {
        headers: { "Content-Type": "application/json", ...options?.headers },
        ...options,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `API error: ${res.status}`);
      }

      return await res.json();
    } catch (err) {
      if (attempt < retries && (!options?.method || options.method === "GET")) {
        await new Promise((r) => setTimeout(r, 500));
        continue;
      }
      throw err;
    }
  }
  throw new Error("API request failed");
}

export async function searchModels(params: SearchParams) {
  const qs = new URLSearchParams();
  if (params.query) qs.set("query", params.query);
  if (params.modelType && params.modelType.length > 0)
    for (const t of params.modelType) qs.append("type", t);
  if (params.baseModel && params.baseModel.length > 0)
    for (const b of params.baseModel) qs.append("baseModel", b);
  if (params.nsfw !== undefined) qs.set("nsfw", String(params.nsfw));
  if (params.tag) qs.set("tag", params.tag);
  if (params.sort) qs.set("sort", params.sort);
  if (params.period) qs.set("period", params.period);
  if (params.limit) qs.set("limit", String(params.limit));
  if (params.cursor) qs.set("cursor", params.cursor);
  qs.set("source", params.source || "rest");
  return fetchApi(`/models?${qs.toString()}`);
}

import type { CivitaiModel } from "./stores.svelte";

export async function getModel(modelId: number): Promise<CivitaiModel> {
  return fetchApi<CivitaiModel>(`/models/${modelId}`);
}

export async function getModelExtras(ids: number[], filters?: { sort?: string; period?: string; type?: string; nsfw?: boolean }): Promise<{ extras: Record<string, { cosmetic?: { cssFrame: string; glow: boolean }; baseModels?: string[]; avatarDeco?: string; badge?: string; hasBuzz?: boolean; nameplate?: { gradient?: string; color?: string }; availability?: string; earlyAccessDeadline?: string; publishedAt?: string; createdAt?: string; mode?: string }> }> {
  const qs = new URLSearchParams();
  for (const i of ids) qs.append("id", String(i));
  if (filters?.sort) qs.set("sort", filters.sort);
  if (filters?.period) qs.set("period", filters.period);
  if (filters?.type) qs.set("type", filters.type);
  if (filters?.nsfw) qs.set("nsfw", "true");
  return fetchApi(`/models/extras?${qs.toString()}`);
}

export async function getModelVersions(modelId: number) {
  return fetchApi(`/models/${modelId}/versions`);
}

export async function getVersionDetails(versionId: number) {
  return fetchApi(`/versions/${versionId}`);
}

export async function downloadModel(body: {
  modelId: number;
  versionId: number;
  fileId?: number;
  downloadUrl: string;
  downloadDir: string;
  fileName?: string;
  sizeKB?: number;
}) {
  return fetchApi("/download", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function getDownloadQueue() {
  return fetchApi("/download/queue");
}

export async function deleteDownload(id: string) {
  return fetchApi(`/download/${id}`, { method: "DELETE" });
}

export async function deleteLocalModel(modelId: number) {
  return fetchApi(`/local/delete?model_id=${modelId}`, { method: "DELETE" });
}

export async function getLocalModels() {
  return fetchApi("/local/models");
}

export async function getInstalledVersions(): Promise<{ versionIds: number[]; modelIds: number[] }> {
  return fetchApi("/local/installed");
}

export async function getFileStatus(
  versionId: number,
  verify = false,
): Promise<{ files: { fileId: number; name: string; dir: string; status: string; hashOk: boolean | null; sizeKB: number }[] }> {
  return fetchApi(`/local/filestatus?version_id=${versionId}${verify ? "&verify=1" : ""}`);
}

export async function scanLocalModels(type?: string) {
  const qs = type ? `?model_type=${encodeURIComponent(type)}` : "";
  return fetchApi(`/local/scan${qs}`);
}

export async function refreshLocalModels() {
  return fetchApi("/local/refresh", { method: "POST" });
}

export async function getSettings(): Promise<Record<string, unknown> | null> {
  try {
    return fetchApi("/settings/_all");
  } catch {
    return null;
  }
}

export async function setSettings(settings: Record<string, unknown>) {
  return fetchApi("/settings/_all", {
    method: "POST",
    body: JSON.stringify({ value: JSON.stringify(settings) }),
  });
}

export async function getTags() {
  return fetchApi("/tags");
}

export async function getSuggestions(query: string) {
  return fetchApi(`/search/suggestions?query=${encodeURIComponent(query)}`);
}

export async function clearCache() {
  return fetchApi("/cache", { method: "DELETE" });
}

export async function setThrottle(enable: boolean) {
  return fetchApi("/download/throttle", {
    method: "POST",
    body: JSON.stringify({ enable }),
  });
}

export async function validateApiKey(key: string): Promise<{ valid: boolean; message: string }> {
  return fetchApi("/settings/validate-key", {
    method: "POST",
    body: JSON.stringify({ key }),
  });
}

export async function reorderDownloads(order: string[]) {
  return fetchApi("/download/reorder", {
    method: "POST",
    body: JSON.stringify({ order }),
  });
}
