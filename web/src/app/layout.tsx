import type { Metadata } from "next";

import { mono, sans } from "./fonts";
import "./globals.css";

export const metadata: Metadata = {
  title: "MCPlain",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">{children}</body>
    </html>
  );
}
