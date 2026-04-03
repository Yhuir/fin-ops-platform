import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";
export default defineConfig(function (_a) {
    var mode = _a.mode;
    var env = loadEnv(mode, ".", "");
    return {
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
        },
    };
});
