import type { CivitaiModel } from "./stores/types";

type Creator = CivitaiModel["creator"];

export function mergeCreatorFromExtras(current: Creator, extra: Creator): Creator {
  return current?.username ? current : extra?.username ? extra : current;
}

export function mergeModelDetail(card: CivitaiModel, detail: CivitaiModel): CivitaiModel {
  return {
    ...card,
    ...detail,
    cosmetic: detail.cosmetic ?? card.cosmetic,
    avatarDeco: detail.avatarDeco ?? card.avatarDeco,
    badge: detail.badge ?? card.badge,
    profileBackground: detail.profileBackground ?? card.profileBackground,
    nameplate: detail.nameplate ?? card.nameplate,
    hasBuzz: detail.hasBuzz ?? card.hasBuzz ?? false,
    availability: detail.availability ?? card.availability,
  };
}
