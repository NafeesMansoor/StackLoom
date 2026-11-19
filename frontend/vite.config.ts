import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: `STACKLOOM_API=http://127.0.0.1:<port> pnpm dev` proxies /api to a running dashboard.
export default defineConfig({
  plugins: [react()],
  base: "/",
  build: { outDir: "../stackloom/web/dist", emptyOutDir: true, sourcemap: false, target: "es2020" },
  server: {
    host: "127.0.0.1",
    proxy: process.env.STACKLOOM_API ? { "/api": process.env.STACKLOOM_API } : undefined,
  },
});
