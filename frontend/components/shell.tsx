"use client";
import { createContext, useContext, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ShieldCheck,
  LayoutDashboard,
  LogOut,
  BookOpen,
  ArrowUpRight,
  LockKeyhole,
} from "lucide-react";
import { api, setCsrf } from "@/lib/api";
import type { User } from "@/lib/types";
const UserContext = createContext<User | null>(null);
export const useUser = () => useContext(UserContext);
export function Shell({
  children,
  onBeforeLogout,
}: {
  children: React.ReactNode;
  onBeforeLogout?: (action: () => void) => void;
}) {
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState("");
  const router = useRouter();
  useEffect(() => {
    api<User>("/auth/me")
      .then((u) => {
        setCsrf(u.csrf);
        setUser(u);
      })
      .catch(() => router.replace("/login"));
  }, [router]);
  async function logout() {
    try {
      await api("/auth/logout", { method: "POST" });
      setCsrf("");
      router.push("/login");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  if (!user)
    return (
      <main className="loading-screen">
        <ShieldCheck size={36} />
        <p>Opening your workspace…</p>
      </main>
    );
  return (
    <UserContext.Provider value={user}>
      <div className="app-shell">
        <aside className="sidebar">
          <Link href="/" className="brand">
            <span className="brand-icon">
              <ShieldCheck size={24} />
            </span>
            DocVerify<span className="brand-dot">.</span>
          </Link>
          <div className="workspace-label">YOUR WORKSPACE</div>
          <nav>
            <Link href="/" className="nav-link">
              <LayoutDashboard size={18} /> Cases{" "}
              <ArrowUpRight size={14} className="nav-arrow" />
            </Link>
          </nav>
          <div className="sidebar-note">
            <BookOpen size={19} />
            <strong>Every finding has a source.</strong>
            <p>
              Review the original, correct the extraction, and keep a clear
              audit trail.
            </p>
          </div>
          <div className="sidebar-bottom">
            <div className="account">
              <span className="avatar">{user.email[0].toUpperCase()}</span>
              <div>
                <strong>Personal workspace</strong>
                <span title={user.email}>{user.email}</span>
              </div>
            </div>
            <button
              className="logout"
              onClick={() => {
                if (onBeforeLogout)
                  onBeforeLogout(() => {
                    void logout();
                  });
                else void logout();
              }}
            >
              <LogOut size={16} /> Sign out
            </button>
            {error && <p role="alert">{error}</p>}
          </div>
        </aside>
        <div className="main-column">
          <header className="topbar">
            <span>DOCUMENT INTELLIGENCE & VERIFICATION</span>
            <span className="private-pill">
              <LockKeyhole size={12} /> Private workspace
            </span>
          </header>
          <main className="content">{children}</main>
          <footer>
            DocVerify{" "}
            <span>Source-linked extraction. Human-reviewed decisions.</span>
          </footer>
        </div>
      </div>
    </UserContext.Provider>
  );
}
