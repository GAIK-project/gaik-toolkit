import { SiteNav } from "@/components/layout/site-nav";
import { Toaster } from "@/components/ui/toaster";
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
  metadataBase: new URL("https://gaik-demo.2.rahtiapp.fi"),
  openGraph: {
    type: "website",
    locale: "en_US",
    url: "https://gaik-demo.2.rahtiapp.fi",
    siteName: "GAIK Toolkit Demo",
    title: "GAIK Toolkit Demo",
    description:
      "Interactive demos for GAIK Toolkit - Extract, parse, classify, and transcribe documents with AI",
    images: [
      {
        url: "/logos/gaik_logo_medium.png",
        width: 512,
        height: 512,
        alt: "GAIK Toolkit Demo",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "GAIK Toolkit Demo",
    description:
      "Interactive demos for GAIK Toolkit - Extract, parse, classify, and transcribe documents with AI",
    images: ["/logos/gaik_logo_medium.png"],
  },
  icons: {
    icon: "/logos/favicon.ico",
    apple: "/logos/gaik_logo_medium.png",
  },
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
