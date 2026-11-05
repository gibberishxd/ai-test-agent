import { isValidTargetUrl } from "@/lib/url";

export default function Home() {
  // Placeholder dashboard. Phase 5 replaces this with: start a run, live progress, bug report.
  const demo = "http://localhost:5173";
  return (
    <main>
      <h1>AI Test Agent</h1>
      <p>Dashboard coming in Phase 5.</p>
      <p>
        Demo target: <code>{demo}</code> ({isValidTargetUrl(demo) ? "valid" : "invalid"} URL)
      </p>
    </main>
  );
}
