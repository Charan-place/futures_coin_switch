import type { Metadata } from "next";
import "./globals.css";
import Navbar from "@/components/Navbar";
import ClientOnly from "@/components/ClientOnly";

export const metadata: Metadata = {
  title: "Coin Switch Dashboard",
  description: "Futures trading monitor for CoinSwitch",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <ClientOnly>
          <Navbar />
          <main className="max-w-6xl mx-auto px-4 py-8">{children}</main>
        </ClientOnly>
      </body>
    </html>
  );
}
