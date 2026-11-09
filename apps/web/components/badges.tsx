import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const SEVERITY_STYLES: Record<string, string> = {
  critical: "bg-red-600 text-white dark:bg-red-500",
  high: "bg-orange-500/15 text-orange-700 dark:text-orange-300",
  medium: "bg-amber-400/20 text-amber-800 dark:text-amber-300",
  low: "bg-muted text-muted-foreground",
};

export function SeverityBadge({ severity }: { severity: string }) {
  return (
    <Badge className={cn("capitalize", SEVERITY_STYLES[severity] ?? SEVERITY_STYLES.low)}>
      {severity}
    </Badge>
  );
}

const STATUS_STYLES: Record<string, string> = {
  queued: "bg-muted text-muted-foreground",
  running: "bg-primary/15 text-primary",
  done: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  failed: "bg-red-500/15 text-red-700 dark:text-red-300",
  stopped: "bg-muted text-muted-foreground",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <Badge
      data-testid="run-status"
      className={cn("capitalize", STATUS_STYLES[status] ?? STATUS_STYLES.queued)}
    >
      {status === "running" && <span className="size-1.5 animate-pulse rounded-full bg-current" />}
      {status}
    </Badge>
  );
}

export function ModeBadge({ mode }: { mode: string }) {
  return (
    <Badge variant="outline" className="capitalize">
      {mode}
    </Badge>
  );
}
