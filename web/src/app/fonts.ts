import localFont from "next/font/local";

export const sans = localFont({
  src: "./fonts/atkinson-hyperlegible-next-latin.woff2",
  weight: "200 800",
  style: "normal",
  display: "swap",
  variable: "--font-atkinson-sans",
});

export const mono = localFont({
  src: "./fonts/atkinson-hyperlegible-mono-latin.woff2",
  weight: "200 800",
  style: "normal",
  display: "swap",
  variable: "--font-atkinson-mono",
});
