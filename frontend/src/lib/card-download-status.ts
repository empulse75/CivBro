export type CardDownloadStatus =
  | "idle"
  | "busy"
  | "active"
  | "completed"
  | "failed"
  | "installed"
  | "buzzLocked"
  | "buzzUnlocked"
  | "apikeyLocked";

interface CardDownloadStatusInput {
  activeStatus: string | null;
  busy: boolean;
  installed: boolean;
  buzzRequired: boolean;
  buzzUnlocked: boolean;
  earlyAccess: boolean;
  modelNsfw: boolean;
  nsfwBrowsing: boolean;
  apiKeyConfigured: boolean;
}

export function getCardDownloadStatus(input: CardDownloadStatusInput): CardDownloadStatus {
  if (input.activeStatus === "downloading" || input.activeStatus === "pending" || input.activeStatus === "queued") {
    return "active";
  }
  if (input.activeStatus === "completed") return "completed";
  if (input.activeStatus === "failed") return "failed";
  if (input.busy) return "busy";
  if (input.installed) return "installed";
  if (input.buzzRequired && input.buzzUnlocked) return "buzzUnlocked";
  if (input.buzzRequired || input.earlyAccess) return "buzzLocked";
  if (input.modelNsfw && input.nsfwBrowsing && !input.apiKeyConfigured) return "apikeyLocked";
  return "idle";
}
