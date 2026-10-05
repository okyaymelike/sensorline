import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The read API runs on :8080; proxy /api in dev so the browser talks same-origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8080",
        changeOrigin: true,
      },
    },
  },
});
