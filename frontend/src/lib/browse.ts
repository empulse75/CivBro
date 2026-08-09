import type { CivitaiModel } from "./stores/types";

export interface BrowseFilterOptions {
  showNsfw: boolean;
  onlyInstalled: boolean;
  installedModelIds: ReadonlySet<number>;
  eaOnly: boolean;
  updatedOnly: boolean;
  now?: number;
}

const UPDATED_WINDOW_MS = 48 * 60 * 60 * 1000;

function isEarlyAccess(model: CivitaiModel, now: number): boolean {
  if (model.availability === "EarlyAccess" || model.hasBuzz) return true;
  if (!model.earlyAccessDeadline) return false;
  const deadline = Date.parse(model.earlyAccessDeadline);
  return Number.isFinite(deadline) && deadline > now;
}

export function isNsfwImage(image: { nsfwLevel?: number; nsfw?: string }): boolean {
  if ((image.nsfwLevel ?? 1) > 1) return true;
  const label = (image.nsfw || "").trim().toLowerCase();
  return label !== "" && label !== "none" && label !== "pg";
}

function previewImages(model: CivitaiModel) {
  return [
    ...(model.images || []),
    ...(model.modelVersions || []).flatMap((version) => version.images || []),
  ];
}

function hasNsfwPreview(model: CivitaiModel): boolean {
  return previewImages(model).some(isNsfwImage);
}

function wasRecentlyUpdated(model: CivitaiModel, now: number): boolean {
  if (!model.publishedAt) return false;
  const publishedAt = Date.parse(model.publishedAt);
  return Number.isFinite(publishedAt)
    && publishedAt <= now
    && now - publishedAt <= UPDATED_WINDOW_MS;
}

export function filterBrowseModels(
  models: CivitaiModel[],
  options: BrowseFilterOptions,
): CivitaiModel[] {
  const now = options.now ?? Date.now();
  return models.filter((model) => {
    if (!options.showNsfw && model.nsfwClassificationKnown === false && previewImages(model).length === 0) return false;
    if (!options.showNsfw && (model.nsfw || hasNsfwPreview(model))) return false;
    if (options.onlyInstalled && !options.installedModelIds.has(model.id)) return false;
    if (options.eaOnly && !isEarlyAccess(model, now)) return false;
    if (options.updatedOnly && !wasRecentlyUpdated(model, now)) return false;
    return true;
  });
}

export function hasNextPage(cursor: unknown): boolean {
  return cursor !== null && cursor !== undefined && cursor !== "";
}
