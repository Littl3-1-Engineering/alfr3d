import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import svgr from 'vite-plugin-svgr'
import compression from 'vite-plugin-compression'

export default defineConfig({
  resolve: {
    alias: {
      'lottie-react': 'lottie-react/build/index.es.js',
    },
  },
  plugins: [
    react(),
    svgr(),
    compression({ algorithm: 'gzip', ext: '.gz' }),
    compression({ algorithm: 'brotliCompress', ext: '.br' })
  ],
  build: {
    chunkSizeWarningLimit: 800,
    rollupOptions: {
    },
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            {
              name: 'lucide',
              test: /node_modules[\\/]lucide-react/,
              priority: 30,
            },
            {
              name: 'vendor',
              test(id) {
                if (id.includes('/node_modules/react-leaflet/')) return false;
                return /node_modules[\\/](react|react-dom|react-router|react-is|react-redux|react-lifecycles-compat|react-modal|scheduler)/.test(id);
              },
              priority: 30,
            },
            {
              name: 'motion',
              test: /node_modules[\\/]framer-motion/,
              priority: 25,
            },
            {
              name: 'charts',
              test: /node_modules[\\/](recharts|d3)/,
              priority: 25,
            },
            {
              name: 'maps',
              test: /node_modules[\\/](leaflet[\\/]|react-leaflet[\\/])/,
              priority: 20,
            },
            {
              name: 'node_modules',
              test: /node_modules/,
              priority: 5,
            },
          ],
        },
      },
    },
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
