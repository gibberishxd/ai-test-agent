import { Bug } from "lucide-react";
import Link from "next/link";
import { SignOutButton } from "@/components/auth-buttons";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { currentUser } from "@/lib/auth";

const NAV = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/runs", label: "Runs" },
  { href: "/benchmark", label: "Benchmark" },
];

export async function SiteHeader() {
  const user = await currentUser().catch(() => null);
  return (
    <header className="border-b bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-2 px-4 sm:gap-4">
        <Link href="/" className="flex items-center gap-2 font-semibold">
          <span className="flex size-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <Bug className="size-4" />
          </span>
          <span className="hidden md:inline">AI Test Agent</span>
        </Link>
        {/* min-w-0 + overflow: on narrow phones the nav scrolls inside itself, never the page. */}
        <nav aria-label="Main" className="flex min-w-0 flex-1 items-center gap-0.5 overflow-x-auto text-sm sm:gap-1">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="shrink-0 rounded-md px-1.5 py-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground sm:px-2"
            >
              {item.label}
            </Link>
          ))}
        </nav>
        {user ? (
          <span className="flex shrink-0 items-center gap-1">
            <Link href="/settings" className="hidden max-w-40 truncate rounded-md px-2 py-1.5 text-sm hover:bg-muted lg:inline" title={user.email}>
              {user.email}
            </Link>
            <Link href="/settings" className="rounded-md px-2 py-1.5 text-sm text-muted-foreground hover:bg-muted lg:hidden">
              Settings
            </Link>
            <SignOutButton />
          </span>
        ) : (
          <Button size="sm" variant="outline" className="shrink-0" asChild>
            <Link href="/signin">Sign in</Link>
          </Button>
        )}
        <ThemeToggle />
      </div>
    </header>
  );
}
