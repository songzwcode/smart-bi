import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
// https://vitejs.dev/config/
export default defineConfig({
    plugins: [react()],
    base: './', // relative paths so PyWebView file:// works
    build: {
        outDir: '../backend/static', // build output goes where FastAPI serves from
        emptyOutDir: true,
        sourcemap: false,
        chunkSizeWarningLimit: 1500, // Monaco is big; bump warning threshold
    },
    server: {
        port: 5173,
        proxy: {
            '/api': {
                target: 'http://127.0.0.1:17890',
                changeOrigin: false,
            },
        },
    },
    optimizeDeps: {
        include: ['react', 'react-dom', 'plotly.js', 'zustand'],
    },
});
