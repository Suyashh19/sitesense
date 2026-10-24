import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// The project-root .env is shared with the backend; only VITE_* variables reach the browser.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '..', '')
  return {
    plugins: [react()],
    envDir: '..',
    server: { port: 5173, proxy: { '/api': env.DEV_API_PROXY || 'http://127.0.0.1:8000' } },
  }
})
