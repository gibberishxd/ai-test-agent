-- Run 4, J5: at most one default model per workspace, enforced by the database (a partial unique
-- index: only rows with is_default = true take part).
CREATE UNIQUE INDEX "model_configs_one_default_per_workspace" ON "model_configs"("workspace_id") WHERE (is_default);
