import localFont from "next/font/local";

export const saira = localFont({
  src: "./fonts/saira-latin.woff2",
  weight: "400 700",
  style: "normal",
  display: "swap",
  variable: "--font-saira",
});

export const sairaCondensed = localFont({
  src: [
    { path: "./fonts/saira-condensed-500-latin.woff2", weight: "500", style: "normal" },
    { path: "./fonts/saira-condensed-600-latin.woff2", weight: "600", style: "normal" },
    { path: "./fonts/saira-condensed-700-latin.woff2", weight: "700", style: "normal" },
  ],
  display: "swap",
  variable: "--font-saira-condensed",
});

export const plexMono = localFont({
  src: [
    { path: "./fonts/ibm-plex-mono-400-latin.woff2", weight: "400", style: "normal" },
    { path: "./fonts/ibm-plex-mono-500-latin.woff2", weight: "500", style: "normal" },
  ],
  display: "swap",
  variable: "--font-plex-mono",
});
