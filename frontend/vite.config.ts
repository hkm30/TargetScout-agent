import { readFileSync } from "fs";
import { execSync } from "child_process";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const pkg = JSON.parse(readFileSync("./package.json", "utf-8"));

let gitTag = "dev";
try {
  gitTag = execSync("git rev-parse --short HEAD", { encoding: "utf-8" }).trim();
} catch { /* not in git */ }

export default defineConfig({
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
    __BUILD_TIME__: JSON.stringify(new Date().toISOString()),
    __GIT_TAG__: JSON.stringify(gitTag),
  },
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
