import { searchModels, getModel, getModelVersions, getVersionDetails, getLocalModels, getInstalledVersions, getFileStatus, downloadModel, getDownloadQueue, getSettings, setSettings, setThrottle, validateApiKey, getModelExtras, reorderDownloads as apiReorder } from "./api";

export interface CivitaiModel {
  id: number;
  name: string;
  description?: string;
  type: string;
  nsfw: boolean;
  stats?: {
    downloadCount: number;
    ratingCount: number;
    rating: number;
    thumbsUpCount: number;
    thumbsDownCount: number;
    favoriteCount?: number;
    commentCount?: number;
    tippedAmountCount?: number;
  };
  creator?: {
    username: string;
    image?: string;
  };
  modelVersions?: ModelVersion[];
  images?: ModelImage[];
  tags?: string[];
  baseModel?: string;
  cosmetic?: { cssFrame: string; glow: boolean } | null;
  poster?: string;
  baseModels?: string[];
  avatarDeco?: string;
  badge?: string;
  hasBuzz?: boolean;
  nameplate?: { gradient?: string; color?: string };
  availability?: string;
  earlyAccessDeadline?: string;
  publishedAt?: string;
  createdAt?: string;
  mode?: string;
}

export interface ModelDependency {
  type: string;
  modelId?: number;
  modelName?: string;
  versionId: number;
  versionName?: string;
  fileId?: number;
  name: string;
  sizeKB: number;
  required?: boolean;
  downloadUrl: string;
}

export interface ModelVersion {
  id: number;
  name: string;
  description?: string;
  baseModel?: string;
  baseModelType?: string;
  trainedWords?: string[];
  files?: ModelFile[];
  images?: ModelImage[];
  downloadUrl?: string;
  createdAt?: string;
  updatedAt?: string;
  dependencies?: ModelDependency[];
  availability?: string;
  earlyAccessEndsAt?: string;
  buzzCost?: number;
  allowCommercialUse?: unknown;
  allowDerivatives?: boolean;
  allowNoCredit?: boolean;
  allowDifferentLicense?: boolean;
  baseModels?: string[];
  epochs?: number;
  steps?: number;
  clipSkip?: number;
  air?: string;
  tensorType?: string;
  modelSize?: string;
  creator?: {
    username: string;
    image?: string;
    createdAt?: string;
  };
}

export interface ModelFile {
  id: number;
  name: string;
  sizeKB: number;
  type: string;
  primary?: boolean;
  format?: string;
  fp?: string;
  sizeType?: string;
  downloadUrl?: string;
  hashes?: Record<string, string>;
  scannedAt?: string | null;
  pickleScanResult?: string | null;
  virusScanResult?: string | null;
}

export interface ModelImage {
  id: number;
  url: string;
  nsfw: string;
  width: number;
  height: number;
  type: string;
  meta?: Record<string, unknown>;
}

export interface LocalModel {
  id: number;
  name: string;
  path: string;
  size: number;
  modelId?: number;
  versionId?: number;
  type: string;
  installed: boolean;
}

export interface DownloadItem {
  id: string;
  versionId: number;
  modelName: string;
  progress: number;
  status: "queued" | "downloading" | "completed" | "failed" | "cancelled";
  error?: string;
  filePath?: string;
}

export interface Filters {
  search: string;
  modelType: string[];
  baseModel: string[];
  nsfw: boolean;
  sort: string;
  period: string;
}

export function createAppState() {
  let filters = $state<Filters>({
    search: "",
    modelType: [],
    baseModel: [],
    nsfw: false,
    sort: "Most Downloaded",
    period: "AllTime",
  });

  let models = $state<CivitaiModel[]>([]);
  let localModels = $state<LocalModel[]>([]);
  let selectedModel = $state<CivitaiModel | null>(null);
  let selectedVersion = $state<ModelVersion | null>(null);
  let modelVersions = $state<ModelVersion[]>([]);
  let popupLoading = $state(false);
  let popupReqId = 0;
  let activeTab = $state<"browse" | "local">("browse");
  let isLoading = $state(false);
  let isLoadingMore = $state(false);
  let isFetching = $state(false);
  let error = $state<string | null>(null);
  let page = $state(1);
  let cursor = $state<string | null>(null);
  let hasMore = $state(true);
  let suggestions = $state<string[]>([]);
  let downloadQueue = $state<DownloadItem[]>([]);
  let installedVersionIds = $state<number[]>([]);
  let installedModelIds = $state<Set<number>>(new Set());
  let onlyInstalled = $state(false);
  let fastSearch = $state(false);
  let savedPeriod = $state("AllTime");
  let fileStatus = $state<Record<string, string>>({});
  // Persistent per-download tracking (survives popup open/close).
  let downloads = $state<Record<string, { fileId: number | null; versionId: number; modelId: number; fileName: string; status: string; progress: number; bytesDownloaded?: number; bytesTotal?: number; speed?: number; etaSec?: number; _t?: number; error?: string }>>({});
  let downloadOrder = $state<string[]>([]);
  let dlPolling = false;
  let nsfwBlurEnabled = $state(true);
  let apiKey = $state("");
  let apiKeyValid = $state<boolean | null>(null);
  let settingsLoaded = $state(false);

  function parseSettingArr(...vals: unknown[]): string[] {
    for (const v of vals) {
      if (Array.isArray(v)) return v.map(String);
      if (typeof v === "string" && v) {
        try { const p = JSON.parse(v); if (Array.isArray(p)) return p; } catch {}
        return [v];
      }
    }
    return [];
  }

  async function loadSettings() {
    try {
      const result: any = await getSettings();
      const settings: any = result?.settings || result || {};
      filters.nsfw = settings.showNsfw ?? false;
      filters.modelType = parseSettingArr(settings.defaultModelType, settings.defaultModelTypes);
      filters.baseModel = parseSettingArr(settings.defaultBaseModel, settings.defaultBaseModels);
      filters.sort = settings.defaultSort ?? "Most Downloaded";
      filters.period = settings.defaultPeriod ?? "AllTime";
      nsfwBlurEnabled = settings.nsfwBlur ?? true;
      apiKey = settings.civitaiRedApiKey ?? "";
      if (apiKey) apiKeyValid = true;
      // Fetch installed model IDs BEFORE marking settings as loaded so the
      // first card render can show green checkmarks immediately.
      await refreshInstalled();
    } catch {
    } finally {
      settingsLoaded = true;
    }
  }

  async function saveSettings() {
    try {
      await setSettings({
        showNsfw: filters.nsfw,
        defaultModelTypes: JSON.stringify(filters.modelType),
        defaultBaseModels: JSON.stringify(filters.baseModel),
        defaultSort: filters.sort,
        defaultPeriod: filters.period,
        nsfwBlur: nsfwBlurEnabled,
        civitaiRedApiKey: apiKey,
      });
    } catch (e) {
      console.error("[CivBro] saveSettings failed:", e);
    }
  }

  async function validateAndSaveKey(key: string) {
    apiKey = key;
    if (!key.trim()) {
      apiKeyValid = null;
      saveSettings();
      return;
    }
    try {
      const result = await validateApiKey(key.trim());
      apiKeyValid = result.valid;
      if (result.valid) saveSettings();
    } catch {
      apiKeyValid = false;
    }
  }

  async function fetchModels(reset = false) {
    if (isFetching) return;
    isFetching = true;
    if (reset) { page = 1; cursor = null; hasMore = true; isLoading = true; extrasRequested.clear(); }
    else { isLoadingMore = true; }

    error = null;
    try {
      const result: any = await searchModels({
        query: filters.search,
        modelType: filters.modelType.length > 0 ? filters.modelType : undefined,
        baseModel: filters.baseModel.length > 0 ? filters.baseModel : undefined,
        nsfw: filters.nsfw || undefined,
        sort: filters.sort,
        period: filters.period !== "AllTime" ? filters.period : undefined,
        limit: 20,
        cursor: reset ? undefined : (cursor ?? undefined),
        // Source follows the NSFW toggle: civitai.red (uncensored, needs a key)
        // only when NSFW is on; otherwise the faster civitai.com REST API.
        source: filters.nsfw && apiKey ? "red" : "rest",
      });

      let items = result.items || [];
      const nextCursor = result.nextCursor;

      // Client-side filtering: only show models that have at least one local file.
      if (onlyInstalled && installedModelIds.size > 0) {
        items = items.filter((m: CivitaiModel) => installedModelIds.has(m.id));
      }

      models = reset ? items : [...models, ...items];
      cursor = nextCursor != null && nextCursor !== "" ? String(nextCursor) : null;
      hasMore = cursor != null && items.length > 0;
      // Lazily enrich cards (cosmetic border, base-model family, avatar
      // decoration, badge) from tRPC — fire-and-forget so it never blocks the
      // grid render.
      loadExtras();
    } catch (e) {
      error = e instanceof Error ? e.message : "Failed to fetch models";
      if (reset) models = [];
    } finally {
      isLoading = false;
      isLoadingMore = false;
      isFetching = false;
      // Restore period after fast-search altered it
      if (fastSearch && filters.search) {
        filters.period = savedPeriod || "AllTime";
      }
    }
  }

  // Non-blocking: fetch tRPC-only card extras (cosmetics, base-model family,
  // avatar decoration, badge, nameplate, EA/updated) by the exact grid model ids
  // and patch the already-rendered models. Called after the grid is shown, so it
  // never delays loading. Only ids not already requested are fetched.
  const extrasRequested = new Set<number>();
  async function loadExtras() {
    try {
      const ids = models.map((m) => m.id).filter((id) => id && !extrasRequested.has(id));
      if (ids.length === 0) return;
      for (let i = 0; i < ids.length; i += 7) {
        const chunk = ids.slice(i, i + 7);
        try {
          const res = await getModelExtras(chunk, { sort: filters.sort, period: filters.period, type: filters.modelType?.[0] || "", nsfw: filters.nsfw });
          const extras = res?.extras || {};
          for (const id of chunk) extrasRequested.add(id);
          if (!extras || Object.keys(extras).length === 0) continue;
          let changed = false;
          for (const m of models) {
            const e = extras[String(m.id)];
            if (!e) continue;
            if (e.cosmetic && !m.cosmetic) m.cosmetic = e.cosmetic;
            if (e.baseModels && (!m.baseModels || m.baseModels.length <= 1)) m.baseModels = e.baseModels;
            if (e.avatarDeco && !m.avatarDeco) m.avatarDeco = e.avatarDeco;
            if (e.badge && !m.badge) m.badge = e.badge;
            if (e.nameplate && !m.nameplate) m.nameplate = e.nameplate;
            if (e.hasBuzz) m.hasBuzz = true;
            if (e.availability) m.availability = e.availability;
            if (e.earlyAccessDeadline) m.earlyAccessDeadline = e.earlyAccessDeadline;
            if (e.publishedAt && !m.publishedAt) m.publishedAt = e.publishedAt;
            if (e.createdAt && !m.createdAt) m.createdAt = e.createdAt;
            if (e.mode && !m.mode) m.mode = e.mode;
            changed = true;
          }
          if (changed) models = [...models];
        } catch {}
      }
    } catch {
      /* extras are best-effort; ignore failures */
    }
  }

  async function loadMore() {
    if (isLoadingMore || !hasMore || isFetching || !cursor) return;
    await fetchModels(false);
  }

  async function openModelDetail(model: CivitaiModel) {
    const reqId = ++popupReqId;
    selectedModel = null;
    selectedVersion = null;
    modelVersions = [];
    popupLoading = true;
    // Signal the backend to throttle downloads while popup images/files load.
    setThrottle(true).catch(() => {});
    try {
      const [detail, versions] = await Promise.all([
        getModel(model.id),
        getModelVersions(model.id),
      ]);
      const detailObj = (detail || {}) as Record<string, any>;
      selectedModel = { ...detailObj, hasBuzz: detailObj.hasBuzz || (model as any).hasBuzz || false, availability: detailObj.availability || (model as any).availability } as CivitaiModel;
      modelVersions = (versions as any).versions || (versions as any).items || [];
      if (modelVersions.length > 0) {
        selectedVersion = modelVersions[0];
        selectVersion(modelVersions[0]); // hydrate images/files/dependencies from version detail
      }
      getInstalledVersions()
        .then((r: any) => { installedVersionIds = r?.versionIds || []; })
        .catch(() => {});
    } catch (e) {
      if (reqId === popupReqId) error = e instanceof Error ? e.message : "Failed to load model details";
    } finally {
      if (reqId === popupReqId) {
        popupLoading = false;
        // Release the download throttle as soon as the detail has loaded so
        // background downloads regain full speed immediately (they no longer
        // wait for the popup to be closed).
        setThrottle(false).catch(() => {});
      }
    }
  }

  function closeModelDetail() {
    popupReqId++; // invalidate any in-flight open so it can't pop up later
    popupLoading = false;
    selectedModel = null;
    selectedVersion = null;
    modelVersions = [];
    setThrottle(false).catch(() => {});
  }

  async function selectVersion(v: ModelVersion) {
    selectedVersion = v;
    fileStatus = {};
    refreshFileStatus(v.id);
    try {
      const detail = (await getVersionDetails(v.id)) as ModelVersion | null;
      if (detail && detail.id === v.id) {
        const merged: ModelVersion = {
          ...v,
          ...detail,
          availability: (detail as any).availability || v.availability,
          images: (detail.images && detail.images.length ? detail.images : v.images) || [],
          files: (detail.files && detail.files.length ? detail.files : v.files) || [],
          dependencies: (detail as any).dependencies || [],
        };
        selectedVersion = merged;
        modelVersions = modelVersions.map((mv) => (mv.id === v.id ? merged : mv));
      }
    } catch {
      // keep the list-provided version data on failure
    }
  }

  const DL_ACTIVE_INTERNAL = ["pending", "queued", "downloading"];

  let activeDownloads = $derived.by(() => {
    const list: { id: string; fileName: string; modelId: number; versionId: number; status: string; progress: number; speed?: number; etaSec?: number; bytesDownloaded?: number; bytesTotal?: number }[] = [];
    for (const id of downloadOrder) {
      if (downloads[id] && DL_ACTIVE_INTERNAL.includes(downloads[id].status)) {
        list.push({ id, ...downloads[id] });
      }
    }
    // Append any active downloads not in the order array
    for (const id in downloads) {
      if (!list.find(x => x.id === id) && DL_ACTIVE_INTERNAL.includes(downloads[id].status)) {
        list.push({ id, ...downloads[id] });
      }
    }
    return list;
  });
  let hasActiveDownloads = $derived(activeDownloads.length > 0);

  async function refreshInstalled() {
    try {
      const r = await getInstalledVersions();
      installedVersionIds = r?.versionIds || [];
      installedModelIds = new Set(r?.modelIds || []);
    } catch {}
  }

  async function refreshFileStatus(versionId: number) {
    try {
      const r = await getFileStatus(versionId);
      const map: Record<string, string> = {};
      for (const f of r?.files || []) map[`${versionId}:${f.fileId}`] = f.status;
      fileStatus = map;
    } catch {
      fileStatus = {};
    }
  }

  async function queueDownload(params: {
    modelId: number;
    versionId: number;
    fileId?: number;
    downloadUrl: string;
    downloadDir: string;
    fileName: string;
    sizeKB?: number;
  }): Promise<string | null> {
    const res: any = await downloadModel(params);
    const id = res?.id;
    if (!id) return null;
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
    // Notify backend of new order
    scheduleReorder();
  }

  let reorderTimer: ReturnType<typeof setTimeout> | null = null;
  function scheduleReorder() {
    if (reorderTimer) clearTimeout(reorderTimer);
    const active = downloadOrder.filter(id => downloads[id] && DL_ACTIVE_INTERNAL.includes(downloads[id].status));
    if (!active.length) return;
    reorderTimer = setTimeout(async () => {
      const current = downloadOrder.filter(id => downloads[id] && DL_ACTIVE_INTERNAL.includes(downloads[id].status));
      try { await apiReorder(current); } catch {}
    }, 400);
  }

  async function pollDownloads() {
    if (dlPolling) return;
    dlPolling = true;
    let stuck = 0;
    while (dlPolling) {
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
        const it = list.find((x) => x.id === id);
        if (!it) { next[id] = { ...next[id], status: "gone" }; continue; }
        const prevBytes = next[id].bytesDownloaded || 0;
        const prevT = next[id]._t || now;
        const dt = (now - prevT) / 1000;
        const dBytes = (it.bytesDownloaded || 0) - prevBytes;
        // smooth speed a little to avoid jitter
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
      if (anyCompleted) { refreshInstalled(); if (selectedVersion) refreshFileStatus(selectedVersion.id); }
    }
  }

  async function refreshLocalModels() {
    try {
      const result = (await getLocalModels()) as { items?: LocalModel[] };
      localModels = result?.items || [];
    } catch (e) {
      error = e instanceof Error ? e.message : "Failed to load local models";
    }
  }

  async function fetchSuggestions(query: string) {
    if (query.length < 2) { suggestions = []; return; }
    try {
      const result: any = await searchModels({ query, limit: 5, source: filters.nsfw && apiKey ? "red" : "rest" });
      const items = result.items || result.models || [];
      suggestions = items.map((m: CivitaiModel) => m.name).slice(0, 5);
    } catch {
      suggestions = [];
    }
  }

  function setFilter(key: keyof Filters, value: string | boolean) {
    (filters as unknown as Record<string, unknown>)[key] = value;
    saveSettings();
  }

  function triggerSearch() {
    // Fast search: when a term is searched via the search box and fastSearch is on,
    // temporarily widen the period to AllTime to return more results.
    if (fastSearch && filters.search) {
      savedPeriod = filters.period;
      filters.period = "AllTime";
    }
    fetchModels(true);
  }

  function toggleModelType(value: string) {
    if (!value) { filters.modelType = []; return; }
    const idx = filters.modelType.indexOf(value);
    if (idx >= 0) filters.modelType = filters.modelType.filter(v => v !== value);
    else filters.modelType = [...filters.modelType, value];
    saveSettings();
  }

  function toggleBaseModel(value: string) {
    if (!value) { filters.baseModel = []; return; }
    const idx = filters.baseModel.indexOf(value);
    if (idx >= 0) filters.baseModel = filters.baseModel.filter(v => v !== value);
    else filters.baseModel = [...filters.baseModel, value];
    saveSettings();
  }

  function clearFilters() {
    filters.search = "";
    filters.modelType = [];
    filters.baseModel = [];
    filters.nsfw = false;
    filters.sort = "Most Downloaded";
    filters.period = "AllTime";
    saveSettings();
  }

  return {
    get filters() { return filters; },
    set filters(v) { filters = v; },
    get models() { return models; },
    set models(v) { models = v; },
    get localModels() { return localModels; },
    set localModels(v) { localModels = v; },
    get selectedModel() { return selectedModel; },
    set selectedModel(v) { selectedModel = v; },
    get popupLoading() { return popupLoading; },
    get selectedVersion() { return selectedVersion; },
    set selectedVersion(v) { selectedVersion = v; },
    get modelVersions() { return modelVersions; },
    set modelVersions(v) { modelVersions = v; },
    get activeTab() { return activeTab; },
    set activeTab(v) { activeTab = v; },
    get isLoading() { return isLoading; },
    set isLoading(v) { isLoading = v; },
    get isLoadingMore() { return isLoadingMore; },
    set isLoadingMore(v) { isLoadingMore = v; },
    get error() { return error; },
    set error(v) { error = v; },
    get page() { return page; },
    set page(v) { page = v; },
    get hasMore() { return hasMore; },
    set hasMore(v) { hasMore = v; },
    get suggestions() { return suggestions; },
    set suggestions(v) { suggestions = v; },
    get downloadQueue() { return downloadQueue; },
    set downloadQueue(v) { downloadQueue = v; },
    get installedVersionIds() { return installedVersionIds; },
    set installedVersionIds(v) { installedVersionIds = v; },
    get installedModelIds() { return installedModelIds; },
    set installedModelIds(v) { installedModelIds = v; },
    get onlyInstalled() { return onlyInstalled; },
    set onlyInstalled(v) { onlyInstalled = v; },
    get fastSearch() { return fastSearch; },
    set fastSearch(v) { fastSearch = v; },
    get fileStatus() { return fileStatus; },
    set fileStatus(v) { fileStatus = v; },
    get downloads() { return downloads; },
    set downloads(v) { downloads = v; },
    get downloadOrder() { return downloadOrder; },
    set downloadOrder(v) { downloadOrder = v; },
    get activeDownloads() { return activeDownloads; },
    get hasActiveDownloads() { return hasActiveDownloads; },
    get nsfwBlurEnabled() { return nsfwBlurEnabled; },
    set nsfwBlurEnabled(v) { nsfwBlurEnabled = v; },
    get apiKey() { return apiKey; },
    set apiKey(v) { apiKey = v; },
    get apiKeyValid() { return apiKeyValid; },
    set apiKeyValid(v) { apiKeyValid = v; },
    get settingsLoaded() { return settingsLoaded; },
    set settingsLoaded(v) { settingsLoaded = v; },

    loadSettings, saveSettings, validateAndSaveKey,
    fetchModels, loadMore, openModelDetail, closeModelDetail, selectVersion,
    refreshLocalModels, fetchSuggestions, setFilter, clearFilters, triggerSearch,
    toggleModelType, toggleBaseModel,
    queueDownload, pollDownloads, refreshInstalled, reorderDownloads,
  };
}

export const appState = createAppState();
