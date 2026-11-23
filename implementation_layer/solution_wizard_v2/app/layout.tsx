import "./globals.css";
import type { Metadata } from "next";
import localFont from "next/font/local";
import { getI18n } from "@/lib/i18n";

// Self-hosted Google Fonts (app/fonts/*.woff2, latin variable) — no build-time
// network fetch to Google Fonts, so container/CI builds work offline.
const inter = localFont({
  src: "./fonts/inter.woff2",
  variable: "--font-sans",
  weight: "100 900",
  display: "swap",
});

const jetbrainsMono = localFont({
  src: "./fonts/jetbrains-mono.woff2",
  variable: "--font-mono",
  weight: "100 800",
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
  const { locale, t } = await getI18n();
  return (
    <html
      lang={locale}
      className={`${inter.variable} ${jetbrainsMono.variable}`}
      // Browser extensions / Next dev overlay often mutate <html> before hydrate.
      suppressHydrationWarning
    >
      <body
        className="antialiased bg-app text-text-secondary"
        suppressHydrationWarning
      >
        <a href="#main-content" className="skip-link">
          {t.skipToContent}
        </a>
        {children}
      </body>
    </html>
  );
}
