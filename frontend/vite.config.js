import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    // En desarrollo, /api va al backend local; en producción Caddy lo enruta.
    proxy: { '/api': 'http://localhost:8000' },
  },
})
