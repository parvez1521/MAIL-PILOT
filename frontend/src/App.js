import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, NavLink, useNavigate, useLocation } from "react-router-dom";
import {
  Mail,
  LayoutDashboard,
  Send,
  Users,
  FlaskConical,
  Settings as SettingsIcon,
  LogOut,
  ArrowRight,
  Check,
  Menu,
  X,
  Loader2,
  Globe,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { api, auth, errorText } from "@/lib/apiClient";
import { Page, Status } from "@/components/Layout";
import Bulk from "@/pages/Bulk";
import Unsubscribe from "@/pages/Unsubscribe";
import CampaignDetail from "@/pages/CampaignDetail";
import DomainSetup from "@/pages/DomainSetup";
import "@/App.css";

function AuthPage({ signup = false }) {
  const [form, setForm] = useState({ email: "", password: "", name: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const nav = useNavigate();

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const r = await api.post(`/auth/${signup ? "register" : "login"}`, form);
      localStorage.setItem("mailpilot_token", r.data.token);
      nav("/");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-shell">
      <div className="auth-mark">
        <span className="logo-mark"><Mail size={20} /></span>
        MailPilot
      </div>
      <motion.section
        className="auth-panel"
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, ease: "easeOut" }}
      >
        <p className="eyebrow">CAMPAIGN WORKSPACE</p>
        <h1>{signup ? "Start sending with confidence." : "Welcome back."}</h1>
        <p className="auth-copy">
          Plan, validate, and review every campaign before it leaves your workspace.
        </p>
        <form onSubmit={submit}>
          {signup && (
            <input
              data-testid="auth-name-input"
              placeholder="Your name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          )}
          <input
            data-testid="auth-email-input"
            required
            type="email"
            placeholder="Work email"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
          <input
            data-testid="auth-password-input"
            required
            minLength={6}
            type="password"
            placeholder="Password"
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
          />
          <AnimatePresence>
            {error && (
              <motion.div
                className="error"
                data-testid="auth-error"
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
              >
                {error}
              </motion.div>
            )}
          </AnimatePresence>
          <button className="primary-btn full" data-testid="auth-submit-button" disabled={busy}>
            {busy ? <><Loader2 size={17} className="spin" /> Working…</> : (<>{signup ? "Create account" : "Sign in"} <ArrowRight size={17} /></>)}
          </button>
        </form>
        <p className="switch-auth">
          {signup ? "Already have an account?" : "New to MailPilot?"}{" "}
          <NavLink data-testid="auth-switch-link" to={signup ? "/login" : "/signup"}>
            {signup ? "Sign in" : "Create an account"}
          </NavLink>
        </p>
      </motion.section>
    </main>
  );
}

function Shell({ children }) {
  const [open, setOpen] = useState(false);
  const nav = useNavigate();
  const loc = useLocation();
  const links = [
    ["/", "Overview", LayoutDashboard],
    ["/single", "Single mail", Send],
    ["/bulk", "Bulk campaign", Users],
    ["/test", "Test mail", FlaskConical],
    ["/domain", "Sender domain", Globe],
  ];
  function logout() {
    localStorage.removeItem("mailpilot_token");
    nav("/login");
  }
  return (
    <div className="app-shell">
      <aside className={open ? "sidebar open" : "sidebar"}>
        <div className="brand">
          <span className="logo-mark"><Mail size={19} /></span>
          <b>MailPilot</b>
          <button className="mobile-close" onClick={() => setOpen(false)} data-testid="close-menu-button">
            <X size={20} />
          </button>
        </div>
        <div className="side-label">WORKSPACE</div>
        <nav>
          {links.map(([url, label, Icon]) => (
            <NavLink
              key={url}
              data-testid={`nav-${label.toLowerCase().replace(" ", "-")}`}
              className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
              to={url}
              onClick={() => setOpen(false)}
              end={url === "/"}
            >
              <Icon size={18} />
              <span>{label}</span>
              {loc.pathname === url && <i />}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <NavLink className="nav-link" data-testid="nav-settings" to="/settings">
            <SettingsIcon size={18} />
            <span>Settings</span>
          </NavLink>
          <button className="nav-link logout" data-testid="logout-button" onClick={logout}>
            <LogOut size={18} />
            <span>Sign out</span>
          </button>
          <div className="user-chip">
            <span className="avatar">MP</span>
            <div>
              <strong>My workspace</strong>
              <small>Resend connected</small>
            </div>
          </div>
        </div>
      </aside>
      <div className="main-area">
        <header className="topbar">
          <button className="menu-button" onClick={() => setOpen(true)} data-testid="open-menu-button">
            <Menu size={20} />
          </button>
          <span className="crumb">
            {loc.pathname === "/" ? "Overview" : loc.pathname.slice(1).replace("-", " ")}
          </span>
          <span className="test-pill"><span /> Resend live</span>
        </header>
        {children}
      </div>
    </div>
  );
}

function Dashboard() {
  const [campaigns, setCampaigns] = useState([]);
  const [usage, setUsage] = useState({ limit: 500, used: 0 });
  const nav = useNavigate();
  useEffect(() => {
    Promise.all([api.get("/campaigns", auth()), api.get("/usage", auth())])
      .then(([a, b]) => {
        setCampaigns(a.data);
        setUsage(b.data);
      })
      .catch(() => {});
  }, []);
  const cards = [
    ["single-mail-card", "Single mail", "Send one considered message", Send, "/single", "blue"],
    ["bulk-mail-card", "Bulk campaign", "Reach a validated audience", Users, "/bulk", "green"],
    ["test-mail-card", "Test mail", "Preview before you send", FlaskConical, "/test", "amber"],
  ];
  return (
    <Page title="Good to see you. Let's ship something clear." subtitle="Your campaign workspace is ready when you are.">
      <div className="quick-grid">
        {cards.map(([id, title, desc, Icon, url, tone], i) => (
          <motion.button
            key={id}
            data-testid={id}
            onClick={() => nav(url)}
            className={`quick-card ${tone}`}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: i * 0.06 }}
            whileHover={{ y: -4 }}
          >
            <span className="icon-box"><Icon size={19} /></span>
            <div>
              <b>{title}</b>
              <small>{desc}</small>
            </div>
            <ArrowRight size={18} />
          </motion.button>
        ))}
      </div>
      <div className="dashboard-grid">
        <motion.section
          className="usage-panel"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.18 }}
        >
          <div className="section-head">
            <div>
              <p className="eyebrow">CAMPAIGN CAPACITY</p>
              <h2>Recipient limit</h2>
            </div>
            <span className="limit-tag">500 max</span>
          </div>
          <div className="usage-number" data-testid="recipient-usage">
            <strong>{usage.used}</strong>
            <span>/ {usage.limit} recipients used</span>
          </div>
          <div className="meter">
            <motion.span
              initial={{ width: 0 }}
              animate={{ width: `${Math.min((usage.used / usage.limit) * 100, 100)}%` }}
              transition={{ duration: 0.7, ease: "easeOut" }}
            />
          </div>
          <p className="muted">
            Each campaign can include up to 500 unique, valid addresses.
          </p>
        </motion.section>
        <motion.section
          className="recent-panel"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.24 }}
        >
          <div className="section-head">
            <div>
              <p className="eyebrow">ACTIVITY</p>
              <h2>Recent campaigns</h2>
            </div>
            <NavLink data-testid="view-all-campaigns" to="/bulk">
              New campaign <ArrowRight size={14} />
            </NavLink>
          </div>
          {campaigns.length ? (
            campaigns.slice(0, 5).map((c) => (
              <NavLink
                key={c.id}
                to={`/campaigns/${c.id}`}
                className="campaign-row"
                data-testid={`campaign-row-${c.id}`}
              >
                <span className="campaign-dot" />
                <div>
                  <b>{c.name}</b>
                  <small>{c.recipient_count} recipients</small>
                </div>
                <Status status={c.status} />
              </NavLink>
            ))
          ) : (
            <div className="empty" data-testid="campaigns-empty">
              <div className="empty-icon"><Mail size={20} /></div>
              <b>No campaigns yet</b>
              <p>Your first campaign will appear here.</p>
            </div>
          )}
        </motion.section>
      </div>
    </Page>
  );
}

function Composer({ kind = "single" }) {
  const [form, setForm] = useState({ recipient: "", subject: "", body: "" });
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const Icon = kind === "single" ? Send : FlaskConical;
  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setSent(false);
    setError("");
    try {
      await api.post(`/mail/${kind}`, form, auth());
      setSent(true);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Page
      title={kind === "single" ? "Send a single mail." : "Send a test mail."}
      subtitle={
        kind === "single"
          ? "A focused message for one recipient."
          : "A real provider submission for a safe inbox check."
      }
    >
      <section className="form-section">
        <div className="form-intro">
          <span className="large-icon"><Icon size={22} /></span>
          <div>
            <h2>{kind === "single" ? "Single mail" : "Test mail"}</h2>
            <p>Resend is connected. Delivery status will follow provider events.</p>
          </div>
        </div>
        <form className="mail-form" onSubmit={submit}>
          <label>
            Recipient email
            <input
              data-testid={`${kind}-recipient-input`}
              required
              type="email"
              value={form.recipient}
              onChange={(e) => setForm({ ...form, recipient: e.target.value })}
            />
          </label>
          <label>
            Subject
            <input
              data-testid={`${kind}-subject-input`}
              required
              value={form.subject}
              onChange={(e) => setForm({ ...form, subject: e.target.value })}
            />
          </label>
          <label>
            Email body
            <textarea
              data-testid={`${kind}-body-input`}
              required
              value={form.body}
              onChange={(e) => setForm({ ...form, body: e.target.value })}
            />
          </label>
          <AnimatePresence>
            {error && (
              <motion.div
                className="error"
                data-testid={`${kind}-error`}
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
              >
                {error}
              </motion.div>
            )}
            {sent && (
              <motion.div
                className="success"
                data-testid={`${kind}-success`}
                initial={{ opacity: 0, scale: 0.97 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0 }}
              >
                <Check size={17} />{" "}
                {kind === "single"
                  ? "Single email submitted successfully."
                  : "Test email submitted successfully."}
              </motion.div>
            )}
          </AnimatePresence>
          <button className="primary-btn" data-testid={`${kind}-send-button`} disabled={busy}>
            {busy ? (
              <><Loader2 size={17} className="spin" /> Sending…</>
            ) : (
              <>{kind === "single" ? "Send single email" : "Send test email"} <ArrowRight size={17} /></>
            )}
          </button>
        </form>
      </section>
    </Page>
  );
}

function Settings() {
  return (
    <Page title="Workspace settings." subtitle="Keep your account details close and your limits clear.">
      <section className="settings-section">
        <div className="setting-row">
          <div>
            <p className="eyebrow">DELIVERY MODE</p>
            <h2>Resend is connected</h2>
            <p className="muted">
              Emails are submitted server-side through the configured provider. API keys never
              reach the browser.
            </p>
          </div>
          <span className="setting-badge"><span /> Active</span>
        </div>
        <div className="setting-row">
          <div>
            <p className="eyebrow">SAFEGUARDS</p>
            <h2>Test-first bulk sends</h2>
            <p className="muted">
              Every bulk campaign requires a successful test email and an explicit confirmation before
              recipients are queued.
            </p>
          </div>
          <span className="setting-badge blue-badge"><span /> Enforced</span>
        </div>
        <div className="setting-row">
          <div>
            <p className="eyebrow">SUPPRESSIONS</p>
            <h2>Unsubscribe honored</h2>
            <p className="muted">
              Every marketing email carries a one-click unsubscribe link. Suppressions are checked before
              each recipient is queued.
            </p>
          </div>
          <span className="setting-badge blue-badge"><span /> Server-side</span>
        </div>
      </section>
    </Page>
  );
}

function Protected() {
  const [user, setUser] = useState(null);
  const nav = useNavigate();
  useEffect(() => {
    api
      .get("/auth/me", auth())
      .then((r) => setUser(r.data))
      .catch(() => nav("/login"));
  }, [nav]);
  return user ? (
    <Shell>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/single" element={<Composer />} />
        <Route path="/test" element={<Composer kind="test" />} />
        <Route path="/bulk" element={<Bulk />} />
        <Route path="/campaigns/:id" element={<CampaignDetail />} />
        <Route path="/domain" element={<DomainSetup />} />
        <Route path="/settings" element={<Settings />} />
      </Routes>
    </Shell>
  ) : (
    <div className="loading">
      <Loader2 size={22} className="spin" />
      <span>Loading workspace…</span>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<AuthPage />} />
        <Route path="/signup" element={<AuthPage signup />} />
        <Route path="/unsubscribe" element={<Unsubscribe />} />
        <Route path="*" element={<Protected />} />
      </Routes>
    </BrowserRouter>
  );
}
