import type { Metadata } from "next";
import "./globals.css";
import SessionProvider from "./components/SessionProvider";
import SessionMigrationWrapper from "./components/SessionMigrationWrapper";
import Header from "./components/Header";

export const metadata: Metadata = {
  title: "晴途 Qingtu · 把好心情，安排进旅程",
  description: "晴途旅行助手：选城市、定偏好、看行程。结合真实地点与交通方案，轻松规划你的下一次出发。",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" data-scroll-behavior="smooth">
      <body className="antialiased qt-app">
        <a className="qt-skip-link" href="#main-content">跳到主要内容</a>
        <SessionProvider>
          <SessionMigrationWrapper />
          <Header />
          <main id="main-content" tabIndex={-1}>{children}</main>
        </SessionProvider>
      </body>
    </html>
  );
}

