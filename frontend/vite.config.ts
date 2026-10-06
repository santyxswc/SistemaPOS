import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// La interfaz compilada queda dentro del paquete de Python: Flask la sirve y el
// computador del negocio no necesita Node.
export default defineConfig({
  plugins: [react()],
  build: { outDir: "../src/pos/presentation/web/static", emptyOutDir: true },
  server: { proxy: { "/api": "http://127.0.0.1:8000", "/health": "http://127.0.0.1:8000" } },
});
