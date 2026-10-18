"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ShieldCheck,
  ArrowRight,
  FileSearch,
  GitCompareArrows,
  CheckCheck,
} from "lucide-react";
import { api, setCsrf } from "@/lib/api";
import type { User } from "@/lib/types";
export function AuthForm({ register = false }: { register?: boolean }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const router = useRouter();
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(e.currentTarget);
    try {
      const user = await api<User>(`/auth/${register ? "register" : "login"}`, {
        method: "POST",
        body: JSON.stringify({
          email: data.get("email"),
          password: data.get("password"),
        }),
      });
      setCsrf(user.csrf);
      router.push("/");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="auth-layout">
      <section className="auth-story">
        <Link href="/" className="brand">
          <span className="brand-icon">
            <ShieldCheck />
          </span>
          DocVerify<span className="brand-dot">.</span>
        </Link>
        <div className="auth-story-inner">
          <span className="eyebrow">CONFIDENCE, WITH EVIDENCE</span>
          <h1>
            Small details.
            <br />
            <em>Big differences.</em>
          </h1>
          <p>
            Bring purchase orders, quotations, and invoices together. See what
            matches, what changed, and what needs a closer look.
          </p>
          <div className="auth-steps">
            <span>
              <FileSearch /> Extract with sources
            </span>
            <span>
              <GitCompareArrows /> Compare with precision
            </span>
            <span>
              <CheckCheck /> Review with confidence
            </span>
          </div>
        </div>
        <span className="auth-disclaimer">
          A portfolio application · Use fictional sample documents
        </span>
      </section>
      <section className="auth-form-wrap">
        <div className="auth-form">
          <span className="eyebrow">YOUR DOCUMENT WORKSPACE</span>
          <h2>{register ? "Create your account" : "Welcome back"}</h2>
          <p>
            {register
              ? "A private place to review documents and resolve differences."
              : "Sign in to pick up where you left off."}
          </p>
          <form onSubmit={submit}>
            <label>
              Email address
              <input
                name="email"
                type="email"
                autoComplete="email"
                required
                placeholder="you@example.com"
              />
            </label>
            <label>
              Password
              <input
                name="password"
                type="password"
                minLength={10}
                maxLength={128}
                autoComplete={register ? "new-password" : "current-password"}
                required
                placeholder="At least 10 characters"
              />
            </label>
            {error && (
              <div className="error-banner" role="alert">
                {error}
              </div>
            )}
            <button className="button primary wide" disabled={busy}>
              {busy ? "Please wait…" : register ? "Create account" : "Sign in"}
              <ArrowRight size={16} />
            </button>
          </form>
          <p className="auth-switch">
            {register ? "Already have an account?" : "New to DocVerify?"}{" "}
            <Link href={register ? "/login" : "/register"}>
              {register ? "Sign in" : "Create an account"}
            </Link>
          </p>
          <div className="auth-security">
            <ShieldCheck size={17} /> Your cases and source files are accessible
            only to your account.
          </div>
        </div>
      </section>
    </main>
  );
}
