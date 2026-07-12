import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Proxy al Atlas OS Bridge (127.0.0.1:7341, ADR-058) para evitar CORS.
// La UI habla SIEMPRE con rutas relativas /api/*.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:7341",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
      "/api-ws": {
        target: "ws://127.0.0.1:7341",
        ws: true,
        rewrite: (path) => path.replace(/^\/api-ws/, ""),
      },
    },
  },
  build: { outDir: "dist", sourcemap: true },
});
