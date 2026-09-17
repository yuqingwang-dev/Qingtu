"use client";
import { useSession, signIn, signOut } from "next-auth/react";
import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import BrandMark from "./BrandMark";

export default function Header() {
  const { data: session, status } = useSession();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const accountRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const outside = (event: MouseEvent) => { if (!accountRef.current?.contains(event.target as Node)) setOpen(false); };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", outside);
    document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("mousedown", outside); document.removeEventListener("keydown", escape); };
  }, []);
  return <header className="qt-header">
    <div className="qt-header-inner">
      <Link href="/" className="qt-brand" aria-label="晴途首页"><BrandMark /><span>晴途 <small>QINGTU</small></span></Link>
      <nav aria-label="主要导航" className="qt-nav">
        <Link href="/" aria-current={pathname === "/" ? "page" : undefined}>发现晴途</Link>
        <Link href="/plan/single-city" aria-current={pathname?.startsWith("/plan") ? "page" : undefined}>规划旅行</Link>
        <Link href="/my-itineraries" aria-current={pathname?.startsWith("/my-itineraries") ? "page" : undefined}>我的行程</Link>
      </nav>
      <div className="qt-header-account" ref={accountRef}>
        {status === "loading" ? <span className="qt-small-note" role="status">加载中…</span> : session ? <>
          <button type="button" className="qt-account-button" onClick={() => setOpen(!open)} aria-expanded={open} aria-controls="qt-account-panel">
            <span className="qt-avatar" aria-hidden="true">{session.user?.name?.slice(0, 1) || "旅"}</span><span className="qt-account-label">我的账户</span><span aria-hidden="true">⌄</span>
          </button>
          {open && <div className="qt-account-panel" id="qt-account-panel"><strong>{session.user?.name || "旅行者"}</strong><Link href="/my-itineraries" onClick={() => setOpen(false)}>查看我的行程</Link><button type="button" onClick={() => { setOpen(false); signOut({ callbackUrl: "/" }); }}>退出登录</button></div>}
        </> : <button type="button" onClick={() => signIn("google")} className="qt-login-button" aria-label="使用 Google 登录，保存行程">登录 / 保存行程</button>}
      </div>
    </div>
  </header>;
}
