import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development the API runs on :8080 (make dev-api). Forwarding /api keeps the
// browser on a single origin, exactly like in production where FastAPI serves both.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: { "/api": "http://localhost:8080" },
  },
});
