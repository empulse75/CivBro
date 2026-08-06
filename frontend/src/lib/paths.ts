/** Map a Civitai type string or file name to its WebUI models subdirectory.
 *  dirMap (from backend config) is authoritative — checked first.
 *  String-matching heuristics are a fallback for filename-based detection. */
export function subdirForType(t: string, dirMap: Record<string, string>): string {
  const backendDir = dirMap[t];
  if (backendDir) return backendDir;
  const s = (t || "").toLowerCase();
  if (s.includes("vae")) return "VAE";
  if (s.includes("encoder") || s === "te") return "text_encoder";
  if (s.includes("lora") || s.includes("locon") || s.includes("dora")) return "Lora";
  if (s.includes("embed") || s.includes("textualinversion")) return "embeddings";
  if (s.includes("controlnet")) return "ControlNet";
  if (s.includes("upscal") || s.includes("esrgan")) return "ESRGAN";
  return "Stable-diffusion";
}

export function subdirForFile(
  fileType: string,
  fileName: string,
  modelType: string,
  dirMap: Record<string, string>,
): string {
  const byType = subdirForType(fileType, dirMap);
  if (byType !== "Stable-diffusion") return byType;
  const name = (fileName || "").toLowerCase();
  if (/(^|[_\-.])vae([_\-.]|$)/.test(name)) return "VAE";
  if (/text.?encoder|(^|[_\-.])te([_\-.]|$)|(^|[_-])txt([_\-.]|$)|t5xxl|clip[_\-]?[lg]/.test(name)) return "text_encoder";
  return dirMap[modelType] || byType;
}

export function imgSrc(img: { url?: string; type?: string } | undefined, w = 600): string {
  const u = img?.url || "";
  if (!u) return "";
  if (img?.type === "video") return u;
  let r = u.replace("/original=true/", "/");
  if (!r.includes("/width=")) {
    const b = r.includes("?") ? r.split("?")[0] : r;
    r = b + `/width=${w},format=webp`;
  }
  return r;
}
