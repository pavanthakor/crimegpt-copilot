import "./globals.css";
import type { ReactNode } from "react";

import { AuthProvider } from "@/components/AuthProvider";
import Nav from "@/components/Nav";

export const metadata = {
  title: "CrimeGPT",
  description: "Crime documentation copilot",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>
          <Nav />
          <main style={{ padding: 16 }}>{children}</main>
        </AuthProvider>
      </body>
    </html>
  );
}
