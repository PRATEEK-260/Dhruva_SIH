import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // MapLibre constructs its worker with { type: "module" }; see src/shared/map/maplibre.ts.
  worker: { format: 'es' },
  // Pre-bundling maplibre-gl moves it away from its worker file and splits it
  // into two module instances, so setWorkerUrl reaches only one of them.
  optimizeDeps: { exclude: ['maplibre-gl'] },
  server: {
    // Matches deploy/Caddyfile's existing /api/* strip-prefix convention, so
    // the same relative fetch("/api/...") path works in dev (via this proxy)
    // and in a Caddy-fronted deployment without a code change.
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      '/tiles': {
        target: 'http://localhost:8001',
        rewrite: (path) => path.replace(/^\/tiles/, ''),
      },
    },
  },
})
