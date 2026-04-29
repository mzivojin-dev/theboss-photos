import Timeline from "@/components/Timeline";
import IngestionPanel from "@/components/IngestionPanel";

export default function Home() {
  return (
    <main>
      <header style={{ padding: "1rem 1.5rem", borderBottom: "1px solid #333", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1 style={{ fontSize: "1.1rem", fontWeight: 600 }}>theboss photos</h1>
        <IngestionPanel />
      </header>
      <Timeline />
    </main>
  );
}
