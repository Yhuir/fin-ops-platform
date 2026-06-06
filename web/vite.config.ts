import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";

function normalizeBasePath(value: string | undefined) {
  const trimmed = String(value ?? "/").trim();
  if (trimmed.length === 0 || trimmed === "/") {
    return "/";
  }
  const withLeadingSlash = trimmed.charAt(0) === "/" ? trimmed : `/${trimmed}`;
  return withLeadingSlash.slice(-1) === "/" ? withLeadingSlash : `${withLeadingSlash}/`;
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");

  return {
    base: normalizeBasePath(env.VITE_APP_BASE_PATH),
    plugins: [react(), tailwindcss()],
    server: {
      proxy: {
        "/api": {
          target: env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8001",
          changeOrigin: true,
        },
        "/imports": {
          target: env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8001",
          changeOrigin: true,
          bypass: (req) => {
            const requestPath = req.url ?? "";
            if (/^\/imports\/(files|templates|batches|preview|confirm)(\/|$)/.test(requestPath)) {
              return undefined;
            }
            return "/index.html";
          },
        },
        "/fin-ops-api": {
          target: env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8001",
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/fin-ops-api/, ""),
        },
      },
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: "./src/test/setup.ts",
      testTimeout: 15000,
    },
  };
});
