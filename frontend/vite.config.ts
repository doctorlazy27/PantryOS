import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(() => {
  const apiUrl = process.env.VITE_API_URL
  return {
    plugins: [react()],
    server: apiUrl ? {
      proxy: {
        '/api': {
          target: apiUrl,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ''),
        },
      },
    } : undefined,
  }
})