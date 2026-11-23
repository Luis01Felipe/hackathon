import { defineConfig } from "vite";

// Caminho público do app: "/" em desenvolvimento; no Docker, BASE_PATH=/editalcheck/ (proxy).
export default defineConfig({
  base: process.env.BASE_PATH || "/",
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    target: "es2022",
    chunkSizeWarningLimit: 4000,
  },
});
