import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";
function normalizeBasePath(value) {
    var trimmed = String(value !== null && value !== void 0 ? value : "/").trim();
    if (trimmed.length === 0 || trimmed === "/") {
        return "/";
    }
    var withLeadingSlash = trimmed.charAt(0) === "/" ? trimmed : "/".concat(trimmed);
    return withLeadingSlash.slice(-1) === "/" ? withLeadingSlash : "".concat(withLeadingSlash, "/");
}
export default defineConfig(function (_a) {
    var mode = _a.mode;
    var env = loadEnv(mode, ".", "");
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
                    bypass: function (req) {
                        var _a;
                        var requestPath = (_a = req.url) !== null && _a !== void 0 ? _a : "";
                        if (/^\/imports\/(files|templates|batches|preview|confirm)(\/|$)/.test(requestPath)) {
                            return undefined;
                        }
                        return "/index.html";
                    },
                },
                "/fin-ops-api": {
                    target: env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8001",
                    changeOrigin: true,
                    rewrite: function (path) { return path.replace(/^\/fin-ops-api/, ""); },
                },
            },
        },
        test: {
            environment: "jsdom",
            globals: true,
            include: ["src/test/**/*.{test,spec}.{ts,tsx}"],
            exclude: ["node_modules", "dist", "e2e"],
            setupFiles: "./src/test/setup.ts",
            testTimeout: 15000,
            fileParallelism: false,
            maxWorkers: 1,
        },
    };
});
