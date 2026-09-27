import type { Metadata } from "next";
import "@fontsource/figtree/400.css";
import "@fontsource/figtree/500.css";
import "@fontsource/figtree/600.css";
import "@fontsource/figtree/700.css";
import "@fontsource/lora/400.css";
import "@fontsource/lora/500.css";
import "@fontsource/azeret-mono/400.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "docket | Document intelligence",
  description:
    "An accounts payable workbench with field provenance, business rules, human review, and transparent evaluation. Demonstration documents only.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
