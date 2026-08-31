import type { Metadata } from "next";
import { Plus_Jakarta_Sans, Syne, Anton, Poppins, Darker_Grotesque } from "next/font/google";
import "./globals.css";

const jakarta = Plus_Jakarta_Sans({
  subsets: ["latin"],
  variable: "--font-jakarta",
  display: "swap",
});

const syne = Syne({
  subsets: ["latin"],
  variable: "--font-syne",
  display: "swap",
});

const anton = Anton({
  weight: "400",
  subsets: ["latin"],
  variable: "--font-anton",
  display: "swap",
});

const poppins = Poppins({
  weight: ["400", "700"],
  subsets: ["latin"],
  variable: "--font-poppins",
  display: "swap",
});

const darkerGrotesque = Darker_Grotesque({
  weight: ["400", "600", "700"],
  subsets: ["latin"],
  variable: "--font-darker-grotesque",
  display: "swap",
});

export const metadata: Metadata = {
  title: "DaantShant — Scan. Detect. Protect.",
  description:
    "AI dental scanner, smart assistant, and dentist matching — everything you need for better oral health.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${jakarta.variable} ${syne.variable} ${anton.variable} ${poppins.variable} ${darkerGrotesque.variable}`}
    >
      <body>{children}</body>
    </html>
  );
}
