import { Skeleton } from "@/components/ui/skeleton";

export default function Loading() {
  return (
    <main className="mx-auto grid max-w-4xl gap-6 px-4 py-10" aria-busy="true" aria-label="Loading run">
      <Skeleton className="h-6 w-40" />
      <Skeleton className="h-8 w-3/4" />
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-20" />
        ))}
      </div>
      <Skeleton className="h-48" />
    </main>
  );
}
