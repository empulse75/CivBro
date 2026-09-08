import { describe, expect, it } from "vitest";
import { mergeCreatorFromExtras, mergeModelDetail } from "@lib/model-detail";
import type { CivitaiModel } from "@lib/stores/types";

function model(overrides: Partial<CivitaiModel> = {}): CivitaiModel {
  return {
    id: 1318945,
    name: "One obsession",
    type: "Checkpoint",
    nsfw: false,
    ...overrides,
  };
}

describe("mergeModelDetail", () => {
  it("preserves creator presentation from the enriched result card", () => {
    const card = model({
      avatarDeco: "avatar-decoration.png",
      badge: "badge.png",
      profileBackground: { url: "profile-background.webm", type: "video" },
      nameplate: { color: "#abcdef" },
      cosmetic: { cssFrame: "linear-gradient(90deg, #fff, #000)", glow: true },
    });
    const detail = model({
      creator: { username: "maxfeifei8", image: "avatar.jpeg" },
      avatarDeco: undefined,
      badge: undefined,
      profileBackground: undefined,
      nameplate: undefined,
      cosmetic: null,
    });

    expect(mergeModelDetail(card, detail)).toMatchObject({
      avatarDeco: "avatar-decoration.png",
      badge: "badge.png",
      profileBackground: { url: "profile-background.webm", type: "video" },
      nameplate: { color: "#abcdef" },
      cosmetic: { cssFrame: "linear-gradient(90deg, #fff, #000)", glow: true },
    });
  });

  it("prefers fresh detail values when present", () => {
    const card = model({ badge: "old.png", availability: "EarlyAccess" });
    const detail = model({ badge: "new.png", availability: "Public" });

    expect(mergeModelDetail(card, detail)).toMatchObject({ badge: "new.png", availability: "Public" });
  });
});

describe("mergeCreatorFromExtras", () => {
  it("fills a missing REST uploader from exact-id extras", () => {
    expect(mergeCreatorFromExtras(
      { username: "", image: "" },
      { username: "civitai", image: "avatar.webp" },
    )).toEqual({ username: "civitai", image: "avatar.webp" });
  });

  it("does not overwrite an existing uploader", () => {
    expect(mergeCreatorFromExtras(
      { username: "original", image: "original.webp" },
      { username: "replacement", image: "replacement.webp" },
    )).toEqual({ username: "original", image: "original.webp" });
  });
});
