import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// During `npm run dev`, /api/* is proxied to the FastAPI backend on :8000,
// so the frontend can call fetch('/api/...') with no CORS or host config.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
