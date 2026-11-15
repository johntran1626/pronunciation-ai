import type { Metadata } from "next";
import { Jua, Outfit } from "next/font/google";
import "./globals.css";

// next/font downloads the fonts at build time and serves them from this site (no request to Google from the
// visitor's browser). Jua has Korean glyphs too; only its Latin part is preloaded, Korean parts load as needed.
const jua = Jua({ weight: "400", variable: "--font-jua", subsets: ["latin"] });
const outfit = Outfit({ variable: "--font-outfit", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Pronunciation coach",
  description: "Korean and English pronunciation practice, estimated from your audio",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${jua.variable} ${outfit.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col font-sans">{children}</body>
    </html>
  );
}
