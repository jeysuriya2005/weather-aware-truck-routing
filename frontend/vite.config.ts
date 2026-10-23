import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // In development, /api calls are proxied to the local Django server,
    // so the browser never needs to know the backend origin.
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
