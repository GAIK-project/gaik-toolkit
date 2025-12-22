import { SiteNav } from "@/components/layout/site-nav";
import { Toaster } from "@/components/ui/sonner";
import type { Metadata } from "next";
import { Fraunces, JetBrains_Mono, Sora } from "next/font/google";
import "./globals.css";

const sora = Sora({
  variable: "--font-sans",
  subsets: ["latin"],
});

const fraunces = Fraunces({
  variable: "--font-serif",
  subsets: ["latin"],
});

const jetBrainsMono = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: {
    default: "GAIK Toolkit Demo",
    template: "%s | GAIK Toolkit",
  },
  description:
    "Interactive demos for GAIK Toolkit - Extract, parse, classify, and transcribe documents with AI",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${sora.variable} ${fraunces.variable} ${jetBrainsMono.variable} antialiased`}
      >
        <div className="min-h-screen">
          <SiteNav />
          {children}
        </div>
        <Toaster />
      </body>
    </html>
  );
}
