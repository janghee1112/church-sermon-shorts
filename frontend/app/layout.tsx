import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";

const pretendardBlack = localFont({
  src: "./fonts/Pretendard-Black.otf",
  weight: "900",
  style: "normal",
  display: "swap",
  variable: "--font-pretendard-black",
});

export const metadata: Metadata = {
  title: "말씀컷 — 설교 쇼츠 구간 추천",
  description: "설교 영상에서 의미 있는 쇼츠 후보를 찾아보세요.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko" className={pretendardBlack.variable}>
      <body>{children}</body>
    </html>
  );
}
