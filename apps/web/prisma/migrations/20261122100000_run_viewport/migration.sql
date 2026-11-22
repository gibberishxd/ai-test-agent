-- Viewport per run: the screen size a run starts on, as "WIDTHxHEIGHT" (e.g. "390x844", "768x1024",
-- "1440x900"). The crawl, the agent and replay verification all start at this size; the agent can
-- still switch to its named desktop/mobile sizes. NULL = the default desktop size (1280x800).

ALTER TABLE "runs" ADD COLUMN "viewport" TEXT;
ALTER TABLE "runs"
  ADD CONSTRAINT "runs_viewport_format" CHECK (viewport IS NULL OR viewport ~ '^[0-9]{3,4}x[0-9]{3,4}$');
