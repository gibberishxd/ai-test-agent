import react from "@vitejs/plugin-react";
import { defineConfig, type Connect, type Plugin } from "vite";

/**
 * The holdout app: a small room-booking site, built the same way as the demo shop.
 *   vite              → buggy build on 5175
 *   vite --mode clean → clean build on 5176, every planted bug switched off (src/bugs.ts)
 */
export default defineConfig(({ mode }) => {
  const clean = mode === "clean";
  return {
    plugins: [react(), bookingApi(clean)],
    server: { port: clean ? 5176 : 5175, strictPort: true },
    preview: { port: clean ? 5176 : 5175, strictPort: true },
  };
});

/** A tiny fake backend inside the dev server. */
function bookingApi(clean: boolean): Plugin {
  const handler: Connect.NextHandleFunction = (req, res, next) => {
    const path = (req.url ?? "").split("?")[0];
    if (path === "/api/availability") {
      res.setHeader("Content-Type", "application/json");
      if (!clean) {
        // Bug 1: the availability service is down.
        res.statusCode = 503;
        res.end(JSON.stringify({ error: "Service Unavailable" }));
        return;
      }
      res.end(JSON.stringify({ openFrom: "2027-01-05", openTo: "2027-03-31" }));
      return;
    }
    next();
  };
  return {
    name: "booking-api",
    configureServer: (server) => void server.middlewares.use(handler),
    configurePreviewServer: (server) => void server.middlewares.use(handler),
  };
}
