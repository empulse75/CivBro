import { describe, expect, it } from "vitest";
import { getCardDownloadStatus } from "@lib/card-download-status";

const defaults = {
  activeStatus: null,
  busy: false,
  installed: false,
  buzzRequired: false,
  buzzUnlocked: false,
  earlyAccess: false,
  nsfwBrowsing: true,
  apiKeyConfigured: false,
};

describe("getCardDownloadStatus", () => {
  it("does not lock a public SFW model returned by an NSFW search", () => {
    expect(getCardDownloadStatus({ ...defaults, modelNsfw: false })).toBe("idle");
  });

  it("locks an NSFW model when its required API key is missing", () => {
    expect(getCardDownloadStatus({ ...defaults, modelNsfw: true })).toBe("apikeyLocked");
  });

  it("does not API-lock an NSFW model when a key is configured", () => {
    expect(getCardDownloadStatus({ ...defaults, modelNsfw: true, apiKeyConfigured: true })).toBe("idle");
  });

  it("preserves Buzz-lock precedence", () => {
    expect(getCardDownloadStatus({ ...defaults, modelNsfw: true, buzzRequired: true })).toBe("buzzLocked");
  });

  it("shows a purchased Buzz model as unlocked until it is installed", () => {
    expect(getCardDownloadStatus({ ...defaults, buzzRequired: true, buzzUnlocked: true })).toBe("buzzUnlocked");
  });
});
