import { searchModels, getModel, getModelVersions, getVersionDetails, getModelExtras, getInstalledVersions, getFileStatus, setThrottle, getSuggestions } from "./api";
import { filterBrowseModels, hasNextPage } from "./browse";
import { mergeCreatorFromExtras, mergeModelDetail } from "./model-detail";
import type { CivitaiModel, ModelVersion, ModelImage, Filters } from "./stores/types";

export function createBrowseStore(
  deps: {
    getApiKeyConfigured: () => boolean,
    onDownloadCompleted: (modelId: number) => void,
    onInstalledRefreshed: (versionIds: number[], modelIds: Set<number>) => void,
    getFastSearch: () => boolean,
    getSavedPeriod: () => string,
    setSavedPeriod: (p: string) => void,
    getOnlyInstalled: () => boolean,
    getInstalledModelIds: () => Set<number>,
  }
) {
  let filters = $state<Filters>({
    search: "",
    modelType: [],
    baseModel: [],
    nsfw: false,
    sort: "Most Downloaded",
    period: "AllTime",
    eaOnly: false,
    updatedOnly: false,
  });

  let models = $state<CivitaiModel[]>([]);
  let selectedModel = $state<CivitaiModel | null>(null);
  let selectedVersion = $state<ModelVersion | null>(null);
  let modelVersions = $state<ModelVersion[]>([]);
  let popupLoading = $state(false);
  let popupReqId = 0;
  let isLoading = $state(false);
  let isLoadingMore = $state(false);
  let isFetching = $state(false);
  let error = $state<string | null>(null);
  let page = $state(1);
  let cursor = $state<string | null>(null);
  let hasMore = $state(true);
  let suggestions = $state<string[]>([]);
  let fileStatus = $state<Record<string, string>>({});

  let visibleModels = $derived.by(() => filterBrowseModels(models, {
    showNsfw: filters.nsfw,
    onlyInstalled: deps.getOnlyInstalled(),
    installedModelIds: deps.getInstalledModelIds(),
    eaOnly: filters.eaOnly,
    updatedOnly: filters.updatedOnly,
  }));

  const extrasRequested = new Set<number>();

  async function loadExtras() {
    try {
      const currentModels = models;
      const ids = currentModels.map((m) => m.id).filter((id) => id && !extrasRequested.has(id));
      if (ids.length === 0) return;
      for (let i = 0; i < ids.length; i += 7) {
        const chunk = ids.slice(i, i + 7);
        try {
          const res = await getModelExtras(chunk, { sort: filters.sort, period: filters.period, type: filters.modelType?.[0] || "", nsfw: filters.nsfw });
          const extras = res?.extras || {};
          for (const id of chunk) extrasRequested.add(id);
          if (!extras || Object.keys(extras).length === 0) continue;
          for (const m of currentModels) {
            const e = extras[String(m.id)];
            if (!e) continue;
            if (e.cosmetic && !m.cosmetic) m.cosmetic = e.cosmetic;
            if (e.baseModels && (!m.baseModels || m.baseModels.length <= 1)) m.baseModels = e.baseModels;
            if (e.avatarDeco && !m.avatarDeco) m.avatarDeco = e.avatarDeco;
            if (e.badge && !m.badge) m.badge = e.badge;
            if (e.profileBackground && !m.profileBackground) m.profileBackground = e.profileBackground;
            if (e.nameplate && !m.nameplate) m.nameplate = e.nameplate;
            m.creator = mergeCreatorFromExtras(m.creator, e.creator);
            if (e.hasBuzz) m.hasBuzz = true;
            if (e.availability) m.availability = e.availability;
            if (e.earlyAccessDeadline) m.earlyAccessDeadline = e.earlyAccessDeadline;
            if (e.publishedAt && !m.publishedAt) m.publishedAt = e.publishedAt;
            if (e.createdAt && !m.createdAt) m.createdAt = e.createdAt;
            if (e.mode && !m.mode) m.mode = e.mode;
          }
        } catch (e) { console.debug("[CivBro] extras chunk failed:", e); }
      }
    } catch (e) {
      console.debug("[CivBro] extras load failed:", e);
    }
  }

  async function fetchModels(reset = false) {
    if (isFetching) return;
    isFetching = true;
    if (reset) { page = 1; cursor = null; hasMore = true; isLoading = true; extrasRequested.clear(); }
    else { isLoadingMore = true; }

    error = null;
    const savedPeriod = deps.getSavedPeriod();
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
        earlyAccess: filters.eaOnly || undefined,
        source: filters.nsfw && deps.getApiKeyConfigured() ? "red" : "rest",
      });

      const items = (result.items || []).map((model: CivitaiModel) => ({
        ...model,
        nsfwClassificationKnown: false,
      }));
      const nextCursor = result.nextCursor;

      models = reset ? items : [...models, ...items];
      cursor = hasNextPage(nextCursor) ? String(nextCursor) : null;
      hasMore = hasNextPage(nextCursor);
      if (filters.eaOnly || filters.updatedOnly) {
        await loadExtras();
      } else {
        loadExtras();
      }
    } catch (e) {
      error = e instanceof Error ? e.message : "Failed to fetch models";
      if (reset) models = [];
    } finally {
      isLoading = false;
      isLoadingMore = false;
      isFetching = false;
      if (deps.getFastSearch() && filters.search) {
        filters.period = savedPeriod || "AllTime";
      }
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
    setThrottle(true).catch(() => {});
    try {
      const [detail, versions, extrasResult] = await Promise.all([
        getModel(model.id),
        getModelVersions(model.id),
        getModelExtras([model.id]),
      ]);
      const extras = extrasResult.extras?.[String(model.id)] || {};
      const enrichedModel = {
        ...model,
        cosmetic: extras.cosmetic ?? model.cosmetic,
        avatarDeco: extras.avatarDeco ?? model.avatarDeco,
        badge: extras.badge ?? model.badge,
        profileBackground: extras.profileBackground ?? model.profileBackground,
        nameplate: extras.nameplate ?? model.nameplate,
      };
      selectedModel = mergeModelDetail(enrichedModel, detail as CivitaiModel);
      modelVersions = (versions as any).versions || (versions as any).items || [];
      if (modelVersions.length > 0) {
        selectedVersion = modelVersions[0];
        selectVersion(modelVersions[0]);
      }
      getInstalledVersions()
        .then((r: any) => { deps.onInstalledRefreshed(r?.versionIds || [], new Set(r?.modelIds || [])); })
        .catch(() => {});
    } catch (e) {
      if (reqId === popupReqId) error = e instanceof Error ? e.message : "Failed to load model details";
    } finally {
      if (reqId === popupReqId) {
        popupLoading = false;
        setThrottle(false).catch(() => {});
      }
    }
  }

  function closeModelDetail() {
    popupReqId++;
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
    } catch (e) {
      console.debug("[CivBro] selectVersion detail failed:", e);
    }
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

  async function fetchSuggestions(query: string) {
    if (query.length < 2) { suggestions = []; return; }
    try {
      const result: any = await getSuggestions(query);
      const items = result.items || [];
      suggestions = items.map((m: any) => m.name).slice(0, 5);
    } catch {
      suggestions = [];
    }
  }

  return {
    get filters() { return filters; },
    set filters(v: Filters) { filters = v; },
    get models() { return visibleModels; },
    set models(v: CivitaiModel[]) { models = v; },
    getVisibleModels() { return visibleModels; },
    get selectedModel() { return selectedModel; },
    set selectedModel(v: CivitaiModel | null) { selectedModel = v; },
    get popupLoading() { return popupLoading; },
    get selectedVersion() { return selectedVersion; },
    set selectedVersion(v: ModelVersion | null) { selectedVersion = v; },
    get modelVersions() { return modelVersions; },
    set modelVersions(v: ModelVersion[]) { modelVersions = v; },
    get isLoading() { return isLoading; },
    set isLoading(v: boolean) { isLoading = v; },
    get isLoadingMore() { return isLoadingMore; },
    get error() { return error; },
    get page() { return page; },
    get hasMore() { return hasMore; },
    get suggestions() { return suggestions; },
    get fileStatus() { return fileStatus; },
    set fileStatus(v: Record<string, string>) { fileStatus = v; },
    getFilter(key: keyof Filters) { return filters[key]; },
    fetchModels, loadMore, openModelDetail, closeModelDetail, selectVersion,
    fetchSuggestions, loadExtras,
  };
}
