import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <main className="mx-auto flex max-w-md flex-col items-center gap-4 px-4 py-24 text-center">
      <p className="text-sm font-medium text-primary">404</p>
      <h1 className="text-xl font-semibold">Page not found</h1>
      <p className="text-muted-foreground">That page or run doesn&apos;t exist, or belongs to another workspace.</p>
      <Button asChild>
        <Link href="/dashboard">Go to the dashboard</Link>
      </Button>
    </main>
  );
}
