import { useState, type FormEvent } from "react";
import { useApi, useAuth } from "../app-context";
import { ApiError } from "../api/client";
import { USE_MOCK } from "../api";
import { TextField } from "../components/Field";
import { Button, Callout } from "../components/ui";
import { Wordmark } from "../components/Wordmark";
import { ThemeToggle } from "../components/Layout";
import { navigate, useRoute } from "../lib/router";
import { fieldErrors, requiredMsg } from "../lib/query";
import { focusFirstInvalid } from "../lib/hooks";

export function LoginScreen() {
  const api = useApi(); const { setUser } = useAuth(); const route = useRoute();
  const [u, setU] = useState(""); const [p, setP] = useState("");
  const [errs, setErrs] = useState<Record<string, string>>({}); const [formErr, setFormErr] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault(); if (pending) return;
    const v: Record<string, string> = {};
    if (!u.trim()) v.username = requiredMsg("نام کاربری");
    if (!p) v.password = requiredMsg("گذرواژه");
    setErrs(v); setFormErr(null);
    if (Object.keys(v).length) { focusFirstInvalid(); return; }
    setPending(true);
    try {
      const r = await api.login(u.trim(), p);
      setUser(r.user);
      const next = route.query.get("next");
      navigate(next && next.startsWith("/") ? next : "/", true);
    } catch (err) {
      setErrs(fieldErrors(err)); // input is preserved on failure
      setFormErr(err instanceof ApiError ? err.message : "ورود انجام نشد.");
      setPending(false);
    }
  };
  return (
    <div className="login">
      <form className="card login__card" onSubmit={submit} noValidate aria-labelledby="login-title">
        <div className="row row--between"><Wordmark /><ThemeToggle /></div>
        <div className="login__accent" />
        <div><h1 id="login-title" tabIndex={-1}>ورود به سامانه</h1><p className="muted">برای ادامه با حساب سازمانی خود وارد شوید.</p></div>
        {route.query.get("expired") === "1" && !formErr && <Callout tone="warn"><strong>نشست شما منقضی شد.</strong> دوباره وارد شوید؛ پس از ورود به همین صفحه برمی‌گردید و ورودی‌های ناتمام شما حفظ شده است.</Callout>}
        {formErr && <Callout tone="danger">{formErr}</Callout>}
        <TextField label="نام کاربری" value={u} onChange={setU} error={errs.username} autoComplete="username" dir="ltr" autoFocus required />
        <TextField label="گذرواژه" type="password" value={p} onChange={setP} error={errs.password} autoComplete="current-password" dir="ltr" required />
        <Button type="submit" variant="primary" pending={pending}>{pending ? "در حال ورود…" : "ورود"}</Button>
        {USE_MOCK && <Callout tone="info"><span>حالت نمایشی با داده‌های ساختگی.</span><br /><span>نام کاربری: <bdi><code>admin</code></bdi> ، <bdi><code>hr</code></bdi> یا <bdi><code>viewer</code></bdi></span><br /><span>گذرواژه: <bdi><code>demo</code></bdi></span></Callout>}
      </form>
    </div>
  );
}
