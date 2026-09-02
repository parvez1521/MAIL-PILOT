import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Globe,
  Check,
  Loader2,
  AlertTriangle,
  Trash2,
  RefreshCw,
  Copy,
  Plus,
  ExternalLink,
  ShieldCheck,
  Inbox,
  Clock,
} from "lucide-react";
import { api, auth, errorText } from "@/lib/apiClient";
import { Page } from "@/components/Layout";

function StatusBadge({ status }) {
  const map = {
    verified: { label: "Verified", tone: "ok" },
    pending: { label: "Pending verification", tone: "warn" },
    not_started: { label: "Not started", tone: "muted" },
    failed: { label: "Failed", tone: "err" },
    verifying: { label: "Verifying…", tone: "warn" },
    temporary_failure: { label: "Retrying", tone: "warn" },
  };
  const s = map[(status || "").toLowerCase()] || { label: status || "Unknown", tone: "muted" };
  return <span className={`domain-badge ${s.tone}`}>{s.label}</span>;
}

function DnsCopy({ value }) {
  const [copied, setCopied] = useState(false);
  if (!value) return <span>—</span>;
  return (
    <button
      className="copy-chip"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value);
          setCopied(true);
          setTimeout(() => setCopied(false), 1400);
        } catch {}
      }}
    >
      <code>{value.length > 44 ? value.slice(0, 44) + "…" : value}</code>
      {copied ? <Check size={13} /> : <Copy size={13} />}
    </button>
  );
}

function DnsRecords({ records }) {
  if (!records || records.length === 0) {
    return <p className="muted">No DNS records were returned. Try refreshing the domain.</p>;
  }
  return (
    <div className="dns-table" data-testid="dns-records">
      <div className="dns-head">
        <span>Type</span>
        <span>Host / Name</span>
        <span>Value</span>
        <span>TTL / Priority</span>
      </div>
      {records.map((r, i) => (
        <div key={i} className="dns-row">
          <span><code>{r.record || r.type}</code></span>
          <span><DnsCopy value={r.name} /></span>
          <span><DnsCopy value={r.value} /></span>
          <span className="muted">{r.ttl || "Auto"}{r.priority ? ` · P${r.priority}` : ""}</span>
        </div>
      ))}
    </div>
  );
}

export default function DomainSetup() {
  const [state, setState] = useState({ can_manage: false, domains: [], reason: "" });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [newDomain, setNewDomain] = useState("");
  const [creating, setCreating] = useState(false);
  const [busyId, setBusyId] = useState("");
  const [expanded, setExpanded] = useState("");
  const [sender, setSender] = useState({ sender_email: "", default_sender_email: "" });
  const [savingSender, setSavingSender] = useState(false);
  const [senderNote, setSenderNote] = useState("");
  const [method, setMethod] = useState({ method: "verified_domain", options: [] });

  async function refresh() {
    setLoading(true);
    try {
      const [dRes, sRes, mRes] = await Promise.all([
        api.get("/settings/domains", auth()),
        api.get("/settings/sender", auth()),
        api.get("/settings/sending-method", auth()),
      ]);
      setState(dRes.data);
      setSender((s) => ({ ...sRes.data, sender_email: sRes.data.sender_email || "" }));
      setMethod(mRes.data);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function addDomain(e) {
    e.preventDefault();
    setError("");
    setCreating(true);
    try {
      const r = await api.post("/settings/domains", { name: newDomain.trim().toLowerCase() }, auth());
      setNewDomain("");
      setExpanded(r.data.domain?.id || "");
      await refresh();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setCreating(false);
    }
  }

  async function verify(id) {
    setBusyId(id);
    try {
      await api.post(`/settings/domains/${id}/verify`, {}, auth());
      await refresh();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusyId("");
    }
  }

  async function remove(id) {
    if (!window.confirm("Remove this domain from Resend? Sends will fall back to the default sender.")) return;
    setBusyId(id);
    try {
      await api.delete(`/settings/domains/${id}`, auth());
      await refresh();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusyId("");
    }
  }

  async function saveSender(e) {
    e.preventDefault();
    setSenderNote("");
    setSavingSender(true);
    try {
      await api.put("/settings/sender", { sender_email: sender.sender_email.trim().toLowerCase() }, auth());
      setSenderNote("Sender address saved. New campaigns will use this address.");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setSavingSender(false);
    }
  }

  async function clearSender() {
    setSavingSender(true);
    try {
      await api.delete("/settings/sender", auth());
      setSender((s) => ({ ...s, sender_email: "" }));
      setSenderNote("Reverted to the default sender.");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setSavingSender(false);
    }
  }

  async function chooseMethod(id) {
    if (id === method.method) return;
    setError("");
    try {
      const r = await api.put("/settings/sending-method", { method: id }, auth());
      setMethod((m) => ({ ...m, method: r.data.method, mailbox_provider: r.data.mailbox_provider }));
    } catch (e) {
      setError(errorText(e));
    }
  }

  return (
    <Page
      title="Connect your sender domain."
      subtitle="Verify a domain with Resend so campaigns can reach anyone — not just your account owner."
    >
      <section className="settings-section" data-testid="sending-method-section">
        <div className="section-head">
          <div>
            <p className="eyebrow">SENDING METHOD</p>
            <h2>How you send</h2>
            <p className="muted">
              Choose the mode that fits this workspace. You can only send bulk campaigns from a verified
              domain — personal mailbox mode is limited to low-volume messages.
            </p>
          </div>
        </div>
        <div className="method-grid" data-testid="method-grid">
          {(method.options || []).map((opt) => {
            const active = method.method === opt.id;
            const Icon = opt.id === "verified_domain" ? ShieldCheck : Inbox;
            return (
              <button
                key={opt.id}
                type="button"
                onClick={() => opt.available && chooseMethod(opt.id)}
                className={`method-card ${active ? "active" : ""} ${!opt.available ? "disabled" : ""}`}
                data-testid={`method-${opt.id}`}
                disabled={!opt.available}
                aria-pressed={active}
              >
                <span className="method-icon"><Icon size={18} /></span>
                <div className="method-body">
                  <div className="method-title">
                    <b>{opt.name}</b>
                    {opt.coming_soon && (
                      <span className="method-tag" data-testid={`method-${opt.id}-badge`}>
                        <Clock size={11} /> Coming soon
                      </span>
                    )}
                    {active && <span className="method-check"><Check size={12} /> Selected</span>}
                  </div>
                  <p>{opt.description}</p>
                  {opt.max_recipients && (
                    <small className="method-meta">Max {opt.max_recipients} recipients per campaign</small>
                  )}
                  {opt.providers && (
                    <div className="method-subs">
                      {opt.providers.map((p) => (
                        <span key={p.id} className="method-sub">
                          {p.name}
                          {p.coming_soon && <em> · soon</em>}
                        </span>
                      ))}
                    </div>
                  )}
                  {opt.notes && <small className="method-note">{opt.notes}</small>}
                </div>
              </button>
            );
          })}
        </div>
      </section>

      <section className="settings-section" style={{ marginTop: 18 }} data-testid="sender-section">
        <div className="section-head">
          <div>
            <p className="eyebrow">FROM ADDRESS</p>
            <h2>Sender email</h2>
            <p className="muted">
              Used as the <b>From:</b> for every send from this workspace. Leave blank to use the default
              <code style={{ margin: "0 4px" }}>{sender.default_sender_email}</code>.
            </p>
          </div>
        </div>
        <form className="sender-form" onSubmit={saveSender}>
          <input
            type="email"
            placeholder="hello@yourdomain.com"
            value={sender.sender_email}
            onChange={(e) => setSender({ ...sender, sender_email: e.target.value })}
            data-testid="sender-email-input"
          />
          <div className="sender-actions">
            <button
              type="button"
              className="secondary-btn"
              onClick={clearSender}
              disabled={savingSender || !sender.sender_email}
              data-testid="sender-clear-button"
            >
              Use default
            </button>
            <button
              type="submit"
              className="primary-btn"
              disabled={savingSender || !sender.sender_email}
              data-testid="sender-save-button"
            >
              {savingSender ? <><Loader2 size={16} className="spin" /> Saving…</> : "Save sender"}
            </button>
          </div>
        </form>
        <AnimatePresence>
          {senderNote && (
            <motion.div
              className="success"
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              style={{ marginTop: 12 }}
              data-testid="sender-note"
            >
              <Check size={14} /> {senderNote}
            </motion.div>
          )}
        </AnimatePresence>
      </section>

      <section className="settings-section" style={{ marginTop: 18 }} data-testid="domain-section">
        <div className="section-head">
          <div>
            <p className="eyebrow">DOMAINS</p>
            <h2>Verified sender domains</h2>
            <p className="muted">
              Add your domain, add the DNS records shown, then click Verify. Only verified domains are safe
              for large campaigns.
            </p>
          </div>
          <button
            type="button"
            className="secondary-btn"
            onClick={refresh}
            data-testid="domain-refresh-button"
            disabled={loading}
          >
            <RefreshCw size={14} /> Refresh
          </button>
        </div>

        {error && (
          <motion.div className="error" data-testid="domain-error" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
            {error}
          </motion.div>
        )}

        {!state.can_manage && (
          <motion.div
            className="notice"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            data-testid="domain-restricted-notice"
          >
            <AlertTriangle size={20} />
            <div>
              <b>Domain management is unavailable with the current API key.</b>
              <p className="muted" style={{ marginTop: 4 }}>
                {state.reason || "Your Resend API key is sending-only."} Create a Full Access API key at{" "}
                <a href="https://resend.com/api-keys" target="_blank" rel="noreferrer">
                  resend.com/api-keys <ExternalLink size={12} />
                </a>{" "}
                and update <code>RESEND_API_KEY</code> in the backend .env, then restart the backend.
              </p>
            </div>
          </motion.div>
        )}

        {state.can_manage && (
          <>
            <form className="domain-form" onSubmit={addDomain}>
              <div className="domain-input">
                <Globe size={18} />
                <input
                  placeholder="yourdomain.com"
                  value={newDomain}
                  onChange={(e) => setNewDomain(e.target.value)}
                  data-testid="domain-input"
                  required
                />
              </div>
              <button className="primary-btn" data-testid="domain-add-button" disabled={creating}>
                {creating ? <><Loader2 size={16} className="spin" /> Adding…</> : (<><Plus size={16} /> Add domain</>)}
              </button>
            </form>

            <div className="domain-list" data-testid="domain-list">
              {loading && state.domains.length === 0 ? (
                <div className="loading" style={{ minHeight: 100 }}>
                  <Loader2 size={20} className="spin" /> <span>Loading domains…</span>
                </div>
              ) : state.domains.length === 0 ? (
                <div className="empty">
                  <div className="empty-icon"><Globe size={20} /></div>
                  <b>No domains yet</b>
                  <p>Add one above to get started with a verified From: address.</p>
                </div>
              ) : (
                state.domains.map((d) => (
                  <motion.div
                    key={d.id}
                    className="domain-card"
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    data-testid={`domain-${d.name}`}
                  >
                    <div className="domain-head" onClick={() => setExpanded(expanded === d.id ? "" : d.id)}>
                      <div>
                        <b>{d.name}</b>
                        <small>Added {d.created_at ? new Date(d.created_at).toLocaleDateString() : ""}</small>
                      </div>
                      <StatusBadge status={d.status} />
                    </div>
                    <AnimatePresence initial={false}>
                      {expanded === d.id && (
                        <motion.div
                          className="domain-body"
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: "auto", opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          transition={{ duration: 0.25 }}
                        >
                          <p className="muted" style={{ margin: "10px 0 14px" }}>
                            Add these records at your DNS provider (Cloudflare, Route53, GoDaddy, etc.), then click Verify.
                          </p>
                          <DnsRecords records={d.records} />
                          <div className="domain-actions">
                            <button
                              className="secondary-btn"
                              onClick={() => remove(d.id)}
                              disabled={busyId === d.id}
                              data-testid={`domain-remove-${d.name}`}
                            >
                              <Trash2 size={14} /> Remove
                            </button>
                            <button
                              className="primary-btn"
                              onClick={() => verify(d.id)}
                              disabled={busyId === d.id}
                              data-testid={`domain-verify-${d.name}`}
                            >
                              {busyId === d.id ? <><Loader2 size={14} className="spin" /> Verifying…</> : <><Check size={14} /> Verify domain</>}
                            </button>
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </motion.div>
                ))
              )}
            </div>
          </>
        )}
      </section>
    </Page>
  );
}
