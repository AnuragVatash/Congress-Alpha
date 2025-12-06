import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { DebugPerformance } from "@/src/components/DebugPerformance";
import { SpeedInsights } from "@vercel/speed-insights/next";
import { Analytics } from "@vercel/analytics/react";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Congress Alpha",
  description:
    "Track stock trades made by members of Congress in real-time. Transparency in congressional trading through comprehensive data analysis. Powered by Congress Alpha.",
  icons: {
    icon: "/favicon.ico",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased text-white`}
      >
        <header
          style={{
            background: "var(--c-navy)",
            color: "#fff",
            padding: "1rem",
          }}
        >
          <nav>{/* Top Navigation */}</nav>
        </header>
        {process.env.NODE_ENV === "development" && <DebugPerformance />}
        <main>{children}</main>
        <SpeedInsights />
        <Analytics />
      </body>
    </html>
  );
}
