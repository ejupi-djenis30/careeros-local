import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    watch: {
      ignored: ['**/src-tauri/target/**', '**/src-tauri/binaries/**'],
    },
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/setupTests.js',
    // Cap parallel JSDOM workers so interaction-heavy suites stay deterministic on shared runners.
    maxWorkers: 4,
    // V8 instrumentation makes interaction-heavy canvas/profile tests slower on CI.
    testTimeout: 15_000,
    coverage: {
      provider: 'v8',
      thresholds: {
        // Ratchet from the measured full-suite baseline; raise these as coverage grows.
        statements: 69,
        branches: 63,
        functions: 58,
        lines: 77,
      },
    },
  },
})
