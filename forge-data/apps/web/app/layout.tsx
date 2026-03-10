import type { Metadata } from "next";
import { DM_Mono, Syne } from "next/font/google";
import "@/styles/globals.css";

const syne = Syne({
  subsets: ["latin"],
  variable: "--font-syne",
  display: "swap",
});

const dmMono = DM_Mono({
  subsets: ["latin"],
  weight: ["300", "400", "500"],
  variable: "--font-dm-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: { default: "FORGE Data", template: "%s | FORGE Data" },
  description: "Open-source, self-hosted data intelligence platform",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${syne.variable} ${dmMono.variable} dark`}
      suppressHydrationWarning
    >
      <body className="min-h-screen bg-forge-bg font-sans antialiased">
        {children}
      </body>
    </html>
  );
}
