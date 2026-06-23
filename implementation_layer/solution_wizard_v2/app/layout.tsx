import "./globals.css";
import type { Metadata } from "next";
import { Inter, JetBrains_Mono, Orbitron } from "next/font/google";
import { getLocale } from "@/lib/i18n";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

// Geometrinen/kulmikas display-fontti logon kirjaimelle.
const orbitron = Orbitron({
  subsets: ["latin"],
  variable: "--font-display",
  weight: ["700", "800"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "GAIK Solution Wizard",
  description: "GAIK Solution Configuration Wizard — basic UI prototype",
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const locale = await getLocale();
  return (
    <html
      lang={locale}
      className={`${inter.variable} ${jetbrainsMono.variable} ${orbitron.variable}`}
    >
      <body className="antialiased bg-app text-text-secondary">{children}</body>
    </html>
  );
}
