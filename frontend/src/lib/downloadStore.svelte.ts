import { downloadModel, getDownloadQueue, reorderDownloads as apiReorder } from "./api";
import type { DownloadItem } from "./stores/types";

const DL_ACTIVE_INTERNAL = ["pending", "queued", "downloading"];

export function createDownloadStore(
  deps: {
    onDownloadCompleted: (modelId: number) => void,
    getInstalledRefresher: () => () => Promise<void>,
    getFileStatusRefresher: () => ((versionId: number) => Promise<void>) | null,
    getSelectedVersionId: () => number | undefined,
  }
) {
  let downloads = $state<Record<string, { fileId: number | null; versionId: number; modelId: number; fileName: string; status: string; progress: number; bytesDownloaded?: number; bytesTotal?: number; speed?: number; etaSec?: number; _t?: number; error?: string }>>({});
  let downloadOrder = $state<string[]>([]);
  let dlPolling = false;
  let reorderTimer: ReturnType<typeof setTimeout> | null = null;

  let activeDownloads = $derived.by(() => {
    const list: { id: string; fileName: string; modelId: number; versionId: number; status: string; progress: number; speed?: number; etaSec?: number; bytesDownloaded?: number; bytesTotal?: number }[] = [];
    for (const id of downloadOrder) {
      if (downloads[id] && DL_ACTIVE_INTERNAL.includes(downloads[id].status)) {
        list.push({ id, ...downloads[id] });
      }
    }
    for (const id in downloads) {
      if (!list.find(x => x.id === id) && DL_ACTIVE_INTERNAL.includes(downloads[id].status)) {
        list.push({ id, ...downloads[id] });
      }
    }
    return list;
  });
  let hasActiveDownloads = $derived(activeDownloads.length > 0);

  async function queueDownload(params: {
    modelId: number;
    versionId: number;
    fileId?: number;
    downloadUrl: string;
    downloadDir: string;
    fileName: string;
    fileType?: string;
    modelType?: string;
    sizeKB?: number;
  }): Promise<string | null> {
    const res: any = await downloadModel(params);
    const id = res?.id;
    if (!id) {
      console.error("[CivBro] downloadModel returned no id — download not queued in frontend");
      return null;
    }
    downloads = {
      ...downloads,
      [id]: { fileId: params.fileId ?? null, versionId: params.versionId, modelId: params.modelId, fileName: params.fileName, status: "queued", progress: 0 },
    };
    downloadOrder = [...downloadOrder, id];
    pollDownloads();
    return id;
  }

  function reorderDownloads(fromIdx: number, toIdx: number) {
    const active = downloadOrder.filter(id => downloads[id] && DL_ACTIVE_INTERNAL.includes(downloads[id].status));
    if (fromIdx < 0 || fromIdx >= active.length || toIdx < 0 || toIdx >= active.length) return;
    const id = active[fromIdx];
    let filtered = downloadOrder.filter(x => x !== id && downloads[x] && DL_ACTIVE_INTERNAL.includes(downloads[x].status));
    filtered.splice(toIdx, 0, id);
    downloadOrder = [...filtered, ...downloadOrder.filter(x => !filtered.includes(x))];
    scheduleReorder();
  }

  function scheduleReorder() {
    if (reorderTimer) clearTimeout(reorderTimer);
    const active = downloadOrder.filter(id => downloads[id] && DL_ACTIVE_INTERNAL.includes(downloads[id].status));
    if (!active.length) return;
    reorderTimer = setTimeout(async () => {
      const current = downloadOrder.filter(id => downloads[id] && DL_ACTIVE_INTERNAL.includes(downloads[id].status));
      try { await apiReorder(current); } catch {}
    }, 400);
  }

  const MAX_POLL_ITERATIONS = 3600;
  async function pollDownloads() {
    if (dlPolling) return;
    dlPolling = true;
    let stuck = 0;
    let iterations = 0;
    while (dlPolling && iterations++ < MAX_POLL_ITERATIONS) {
      const activeIds = Object.keys(downloads).filter((id) => DL_ACTIVE_INTERNAL.includes(downloads[id].status));
      if (activeIds.length === 0) { dlPolling = false; return; }
      await new Promise((r) => setTimeout(r, 1500));
      let items: any;
      try { items = await getDownloadQueue(); } catch { stuck++; if (stuck > 5) { dlPolling = false; return; } continue; }
      stuck = 0;
      const list = (items?.items || items || []) as any[];
      const next = { ...downloads };
      let anyCompleted = false;
      const now = Date.now();
      for (const id of Object.keys(next)) {
        if (!DL_ACTIVE_INTERNAL.includes(next[id].status)) continue;
        const it = list.find((x: any) => x.id === id);
        if (!it) { next[id] = { ...next[id], status: "gone" }; continue; }
        const prevBytes = next[id].bytesDownloaded || 0;
        const prevT = next[id]._t || now;
        const dt = (now - prevT) / 1000;
        const dBytes = (it.bytesDownloaded || 0) - prevBytes;
        let speed = dt > 0.2 && dBytes >= 0 ? dBytes / dt : (next[id].speed || 0);
        if (next[id].speed) speed = next[id].speed! * 0.5 + speed * 0.5;
        const remaining = (it.bytesTotal || 0) - (it.bytesDownloaded || 0);
        const etaSec = speed > 0 && remaining > 0 ? Math.round(remaining / speed) : 0;
        const prog = it.bytesTotal > 0 ? Math.min(100, Math.round((it.bytesDownloaded / it.bytesTotal) * 100)) : next[id].progress;
        if (it.status === "completed") anyCompleted = true;
        next[id] = {
          ...next[id],
          status: it.status,
          progress: prog,
          bytesDownloaded: it.bytesDownloaded,
          bytesTotal: it.bytesTotal,
          speed: it.status === "downloading" ? speed : 0,
          etaSec: it.status === "downloading" ? etaSec : 0,
          _t: now,
          error: it.errorMessage || undefined,
        };
      }
      downloads = next;
      if (anyCompleted) {
        for (const id in downloads) {
          if (downloads[id].status === "completed") {
            deps.onDownloadCompleted(downloads[id].modelId);
          }
        }
        deps.getInstalledRefresher()();
        const svId = deps.getSelectedVersionId();
        const fr = deps.getFileStatusRefresher();
        if (svId !== undefined && fr) fr(svId);
      }
    }
  }

  async function hydrateDownloadQueue(downloadsRef: Record<string, any>, orderRef: string[]) {
    try {
      const res: any = await getDownloadQueue();
      const items = res?.items || [];
      if (items.length === 0) return;
      const next = { ...downloadsRef };
      const order = [...orderRef];
      let hasActive = false;
      for (const it of items) {
        if (next[it.id]) continue;
        const status = it.status || "pending";
        next[it.id] = {
          fileId: it.fileId ?? null,
          versionId: it.versionId,
          modelId: it.modelId,
          fileName: it.fileName || "",
          status,
          progress: it.progress || 0,
          bytesDownloaded: it.bytesDownloaded || 0,
          bytesTotal: it.bytesTotal || 0,
        };
        order.push(it.id);
        if (DL_ACTIVE_INTERNAL.includes(status)) hasActive = true;
      }
      downloads = next;
      downloadOrder = order;
      if (hasActive) pollDownloads();
    } catch (e) {
      console.debug("[CivBro] hydrateDownloadQueue failed:", e);
    }
  }

  function cleanup() {
    if (reorderTimer) { clearTimeout(reorderTimer); reorderTimer = null; }
    dlPolling = false;
  }

  return {
    get downloadQueue() { return []; },
    set downloadQueue(v: DownloadItem[]) {},
    get downloads() { return downloads; },
    set downloads(v: typeof downloads) { downloads = v; },
    get downloadOrder() { return downloadOrder; },
    set downloadOrder(v: string[]) { downloadOrder = v; },
    get activeDownloads() { return activeDownloads; },
    get hasActiveDownloads() { return hasActiveDownloads; },
    queueDownload, pollDownloads, reorderDownloads, hydrateDownloadQueue, cleanup,
  };
}
