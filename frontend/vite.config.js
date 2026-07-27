import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue(), tailwindcss()],
  // prevent vite from obscuring rust errors
  clearScreen: false,
  server: {
    // Tauri expects a fixed port; fail if that port isn't available
    strictPort: true,
    // add connection header for tauri
    headers: {
      "Access-Control-Allow-Origin": "*",
    },
  },
  // Env variables starting with TAURI_ are exposed to tauri's source code
  envPrefix: ['VITE_', 'TAURI_'],
  build: {
    // Tauri uses chromium on Windows and WebKit on macOS and Linux
    target: "esnext",
    // don't minify for debug builds
    minify: !process.env.TAURI_DEBUG ? 'esbuild' : false,
    // produce sourcemaps for debug builds
    sourcemap: !!process.env.TAURI_DEBUG,
  },
})
