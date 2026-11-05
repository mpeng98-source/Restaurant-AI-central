import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = { title: "Chubby AI | Restaurant Operations", description: "Chubby Group restaurant operations platform", referrer: "no-referrer" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{process.env.NEXT_PUBLIC_DEMO_MODE === "true" && <p role="status" className="inventory-alert">PRIVATE INTERNAL DEMO — Synthetic data and test accounts only. No live restaurant integrations. Photo uploads are disabled unless scanner verification is separately completed.</p>}{children}</body></html>;
}
