/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // 127.0.0.1, not localhost: the backend binds 127.0.0.1 (application.yml), and on
    // machines where something else holds ::1:8080 (e.g. Docker) "localhost" can resolve
    // there first and the proxy misses the jar.
    proxy: { '/api': 'http://127.0.0.1:8080' },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    globals: true,
  },
})
