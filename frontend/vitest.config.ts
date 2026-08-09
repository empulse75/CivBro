import { defineConfig } from "vitest/config";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const extLib = resolve(__dirname, "../../Civbro/frontend/src/lib");

export default defineConfig({
  test: {
    include: ["../../tests/frontend/**/*.test.ts"],
  },
  resolve: {
    alias: {
      "@lib": extLib,
    },
  },
});
