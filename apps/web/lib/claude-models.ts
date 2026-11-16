/**
 * The Claude models the model form suggests (run 7). Haiku is the default agent, from run 6's
 * benchmark (DECISIONS D91): most of Sonnet's findings at a fraction of the cost per verified
 * bug. Sonnet is the thorough option. Kept apart from model-configs.ts so the client form can
 * import it without the database code.
 */
export const CLAUDE_MODELS = [
  { id: "claude-haiku-5-5", label: "Claude Haiku 5.5 (default, recommended)" },
  { id: "claude-sonnet-5-5", label: "Claude Sonnet 5.5 (thorough, ~16–28× the cost per run)" },
] as const;

/** The model field after the provider changes: Haiku for Claude when nothing was typed. */
export function modelForProvider(provider: string, typed: string): string {
  if (typed.trim()) return typed;
  return provider === "claude" ? CLAUDE_MODELS[0].id : typed;
}
