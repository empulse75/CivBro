import { getInstalledVersions, getLocalModels } from "./api";
import type { LocalModel } from "./stores/types";

export function createLocalStore() {
  let installedVersionIds = $state<number[]>([]);
  let installedModelIds = $state<Set<number>>(new Set());
  let localModels = $state<LocalModel[]>([]);
  let fileStatus = $state<Record<string, string>>({});

  async function refreshInstalled() {
    try {
      const r = await getInstalledVersions();
      installedVersionIds = r?.versionIds || [];
      installedModelIds = new Set(r?.modelIds || []);
    } catch (e) {
      console.debug("[CivBro] refreshInstalled failed:", e);
    }
  }

  function onInstalledRefreshed(versionIds: number[], modelIds: Set<number>) {
    installedVersionIds = versionIds;
    installedModelIds = modelIds;
  }

  async function refreshLocalModels() {
    try {
      const result = (await getLocalModels()) as { items?: LocalModel[] };
      localModels = result?.items || [];
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to load local models";
    }
  }

  function setFileStatus(fs: Record<string, string>) {
    fileStatus = fs;
  }

  return {
    get installedVersionIds() { return installedVersionIds; },
    set installedVersionIds(v: number[]) { installedVersionIds = v; },
    get installedModelIds() { return installedModelIds; },
    set installedModelIds(v: Set<number>) { installedModelIds = v; },
    get localModels() { return localModels; },
    set localModels(v: LocalModel[]) { localModels = v; },
    get fileStatus() { return fileStatus; },
    set fileStatus(v: Record<string, string>) { fileStatus = v; },
    refreshInstalled, onInstalledRefreshed, refreshLocalModels, setFileStatus,
  };
}
