-- Run 3, H4: a lease for running runs. The worker renews heartbeat_at (database clock) every
-- few seconds while it works; any worker fails runs whose lease expired (the worker died).
ALTER TABLE "runs" ADD COLUMN "heartbeat_at" TIMESTAMPTZ(3);
