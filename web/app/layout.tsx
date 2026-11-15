import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Argos",
  description: "A voice companion for people living with dementia.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
