import { Skeleton } from "@/components/ui/skeleton";

export default function Loading() {
  return (
    <main className="mx-auto grid max-w-6xl gap-6 px-4 py-10" aria-busy="true" aria-label="Loading">
      <Skeleton className="h-8 w-56" />
      <Skeleton className="h-64" />
      <Skeleton className="h-40" />
    </main>
  );
}
