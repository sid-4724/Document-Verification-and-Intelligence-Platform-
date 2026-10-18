import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "DocVerify · Document intelligence",
  description:
    "Evidence-first document extraction and verification for purchase orders, quotes, and invoices.",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
