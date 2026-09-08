import { describe, expect, it } from "vitest";
import { filterBrowseModels, hasNextPage, isNsfwImage } from "@lib/browse";
import type { CivitaiModel } from "@lib/stores/types";

function model(id: number, overrides: Partial<CivitaiModel> = {}): CivitaiModel {
  return {
    id,
    name: `Model ${id}`,
    type: "Checkpoint",
    nsfw: false,
    ...overrides,
  };
}

const defaults = {
  showNsfw: false,
  onlyInstalled: false,
  installedModelIds: new Set<number>(),
  eaOnly: false,
  updatedOnly: false,
};

describe("filterBrowseModels", () => {
  it("returns no models when only-installed is enabled with an empty installation", () => {
    expect(filterBrowseModels([model(1)], { ...defaults, onlyInstalled: true })).toEqual([]);
  });

  it("retains raw models so later extras can make an early-access model visible", () => {
    const models = [model(1)];
    const options = { ...defaults, eaOnly: true };

    expect(filterBrowseModels(models, options)).toEqual([]);
    models[0].availability = "EarlyAccess";
    expect(filterBrowseModels(models, options)).toEqual(models);
  });

  it("filters updated models against a stable clock", () => {
    const now = Date.parse("2026-08-03T12:00:00Z");
    const models = [
      model(1, { publishedAt: "2026-08-02T12:00:00Z" }),
      model(2, { publishedAt: "2026-07-30T12:00:00Z" }),
    ];

    expect(filterBrowseModels(models, { ...defaults, updatedOnly: true, now })).toEqual([models[0]]);
  });

  it("hides a model whose preview is mature when NSFW is disabled", () => {
    const maturePreview = model(1, {
      nsfw: false,
      images: [{ id: 1, url: "preview.webp", type: "image", width: 512, height: 768, nsfw: "Mature", nsfwLevel: 4 }],
    });

    expect(filterBrowseModels([maturePreview], defaults)).toEqual([]);
    expect(filterBrowseModels([maturePreview], { ...defaults, showNsfw: true })).toEqual([maturePreview]);
  });

  it("hides soft and nested NSFW previews when NSFW is disabled", () => {
    const softPreview = model(1, {
      images: [{ id: 1, url: "soft.webp", type: "image", width: 512, height: 768, nsfw: "Soft", nsfwLevel: 2 }],
    });
    const nestedPreview = model(2, {
      modelVersions: [{
        id: 20,
        name: "v1",
        images: [{ id: 2, url: "nested.webp", type: "image", width: 512, height: 768, nsfw: "Mature", nsfwLevel: 4 }],
      }],
    });

    expect(filterBrowseModels([softPreview, nestedPreview], defaults)).toEqual([]);
  });

  it("keeps unclassified slim results out of an SFW grid", () => {
    const unknown = model(1, { nsfwClassificationKnown: false });
    expect(filterBrowseModels([unknown], defaults)).toEqual([]);
    expect(filterBrowseModels([unknown], { ...defaults, showNsfw: true })).toEqual([unknown]);
  });

  it("keeps a full page of safe card previews visible before extras arrive", () => {
    const safeResults = Array.from({ length: 20 }, (_, index) => model(index + 1, {
      nsfwClassificationKnown: false,
      images: [{
        id: index + 1,
        url: `safe-${index + 1}.webp`,
        type: "image",
        width: 512,
        height: 768,
        nsfw: "PG",
        nsfwLevel: 1,
      }],
    }));

    expect(filterBrowseModels(safeResults, defaults)).toHaveLength(20);
  });

});

describe("hasNextPage", () => {
  it("follows the server cursor even when the visible page is empty", () => {
    expect(hasNextPage("next-page")).toBe(true);
    expect(hasNextPage(null)).toBe(false);
  });
});

describe("isNsfwImage", () => {
  it("uses the same soft-content threshold as browse filtering", () => {
    expect(isNsfwImage({ nsfwLevel: 2, nsfw: "Soft" })).toBe(true);
    expect(isNsfwImage({ nsfwLevel: 1, nsfw: "PG" })).toBe(false);
  });
});
