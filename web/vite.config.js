import react from "@vitejs/plugin-react";
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
        plugins: [react()],
        server: {
            proxy: {
                "/api": {
                    target: env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8001",
                    changeOrigin: true,
                },
                "/imports": {
                    target: env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8001",
                    changeOrigin: true,
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
