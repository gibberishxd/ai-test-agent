/** The error to show for a display name, or undefined when it can be saved. */
export function nameError(name: string): string | undefined {
  return name.trim() ? undefined : "Enter a display name.";
}
