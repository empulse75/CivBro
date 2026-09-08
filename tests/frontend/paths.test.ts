import { describe, it, expect } from "vitest";
import { subdirForFile, subdirForType, imgSrc } from "@lib/paths";

const DIR_MAP: Record<string, string> = {
  Checkpoint: "Stable-diffusion",
  LORA: "Lora",
  VAE: "VAE",
  TextualInversion: "embeddings",
  Controlnet: "ControlNet",
  Upscaler: "ESRGAN",
  MotionModule: "AnimateDiff",
  AestheticGradient: "aesthetic_embeddings",
  Poses: "Poses",
  Wildcards: "wildcards",
  Other: "Other",
};

describe("subdirForType", () => {
  it("gives VAE for vae", () => expect(subdirForType("VAE", DIR_MAP)).toBe("VAE"));
  it("gives text_encoder for Text Encoder", () => expect(subdirForType("Text Encoder", DIR_MAP)).toBe("text_encoder"));
  it("gives Lora for LoCon", () => expect(subdirForType("LoCon", DIR_MAP)).toBe("Lora"));
  it("gives Lora for DoRA", () => expect(subdirForType("DoRA", DIR_MAP)).toBe("Lora"));
  it("gives embeddings for TextualInversion", () => expect(subdirForType("TextualInversion", DIR_MAP)).toBe("embeddings"));
  it("gives ControlNet for controlnet", () => expect(subdirForType("ControlNet", DIR_MAP)).toBe("ControlNet"));
  it("gives ESRGAN for Upscaler", () => expect(subdirForType("Upscaler", DIR_MAP)).toBe("ESRGAN"));
  it("routes every extended model category", () => {
    expect(subdirForType("MotionModule", DIR_MAP)).toBe("AnimateDiff");
    expect(subdirForType("AestheticGradient", DIR_MAP)).toBe("aesthetic_embeddings");
    expect(subdirForType("Poses", DIR_MAP)).toBe("Poses");
    expect(subdirForType("Wildcards", DIR_MAP)).toBe("wildcards");
    expect(subdirForType("Other", DIR_MAP)).toBe("Other");
  });
  it("falls back to dirMap", () => expect(subdirForType("Checkpoint", DIR_MAP)).toBe("Stable-diffusion"));
  it("defaults to Stable-diffusion when unknown", () => expect(subdirForType("UnknownType", DIR_MAP)).toBe("Stable-diffusion"));
  it("prefers backend dirMap over heuristics for authoritative types", () => {
    // If backend dirMap says "Other", don't let heuristics override it
    expect(subdirForType("Other", DIR_MAP)).toBe("Other");
  });
});

describe("subdirForFile", () => {
  it("keeps wildcard txt files out of text_encoder", () => {
    expect(subdirForFile("Config", "subjects.txt", "Wildcards", DIR_MAP)).toBe("wildcards");
  });

  it("recognizes explicit text-encoder filenames", () => {
    expect(subdirForFile("Model", "anima_txt.safetensors", "Checkpoint", DIR_MAP)).toBe("text_encoder");
  });
});

describe("imgSrc", () => {
  const CDN = "https://image.civitai.com";

  it("returns empty for missing img", () => expect(imgSrc(undefined, 450)).toBe(""));

  it("returns video URL unchanged", () => {
    const vid = `${CDN}/x/v.mp4`;
    expect(imgSrc({ url: vid, type: "video" }, 450)).toBe(vid);
  });

  it("strips original=true and injects width for images", () => {
    const url = `${CDN}/bucket/a/original=true/p.png`;
    const result = imgSrc({ url, type: "image" }, 450);
    expect(result).not.toContain("original=true");
    expect(result).toContain("width=450,format=webp");
  });

  it("passes through images already with width", () => {
    const url = `${CDN}/width=200/p.png`;
    expect(imgSrc({ url, type: "image" }, 450)).toBe(url);
  });
});
