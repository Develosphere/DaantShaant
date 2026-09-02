import type { Metadata } from "next";
import { Plus_Jakarta_Sans, Syne, Anton, Poppins, Darker_Grotesque } from "next/font/google";
import { LanguageProvider } from "@/i18n";
import { ThemeProvider } from "@/theme";
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
  title: "DaantShaant — Scan. Detect. Protect.",
  description:
    "Smart oral-health screening assistant and dentist discovery — care navigation for better oral health.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      dir="ltr"
      data-theme="light"
      className={`${jakarta.variable} ${syne.variable} ${anton.variable} ${poppins.variable} ${darkerGrotesque.variable}`}
    >
      <body>
        <ThemeProvider>
          <LanguageProvider>{children}</LanguageProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}

