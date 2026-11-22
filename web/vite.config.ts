import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [
    react(),
    {
      name: "explicit-local-demo",
      configureServer(server) {
        // Opt-in development convenience only; never bundled into production assets.
        server.middlewares.use("/api/demo-session", (req, res) => {
          res.setHeader("Cache-Control", "no-store");
          res.setHeader("Content-Type", "application/json");
          if (req.method !== "GET" || !process.env.EPOCH_DEMO_TOKEN) {
            res.statusCode = 404;
            res.end("{}");
            return;
          }
          res.end(JSON.stringify({ token: process.env.EPOCH_DEMO_TOKEN }));
        });
      },
    },
  ],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: process.env.EPOCH_API_TARGET || "http://127.0.0.1:8000",
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
