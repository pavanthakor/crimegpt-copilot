import "./globals.css";
import type { ReactNode } from "react";
import {
  Noto_Serif,
  Noto_Sans,
  Noto_Sans_Gujarati,
  Noto_Sans_Devanagari,
  JetBrains_Mono,
} from "next/font/google";

import { AuthProvider } from "@/components/AuthProvider";
import AppShell from "@/components/AppShell";

// Self-hosted via next/font (no runtime Google Fonts dependency, so Gujarati +
// Devanagari render even offline). Each exposes a CSS variable consumed by
// tailwind.config.ts and globals.css.
const notoSerif = Noto_Serif({
  subsets: ["latin"],
  weight: ["400", "600", "700"],
  variable: "--font-noto-serif",
  display: "swap",
});
const notoSans = Noto_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-noto-sans",
  display: "swap",
});
const notoSansGujarati = Noto_Sans_Gujarati({
  subsets: ["gujarati"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-noto-gujarati",
  display: "swap",
});
const notoSansDevanagari = Noto_Sans_Devanagari({
  subsets: ["devanagari"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-noto-devanagari",
  display: "swap",
});
const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-jetbrains-mono",
  display: "swap",
});

const fontVars = [
  notoSerif.variable,
  notoSans.variable,
  notoSansGujarati.variable,
  notoSansDevanagari.variable,
  jetbrainsMono.variable,
].join(" ");

export const metadata = {
  title: "CrimeGPT",
  description: "AI-powered crime documentation and legal intelligence",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={fontVars}>
      {/* Material Symbols is self-hosted via @font-face in globals.css — no runtime
          Google Fonts link, so the app has no network font dependency at all. */}
      <body>
        <AuthProvider>
          <AppShell>{children}</AppShell>
        </AuthProvider>
      </body>
    </html>
  );
}
