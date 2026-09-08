import { reorderDownloads as apiReorder } from "./api";
import { filterBrowseModels } from "./browse";
import { createBrowseStore } from "./browseStore.svelte.ts";
import { createDownloadStore } from "./downloadStore.svelte.ts";
import { createSettingsStore } from "./settingsStore.svelte.ts";
import { createLocalStore } from "./localStore.svelte.ts";
export type {
  CivitaiModel, ModelDependency, ModelVersion, ModelFile, ModelImage,
  LocalModel, DownloadItem, Filters, FrontendConfig
} from "./stores/types";

import type { CivitaiModel, ModelDependency, ModelVersion, ModelFile, ModelImage, LocalModel, DownloadItem, Filters, FrontendConfig } from "./stores/types";

export function createAppState() {
  let activeTab = $state<"browse" | "local">("browse");
  let unlockedBuzzModelIds = $state<Set<number>>(new Set());
  let downloadQueue = $state<DownloadItem[]>([]);

  const local = createLocalStore();
  const settings = createSettingsStore();
  const browse = createBrowseStore({
    getApiKeyConfigured: () => settings.apiKeyConfigured,
    onDownloadCompleted: (modelId: number) => {
      unlockedBuzzModelIds = new Set([...unlockedBuzzModelIds, modelId]);
    },
    onInstalledRefreshed: (versionIds: number[], modelIds: Set<number>) => {
      local.installedVersionIds = versionIds;
      local.installedModelIds = modelIds;
    },
    getFastSearch: () => settings.fastSearch,
    getSavedPeriod: () => settings.savedPeriod,
    setSavedPeriod: (p: string) => { settings.savedPeriod = p; },
    getOnlyInstalled: () => settings.onlyInstalled,
    getInstalledModelIds: () => local.installedModelIds,
  });
  const downloads = createDownloadStore({
    onDownloadCompleted: (modelId: number) => {
      unlockedBuzzModelIds = new Set([...unlockedBuzzModelIds, modelId]);
    },
    getInstalledRefresher: () => () => local.refreshInstalled(),
    getFileStatusRefresher: () => null,
    getSelectedVersionId: () => browse.selectedVersion?.id,
  });

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

  async function loadSettingsWrapper() {
    await settings.loadSettings(
      (s: any) => {
        browse.filters = {
          ...browse.filters,
          modelType: parseSettingArr(s.defaultModelTypes, s.defaultModelType),
          baseModel: parseSettingArr(s.defaultBaseModels, s.defaultBaseModel),
          nsfw: s.showNsfw ?? false,
          sort: s.defaultSort ?? "Most Downloaded",
          period: s.defaultPeriod ?? "AllTime",
          eaOnly: s.eaOnly ?? false,
          updatedOnly: s.updatedOnly ?? false,
        };
      },
      (ids: Set<number>) => { unlockedBuzzModelIds = ids; },
    );
    await local.refreshInstalled();
    downloads.hydrateDownloadQueue(downloads.downloads, downloads.downloadOrder);
    settings.loadConfig();
    settings.loadLicenseStatus();
  }

  function saveSettingsWrapper() {
    settings.saveSettings({
      nsfw: browse.filters.nsfw,
      modelType: browse.filters.modelType,
      baseModel: browse.filters.baseModel,
      sort: browse.filters.sort,
      period: browse.filters.period,
      eaOnly: browse.filters.eaOnly,
      updatedOnly: browse.filters.updatedOnly,
    }, unlockedBuzzModelIds);
  }

  function setFilter(key: keyof Filters, value: string | boolean | string[]) {
    (browse.filters as unknown as Record<string, unknown>)[key] = value;
    saveSettingsWrapper();
  }

  function triggerSearch() {
    if (settings.fastSearch && browse.filters.search) {
      settings.savedPeriod = browse.filters.period;
      browse.filters = { ...browse.filters, period: "AllTime" };
    }
    browse.fetchModels(true);
  }

  function toggleModelType(value: string) {
    if (!value) { browse.filters = { ...browse.filters, modelType: [] }; }
    else {
      const idx = browse.filters.modelType.indexOf(value);
      if (idx >= 0) browse.filters = { ...browse.filters, modelType: browse.filters.modelType.filter(v => v !== value) };
      else browse.filters = { ...browse.filters, modelType: [...browse.filters.modelType, value] };
    }
    saveSettingsWrapper();
  }

  function toggleBaseModel(value: string) {
    if (!value) { browse.filters = { ...browse.filters, baseModel: [] }; }
    else {
      const idx = browse.filters.baseModel.indexOf(value);
      if (idx >= 0) browse.filters = { ...browse.filters, baseModel: browse.filters.baseModel.filter(v => v !== value) };
      else browse.filters = { ...browse.filters, baseModel: [...browse.filters.baseModel, value] };
    }
    saveSettingsWrapper();
  }

  function clearFilters() {
    browse.filters = {
      search: "",
      modelType: [],
      baseModel: [],
      nsfw: false,
      sort: "Most Downloaded",
      period: "AllTime",
      eaOnly: false,
      updatedOnly: false,
    };
    saveSettingsWrapper();
  }

  function cleanup() {
    settings.cleanup();
    downloads.cleanup();
  }

  return {
    cleanup,
    get filters() { return browse.filters; },
    set filters(v: Filters) { browse.filters = v; },
    get models() { return browse.models; },
    set models(v: CivitaiModel[]) { browse.models = v; },
    get visibleModels() { return browse.models; },
    get localModels() { return local.localModels; },
    set localModels(v: LocalModel[]) { local.localModels = v; },
    get selectedModel() { return browse.selectedModel; },
    set selectedModel(v: CivitaiModel | null) { browse.selectedModel = v; },
    get popupLoading() { return browse.popupLoading; },
    get selectedVersion() { return browse.selectedVersion; },
    set selectedVersion(v: ModelVersion | null) { browse.selectedVersion = v; },
    get modelVersions() { return browse.modelVersions; },
    set modelVersions(v: ModelVersion[]) { browse.modelVersions = v; },
    get activeTab() { return activeTab; },
    set activeTab(v: "browse" | "local") { activeTab = v; },
    get isLoading() { return browse.isLoading; },
    set isLoading(v: boolean) { browse.isLoading = v; },
    get isLoadingMore() { return browse.isLoadingMore; },
    get error() { return browse.error; },
    set error(v: string | null) { browse.error = v; },
    get page() { return browse.page; },
    get hasMore() { return browse.hasMore; },
    get suggestions() { return browse.suggestions; },
    get downloadQueue() { return downloadQueue; },
    set downloadQueue(v: DownloadItem[]) { downloadQueue = v; },
    get installedVersionIds() { return local.installedVersionIds; },
    set installedVersionIds(v: number[]) { local.installedVersionIds = v; },
    get installedModelIds() { return local.installedModelIds; },
    set installedModelIds(v: Set<number>) { local.installedModelIds = v; },
    get onlyInstalled() { return settings.onlyInstalled; },
    set onlyInstalled(v: boolean) { settings.onlyInstalled = v; },
    get fastSearch() { return settings.fastSearch; },
    set fastSearch(v: boolean) { settings.fastSearch = v; },
    get fileStatus() { return browse.fileStatus; },
    set fileStatus(v: Record<string, string>) { browse.fileStatus = v; },
    get downloads() { return downloads.downloads; },
    set downloads(v: typeof downloads.downloads) { downloads.downloads = v; },
    get downloadOrder() { return downloads.downloadOrder; },
    set downloadOrder(v: string[]) { downloads.downloadOrder = v; },
    get activeDownloads() { return downloads.activeDownloads; },
    get hasActiveDownloads() { return downloads.hasActiveDownloads; },
    get nsfwBlurEnabled() { return settings.nsfwBlurEnabled; },
    set nsfwBlurEnabled(v: boolean) { settings.nsfwBlurEnabled = v; },
    get apiKey() { return settings.apiKey; },
    set apiKey(v: string) { settings.apiKey = v; },
    get apiKeyConfigured() { return settings.apiKeyConfigured; },
    get apiKeyValid() { return settings.apiKeyValid; },
    set apiKeyValid(v: boolean | null) { settings.apiKeyValid = v; },
    get licenseActive() { return settings.licenseActive; },
    get settingsLoaded() { return settings.settingsLoaded; },
    set settingsLoaded(v: boolean) { settings.settingsLoaded = v; },
    get config() { return settings.config; },
    get unlockedBuzzModelIds() { return unlockedBuzzModelIds; },

    loadSettings: loadSettingsWrapper,
    loadConfig: () => settings.loadConfig(),
    saveSettings: saveSettingsWrapper,
    validateAndSaveKey: (k: string) => settings.validateAndSaveKey(k),
    ingestLicense: (k: string) => settings.ingestLicense(k),
    fetchModels: (reset?: boolean) => browse.fetchModels(reset),
    loadMore: () => browse.loadMore(),
    openModelDetail: (m: CivitaiModel) => browse.openModelDetail(m),
    closeModelDetail: () => browse.closeModelDetail(),
    selectVersion: (v: ModelVersion) => browse.selectVersion(v),
    refreshLocalModels: () => local.refreshLocalModels(),
    fetchSuggestions: (q: string) => browse.fetchSuggestions(q),
    setFilter, clearFilters, triggerSearch, toggleModelType, toggleBaseModel,
    queueDownload: (params: any) => downloads.queueDownload(params),
    pollDownloads: () => downloads.pollDownloads(),
    refreshInstalled: () => local.refreshInstalled(),
    reorderDownloads: (a: number, b: number) => downloads.reorderDownloads(a, b),
  };
}

export const appState = createAppState();
