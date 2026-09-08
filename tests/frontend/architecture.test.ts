/**
 * Static architecture guards (ADR-0002). These are deliberately the only
 * source-reading assertions in the suite: dependency *direction* cannot be
 * observed at runtime, so it is checked here. Anything that can be asserted
 * through behaviour belongs in the behavioural suites instead — an earlier
 * version of this file also pinned CSS pixel values and class names, which
 * broke on every restyle without ever catching a defect.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const libDir = resolve(import.meta.dirname, "../../frontend/src/lib");

function source(path: string): string {
  return readFileSync(resolve(libDir, path), "utf8");
}

describe("frontend dependency direction", () => {
  it("keeps domain contracts independent of adapters and state", () => {
    expect(source("stores/types.ts")).not.toMatch(
      /^\s*(?:import|export\s+type\s+\{[^}]*\}\s+from)\b/m,
    );
  });

  it("keeps the HTTP adapter independent of the state implementation", () => {
    expect(source("api.ts")).not.toMatch(/from\s+["'].+stores\.svelte(?:\.ts)?["']/);
  });

  it("composes createAppState from the four domain store modules", () => {
    const s = source("stores.svelte.ts");
    expect(s).toMatch(/from\s+[".']\.\/browseStore\.svelte\.ts["']/);
    expect(s).toMatch(/from\s+[".']\.\/downloadStore\.svelte\.ts["']/);
    expect(s).toMatch(/from\s+[".']\.\/settingsStore\.svelte\.ts["']/);
    expect(s).toMatch(/from\s+[".']\.\/localStore\.svelte\.ts["']/);
  });
});
