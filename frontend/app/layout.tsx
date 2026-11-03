import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = { title: "Chubby AI | Restaurant Operations", description: "Chubby Group restaurant operations platform", referrer: "no-referrer" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
