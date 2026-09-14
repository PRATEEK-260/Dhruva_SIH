import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
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
