import react from "@vitejs/plugin-react";
import { defineConfig, type Connect, type Plugin } from "vite";

/**
 * Two builds from one codebase:
 *   vite              → buggy shop on 5173 (mode "development")
 *   vite --mode clean → clean shop on 5174, every planted bug switched off (see src/bugs.ts)
 */
export default defineConfig(({ mode }) => {
  const clean = mode === "clean";
  return {
    plugins: [react(), demoApi(clean)],
    server: { port: clean ? 5174 : 5173, strictPort: true },
    preview: { port: clean ? 5174 : 5173, strictPort: true },
  };
});

const ORDERS = [
  { id: 10231, date: "2026-10-02", total: 36 },
  { id: 10457, date: "2026-10-19", total: 89 },
];

/** A tiny fake backend inside the dev server, so the shop has real HTTP responses to test. */
function demoApi(clean: boolean): Plugin {
  const handler: Connect.NextHandleFunction = (req, res, next) => {
    const path = (req.url ?? "").split("?")[0];

    if (path === "/api/profile") {
      res.setHeader("Content-Type", "application/json");
      if (!clean) {
        // Bug 2: the profile API fails with a server error.
        res.statusCode = 500;
        res.end(JSON.stringify({ error: "Internal Server Error" }));
        return;
      }
      res.end(JSON.stringify({ orders: ORDERS }));
      return;
    }

    if (path === "/return-policy") {
      // Bug 3's target: an old URL that no longer exists. Only the buggy footer links here.
      res.statusCode = 404;
      res.setHeader("Content-Type", "text/html");
      res.end('<!doctype html><html lang="en"><title>404 Not Found</title><h1>404 Not Found</h1></html>');
      return;
    }

    next();
  };

  return {
    name: "demo-api",
    configureServer: (server) => void server.middlewares.use(handler),
    configurePreviewServer: (server) => void server.middlewares.use(handler),
  };
}
