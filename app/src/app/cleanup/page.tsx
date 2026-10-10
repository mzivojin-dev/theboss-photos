import Link from "next/link";
import CleanupPanel from "@/components/CleanupPanel";

export default function CleanupPage() {
  return (
    <main>
      <header style={{ padding: "1rem 1.5rem", borderBottom: "1px solid #333", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1 style={{ fontSize: "1.1rem", fontWeight: 600 }}>Clean up Google Photos</h1>
        <Link href="/">← Timeline</Link>
      </header>
      <CleanupPanel />
    </main>
  );
}
