/**
 * A workspace's own models ("bring any model"), always scoped to one workspace.
 *
 * The API key is encrypted before it reaches the database (lib/secret-box.ts) and nothing
 * here ever returns it: views carry only "•••• last4". A new or replaced key clears the last
 * "Test connection" result, because the new key has to pass it again.
 */
import { db } from "@/lib/db";
import { tenantDb } from "@/lib/tenant-db";
import type { ProbeResult } from "@/lib/model-probe";
import { encryptSecret, lastFour } from "@/lib/secret-box";

/** Providers a workspace can choose. (claude-cli is the owner's local test tool, never here.) */
export const WORKSPACE_PROVIDERS = ["openai-compat", "claude"] as const;
export type WorkspaceProvider = (typeof WORKSPACE_PROVIDERS)[number];

export type ModelInput = {
  label: string;
  provider: WorkspaceProvider;
  baseUrl: string | null;
  model: string;
  cheapModel: string | null;
  apiKey: string | null;
  inputPrice: number;
  outputPrice: number;
};

export type ModelErrors = Partial<Record<keyof ModelInput, string>>;

export type ModelConfigView = {
  id: string;
  label: string;
  provider: string;
  baseUrl: string | null;
  model: string;
  cheapModel: string | null;
  keyHint: string | null;
  inputPrice: number;
  outputPrice: number;
  isDefault: boolean;
  probe: ProbeResult | null;
  /** Passed Test connection: answers, calls tools, reads images. */
  usable: boolean;
};

const text = (value: unknown) => (typeof value === "string" ? value.trim() : "");

function price(value: unknown): number | null {
  if (value === undefined || value === null || value === "") return 0;
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : null;
}

export function parseModelInput(body: Record<string, unknown>): { ok: true; value: ModelInput } | { ok: false; errors: ModelErrors } {
  const errors: ModelErrors = {};
  const provider = text(body.provider);
  if (!WORKSPACE_PROVIDERS.includes(provider as WorkspaceProvider)) errors.provider = "Choose OpenAI-compatible or Anthropic.";
  const label = text(body.label).slice(0, 80);
  if (!label) errors.label = "Give the model a name you'll recognise.";
  const model = text(body.model).slice(0, 200);
  if (!model) errors.model = "Enter the model's id, e.g. gpt-5-mini.";
  const baseUrl = text(body.baseUrl) || null;
  if (provider === "openai-compat") {
    if (!baseUrl) errors.baseUrl = "Enter the API's base URL, e.g. https://api.openai.com/v1.";
    else {
      try {
        const url = new URL(baseUrl);
        if (url.protocol !== "https:" && url.protocol !== "http:") throw new Error();
      } catch {
        errors.baseUrl = "That isn't an http(s) URL.";
      }
    }
  }
  const apiKey = text(body.apiKey) || null;
  if (provider === "claude" && !apiKey) errors.apiKey = "Paste your Anthropic API key.";
  const inputPrice = price(body.inputPrice);
  const outputPrice = price(body.outputPrice);
  if (inputPrice === null) errors.inputPrice = "Enter a price of 0 or more.";
  if (outputPrice === null) errors.outputPrice = "Enter a price of 0 or more.";
  if (Object.keys(errors).length > 0) return { ok: false, errors };
  return {
    ok: true,
    value: {
      label,
      provider: provider as WorkspaceProvider,
      baseUrl: provider === "openai-compat" ? baseUrl : null,
      model,
      cheapModel: text(body.cheapModel) || null,
      apiKey,
      inputPrice: inputPrice!,
      outputPrice: outputPrice!,
    },
  };
}

type Row = Awaited<ReturnType<typeof db.modelConfig.findFirstOrThrow>>;

export function toView(row: Row): ModelConfigView {
  const probe = (row.probe as ProbeResult | null) ?? null;
  return {
    id: row.id,
    label: row.label,
    provider: row.provider,
    baseUrl: row.baseUrl,
    model: row.model,
    cheapModel: row.cheapModel,
    keyHint: row.apiKeyLast4 ? `•••• ${row.apiKeyLast4}` : null,
    inputPrice: row.inputPrice,
    outputPrice: row.outputPrice,
    isDefault: row.isDefault,
    probe,
    usable: probe?.ok === true,
  };
}

export async function listModelConfigs(workspaceId: string): Promise<ModelConfigView[]> {
  const rows = await tenantDb(workspaceId).modelConfig.findMany({ where: { workspaceId }, orderBy: { createdAt: "asc" } });
  return rows.map(toView);
}

export async function createModelConfig(workspaceId: string, body: Record<string, unknown>, serverKey: Buffer) {
  const parsed = parseModelInput(body);
  if (!parsed.ok) return parsed;
  const { apiKey, ...fields } = parsed.value;
  const row = await db.modelConfig.create({
    data: {
      workspaceId,
      ...fields,
      apiKeyCiphertext: apiKey ? encryptSecret(apiKey, workspaceId, serverKey) : null,
      apiKeyLast4: apiKey ? lastFour(apiKey) : null,
    },
  });
  return { ok: true as const, model: toView(row) };
}

export async function replaceModelKey(workspaceId: string, id: string, apiKey: string, serverKey: Buffer) {
  const key = apiKey.trim();
  if (!key) return null;
  const updated = await db.modelConfig.updateMany({
    where: { id, workspaceId },
    data: { apiKeyCiphertext: encryptSecret(key, workspaceId, serverKey), apiKeyLast4: lastFour(key), probe: undefined },
  });
  if (updated.count === 0) return null;
  // Prisma can't set JSON to SQL NULL in updateMany; clear the old test result separately.
  await db.$executeRaw`UPDATE model_configs SET probe = NULL WHERE id = ${id}::uuid AND workspace_id = ${workspaceId}::uuid`;
  return toView(await db.modelConfig.findFirstOrThrow({ where: { id, workspaceId } }));
}

export async function deleteModelConfig(workspaceId: string, id: string): Promise<boolean> {
  return (await db.modelConfig.deleteMany({ where: { id, workspaceId } })).count > 0;
}

export async function setDefaultModel(workspaceId: string, id: string): Promise<boolean> {
  return db.$transaction(async (tx) => {
    const found = await tx.modelConfig.count({ where: { id, workspaceId } });
    if (found === 0) return false;
    await tx.modelConfig.updateMany({ where: { workspaceId }, data: { isDefault: false } });
    await tx.modelConfig.update({ where: { id }, data: { isDefault: true } });
    return true;
  });
}

export async function storeProbe(workspaceId: string, id: string, probe: ProbeResult): Promise<boolean> {
  const updated = await db.modelConfig.updateMany({ where: { id, workspaceId }, data: { probe } });
  return updated.count > 0;
}

/** For starting a run: the model, if it is this workspace's and passed Test connection. */
export async function usableModel(workspaceId: string, id: string): Promise<{ ok: true } | { ok: false; error: string }> {
  const row = await db.modelConfig.findFirst({ where: { id, workspaceId } });
  if (!row) return { ok: false, error: "Choose one of your workspace's models." };
  const probe = row.probe as ProbeResult | null;
  if (!probe) return { ok: false, error: `“${row.label}” hasn't passed Test connection yet (Settings → Models).` };
  if (!probe.ok) return { ok: false, error: `“${row.label}” failed Test connection: ${probe.error ?? "unknown reason"}` };
  return { ok: true };
}
