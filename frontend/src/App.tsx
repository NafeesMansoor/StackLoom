import { useEffect, useState, type FormEvent } from "react";
import { api, setCsrf, type ApiError, type Health, type Me } from "./api";
import { Mark } from "./Logo";
import { Activity } from "./pages/Activity";
import { CodeMaps } from "./pages/CodeMaps";
import { Databases } from "./pages/Databases";
import { Discovery } from "./pages/Discovery";
import { Docker } from "./pages/Docker";
import { GitList, GitRepo } from "./pages/Git";
import { Graph } from "./pages/Graph";
import { Overview } from "./pages/Overview";
import { Project } from "./pages/Project";
import { Projects } from "./pages/Projects";
import { Ports, Services } from "./pages/Services";
import { Settings } from "./pages/Settings";
import { About, Backups, Diagnostics } from "./pages/System";
import { Tasks } from "./pages/Tasks";
import { Bell } from "./Bell";

function useHashRoute(): string {
  const [route, setRoute] = useState(() => window.location.hash.slice(1) || "/");
  useEffect(() => {
    const onHash = () => setRoute(window.location.hash.slice(1) || "/");
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  return route;
}

const NAV: { section?: string; items: { href: string; label: string }[] }[] = [
  { items: [{ href: "/", label: "Overview" }] },
  { section: "Workspace", items: [
    { href: "/projects", label: "Projects" },
    { href: "/discovery", label: "Discovery" },
    { href: "/activity", label: "Recent activity" },
  ] },
  { section: "Runtime", items: [
    { href: "/services", label: "Services" },
    { href: "/ports", label: "Ports" },
  ] },
  { section: "Docker", items: [
    { href: "/docker", label: "Containers and images" },
    { href: "/docker/compose", label: "Compose projects" },
  ] },
  { section: "Databases", items: [{ href: "/databases", label: "Connections" }] },
  { section: "Code intelligence", items: [
    { href: "/codecortex", label: "Project maps" },
    { href: "/graph", label: "Graph explorer" },
  ] },
  { section: "Development", items: [
    { href: "/git", label: "Git repositories" },
    { href: "/diagnostics", label: "Diagnostics" },
  ] },
  { section: "System", items: [
    { href: "/tasks", label: "Tasks" },
    { href: "/backups", label: "Backups" },
    { href: "/settings", label: "Settings" },
    { href: "/about", label: "About" },
  ] },
];

export function App() {
  const [me, setMe] = useState<Me | null>(null);
  const [checked, setChecked] = useState(false);
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    api.get<Health>("/api/health").then(setHealth).catch(() => undefined);
    api.get<Me>("/api/auth/me")
      .then((m) => { setCsrf(m.csrf); setMe(m); })
      .catch(() => setMe(null))
      .finally(() => setChecked(true));
    const out = () => setMe(null);
    window.addEventListener("stackloom:signed-out", out);
    return () => window.removeEventListener("stackloom:signed-out", out);
  }, []);

  if (!checked) return <div className="loading" role="status">Loading…</div>;
  if (!me) return <SignIn onDone={(m) => { setCsrf(m.csrf); setMe(m); }} health={health} />;
  if (me.must_change_password) return <ChangePassword me={me} onDone={() => setMe({ ...me, must_change_password: false })} />;
  return <Shell me={me} health={health} onSignOut={() => setMe(null)} />;
}

function Footer({ health, inverse }: { health: Health | null; inverse?: boolean }) {
  return (
    <p className="small" style={{ color: inverse ? "var(--side-muted)" : "var(--muted)", margin: "24px 0 0" }}>
      STACKLOOM {health?.version ?? ""} · <a href="https://www.nafees.info" target="_blank" rel="noreferrer"
        style={{ color: "inherit", textDecoration: "underline" }}>© 2026 Nafees Mansoor</a>
    </p>
  );
}

function Shell({ me, health, onSignOut }: { me: Me; health: Health | null; onSignOut: () => void }) {
  const route = useHashRoute();
  const [menu, setMenu] = useState(false);
  const [theme, setTheme] = useState<string>(() => {
    try { return localStorage.getItem("stackloom-theme") || ""; } catch { return ""; }
  });
  useEffect(() => {
    if (theme) document.documentElement.setAttribute("data-theme", theme);
    else document.documentElement.removeAttribute("data-theme");
    try { localStorage.setItem("stackloom-theme", theme); } catch { /* private mode */ }
  }, [theme]);
  useEffect(() => setMenu(false), [route]);

  const signOut = async () => {
    try { await api.post("/api/auth/logout"); } catch { /* already gone */ }
    onSignOut();
  };
  const parts = route.split("/").slice(1).map(decodeURIComponent);
  const base = "/" + (parts[0] ?? "");
  const full = route === "/docker/compose" ? "/docker/compose" : base;
  const page = (() => {
    switch (base) {
      case "/projects": return parts[1] ? <Project key={parts[1]} id={parts[1]} tab={parts[2]} /> : <Projects />;
      case "/discovery": return <Discovery />;
      case "/services": return <Services />;
      case "/ports": return <Ports />;
      case "/docker": return <Docker key={parts[1] ?? "x"} tab={parts[1]} />;
      case "/databases": return <Databases key={parts[1] ?? "list"} id={parts[1]} />;
      case "/codecortex": return <CodeMaps />;
      case "/graph": return <Graph key={parts[1] ?? "g"} project={parts[1]} />;
      case "/git": return parts[1] ? <GitRepo key={parts[1]} project={parts[1]} /> : <GitList />;
      case "/diagnostics": return <Diagnostics />;
      case "/tasks": return <Tasks />;
      case "/backups": return <Backups />;
      case "/activity": return <Activity />;
      case "/settings": return <Settings />;
      case "/about": return <About />;
      default: return <Overview />;
    }
  })();

  return (
    <div className="shell">
      <header className="topbar">
        <button className="icon-btn menu-btn" aria-label="Menu" aria-expanded={menu} onClick={() => setMenu(!menu)}>☰</button>
        <a className="brand" href="#/"><Mark /> STACKLOOM</a>
        <span className="spacer" />
        <button className="icon-btn" title="Switch theme" aria-label="Switch theme"
          onClick={() => setTheme(theme === "dark" ? "light" : theme === "light" ? "" : "dark")}>
          {theme === "dark" ? "Dark" : theme === "light" ? "Light" : "Auto"}
        </button>
        <Bell />
        <span className="user">{me.username}</span>
        <button className="icon-btn" onClick={signOut}>Sign out</button>
      </header>
      <div className="body">
        <nav className={`side ${menu ? "open" : ""}`} aria-label="Main">
          {NAV.map((group, i) => (
            <div key={i}>
              {group.section && <div className="nav-section">{group.section}</div>}
              {group.items.map((item) => (
                <a key={item.href} className="nav-link" href={`#${item.href}`}
                  aria-current={(item.href === "/" ? route === "/" : item.href === full) ? "page" : undefined}>
                  {item.label}
                </a>
              ))}
            </div>
          ))}
          <div style={{ padding: "0 12px" }}><Footer health={health} inverse /></div>
        </nav>
        <main className="main" id="main">{page}</main>
      </div>
    </div>
  );
}

function SignIn({ onDone, health }: { onDone: (m: Me) => void; health: Health | null }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      onDone(await api.post<Me>("/api/auth/login", { username, password }));
    } catch (err) {
      setError((err as ApiError).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="auth">
      <form className="auth-card" onSubmit={submit}>
        <div className="brand"><Mark size={28} /> STACKLOOM</div>
        <h1>Sign in</h1>
        <p className="lede">One workspace. Every project. Complete control.</p>
        {error && <div className="notice notice-error" role="alert"><strong>Error:</strong> {error}</div>}
        <div className="field">
          <label htmlFor="u">Username</label>
          <input id="u" className="input" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
        </div>
        <div className="field">
          <label htmlFor="p">Password</label>
          <input id="p" className="input" type="password" autoComplete="current-password" value={password}
            onChange={(e) => setPassword(e.target.value)} required autoFocus />
        </div>
        <button className="btn btn-primary" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        <Footer health={health} />
      </form>
    </div>
  );
}

function ChangePassword({ me, onDone }: { me: Me; onDone: () => void }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (next !== again) { setError("The two new passwords differ."); return; }
    setBusy(true); setError("");
    try {
      await api.post("/api/auth/password", { current, new: next });
      onDone();
    } catch (err) {
      setError((err as ApiError).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="auth">
      <form className="auth-card" onSubmit={submit}>
        <div className="brand"><Mark size={28} /> STACKLOOM</div>
        <h1>Choose a new password</h1>
        <p className="lede">You signed in as {me.username} with the first-run password. Replace it before you continue.</p>
        {error && <div className="notice notice-error" role="alert"><strong>Error:</strong> {error}</div>}
        <div className="field">
          <label htmlFor="c">Current password</label>
          <input id="c" className="input" type="password" autoComplete="current-password" value={current}
            onChange={(e) => setCurrent(e.target.value)} required />
        </div>
        <div className="field">
          <label htmlFor="n">New password</label>
          <input id="n" className="input" type="password" autoComplete="new-password" value={next}
            onChange={(e) => setNext(e.target.value)} required minLength={10} />
          <span className="field-help">At least 10 characters, without the username.</span>
        </div>
        <div className="field">
          <label htmlFor="a">New password again</label>
          <input id="a" className="input" type="password" autoComplete="new-password" value={again}
            onChange={(e) => setAgain(e.target.value)} required />
        </div>
        <button className="btn btn-primary" disabled={busy}>{busy ? "Saving…" : "Save and continue"}</button>
      </form>
    </div>
  );
}
