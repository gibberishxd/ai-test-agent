import type { ReactNode } from "react";

export const metadata = {
  title: "AI Test Agent",
  description: "An AI agent that explores web apps and reports bugs",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui, sans-serif", margin: "2rem" }}>{children}</body>
    </html>
  );
}
