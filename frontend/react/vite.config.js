import fs from "node:fs";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

function readHttpsConfig(env) {
  const keyPath = env.VITE_DEV_SSL_KEY;
  const certPath = env.VITE_DEV_SSL_CERT;

  if (!keyPath || !certPath) {
    return false;
  }

  if (!fs.existsSync(keyPath) || !fs.existsSync(certPath)) {
    throw new Error(
      `HTTPS is enabled but the certificate files were not found. Checked key="${keyPath}" cert="${certPath}".`
    );
  }

  return {
    key: fs.readFileSync(keyPath),
    cert: fs.readFileSync(certPath)
  };
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const https = readHttpsConfig(env);

  return {
    base: "/",
    plugins: [react()],
    server: {
      host: "0.0.0.0",
      port: 5173,
      https,
      proxy: {
        "/api": {
          target: "http://localhost:8000",
          changeOrigin: true
        }
      }
    }
  };
});
