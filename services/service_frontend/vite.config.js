import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import svgr from 'vite-plugin-svgr'
import compression from 'vite-plugin-compression'

export default defineConfig({
  plugins: [
    react(),
    svgr(),
    compression({ algorithm: 'gzip', ext: '.gz' }),
    compression({ algorithm: 'brotliCompress', ext: '.br' })
  ],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor': ['react', 'react-dom', 'react-router-dom'],
          'motion': ['framer-motion'],
          'charts': ['recharts', 'd3'],
          'maps': ['leaflet', 'react-leaflet'],
          'lucide': ['lucide-react']
        }
      }
    },
    chunkSizeWarningLimit: 600
  },
  server: {
    host: '0.0.0.0',
    port: 8000,
    proxy: {
      '/api': {
        target: 'http://localhost:5001',
        changeOrigin: true,
      },
    },
  },
})
