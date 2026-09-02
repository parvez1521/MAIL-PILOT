import { useEffect, useMemo, useState } from "react";
import { useParams, NavLink } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowLeft,
  Mail,
  Check,
  X,
  AlertTriangle,
  Loader2,
  Ban,
  ShieldOff,
  Send,
  Radio,
} from "lucide-react";
import { api, auth, errorText } from "@/lib/apiClient";
import { Page, Status } from "@/components/Layout";

const STATUS_META = {
  ALL: { label: "All", icon: Mail, tone: "muted" },
  QUEUED: { label: "Queued", icon: Loader2, tone: "muted" },
  SENDING: { label: "Sending", icon: Send, tone: "warn" },
  SENT: { label: "Sent", icon: Check, tone: "info" },
  DELIVERED: { label: "Delivered", icon: Check, tone: "ok" },
  BOUNCED: { label: "Bounced", icon: AlertTriangle, tone: "err" },
  COMPLAINED: { label: "Complained", icon: Ban, tone: "err" },
  FAILED: { label: "Failed", icon: X, tone: "err" },
  SUPPRESSED: { label: "Suppressed", icon: ShieldOff, tone: "muted" },
};

function formatDate(v) {
  if (!v) return "—";
  try {
    return new Date(v).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return v;
  }
}

const EVENT_META = {
  sent: { label: "Sent", tone: "info", icon: Send },
  delivered: { label: "Delivered", tone: "ok", icon: Check },
  bounced: { label: "Bounced", tone: "err", icon: AlertTriangle },
  complained: { label: "Complained", tone: "err", icon: Ban },
  failed: { label: "Failed", tone: "err", icon: X },
  suppressed: { label: "Suppressed", tone: "muted", icon: ShieldOff },
};

function relativeTime(ts) {
  if (!ts) return "";
  const diff = Math.max(0, (Date.now() - new Date(ts).getTime()) / 1000);
  if (diff < 5) return "just now";
  if (diff < 60) return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return new Date(ts).toLocaleDateString();
}

function DeliveryFeed({ campaignId, live }) {
  const [events, setEvents] = useState([]);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let cancelled = false;
    let timer;
    const load = async () => {
      try {
        const r = await api.get(`/campaigns/${campaignId}/events`, { ...auth(), params: { limit: 30 } });
        if (cancelled) return;
        setEvents(r.data.events || []);
      } catch {}
      if (!cancelled) timer = setTimeout(load, live ? 3000 : 15000);
    };
    load();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [campaignId, live]);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 15000);
    return () => clearInterval(id);
  }, []);
  return (
    <section className="feed-section" data-testid="delivery-feed">
      <div className="feed-head">
        <div>
          <p className="eyebrow">LIVE DELIVERY FEED</p>
          <h2>Recent inbox activity</h2>
        </div>
        <span className={`feed-live ${live ? "on" : ""}`} title={live ? "Auto-refreshing" : "Idle"}>
          <Radio size={14} /> {live ? "Live" : "Idle"}
        </span>
      </div>
      {events.length === 0 ? (
        <div className="feed-empty" data-testid="feed-empty">
          <span className="empty-icon"><Radio size={18} /></span>
          <b>No delivery events yet</b>
          <p>Delivery, bounce, and complaint events from Resend will appear here.</p>
        </div>
      ) : (
        <ol className="feed-list" aria-hidden={tick /* re-render for relative times */}>
          <AnimatePresence initial={false}>
            {events.map((e) => {
              const meta = EVENT_META[e.type] || { label: e.type, tone: "muted", icon: Mail };
              const Icon = meta.icon;
              return (
                <motion.li
                  key={e.id}
                  className={`feed-item ${meta.tone}`}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.25 }}
                  data-testid={`feed-item-${e.type}`}
                >
                  <span className="feed-dot"><Icon size={12} /></span>
                  <div className="feed-body">
                    <b>{meta.label}</b>
                    <span className="feed-email">{e.email}</span>
                    {e.reason && <em>{e.reason}</em>}
                  </div>
                  <span className="feed-time">{relativeTime(e.at)}</span>
                </motion.li>
              );
            })}
          </AnimatePresence>
        </ol>
      )}
    </section>
  );
}

export default function CampaignDetail() {
  const { id } = useParams();
  const [campaign, setCampaign] = useState(null);
  const [recipients, setRecipients] = useState([]);
  const [filter, setFilter] = useState("ALL");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const [c, r] = await Promise.all([
          api.get(`/campaigns/${id}`, auth()),
          api.get(`/campaigns/${id}/recipients`, auth()),
        ]);
        if (cancelled) return;
        setCampaign(c.data);
        setRecipients(r.data.recipients);
        setLoading(false);
        if (["QUEUED", "READY_TO_SEND", "SENDING"].includes(c.data.status)) {
          setTimeout(load, 3000);
        }
      } catch (e) {
        if (!cancelled) {
          setError(errorText(e));
          setLoading(false);
        }
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [id]);

  const filtered = useMemo(() => {
    if (filter === "ALL") return recipients;
    return recipients.filter((r) => r.sending_status === filter);
  }, [recipients, filter]);

  const stats = useMemo(() => {
    const s = {};
    recipients.forEach((r) => {
      s[r.sending_status] = (s[r.sending_status] || 0) + 1;
    });
    return s;
  }, [recipients]);

  if (loading) {
    return (
      <Page title="Loading campaign…" subtitle="One moment while we fetch the details.">
        <div className="loading" style={{ minHeight: 240 }}>
          <Loader2 size={22} className="spin" />
          <span>Loading…</span>
        </div>
      </Page>
    );
  }

  if (error || !campaign) {
    return (
      <Page title="Campaign not found." subtitle="This campaign may have been removed.">
        <div className="error" data-testid="campaign-detail-error">
          {error || "We could not find that campaign."}
        </div>
        <NavLink to="/" className="secondary-btn" style={{ marginTop: 16 }}>
          <ArrowLeft size={16} /> Back to overview
        </NavLink>
      </Page>
    );
  }

  return (
    <Page title={campaign.name} subtitle={`Subject · ${campaign.subject}`}>
      <div className="detail-top">
        <NavLink to="/" className="back-link" data-testid="campaign-back-link">
          <ArrowLeft size={14} /> Back to overview
        </NavLink>
        <Status status={campaign.status} />
      </div>

      <DeliveryFeed
        campaignId={campaign.id}
        live={["QUEUED", "READY_TO_SEND", "SENDING"].includes(campaign.status)}
      />

      <div className="detail-metrics">
        {[
          ["Total", campaign.total_recipients, "muted"],
          ["Delivered", campaign.delivered_count, "ok"],
          ["Sent", campaign.sent_count, "info"],
          ["Bounced", campaign.bounced_count, "err"],
          ["Complained", campaign.complained_count, "err"],
          ["Failed", campaign.failed_count, "err"],
        ].map(([label, value, tone]) => (
          <motion.div
            key={label}
            className={`metric-card ${tone}`}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
          >
            <b data-testid={`metric-${label.toLowerCase()}`}>{value || 0}</b>
            <small>{label}</small>
          </motion.div>
        ))}
      </div>

      <div className="filter-row" data-testid="recipient-filters">
        {Object.entries(STATUS_META).map(([key, meta]) => {
          const count = key === "ALL" ? recipients.length : stats[key] || 0;
          const active = filter === key;
          return (
            <button
              key={key}
              onClick={() => setFilter(key)}
              className={`filter-chip ${meta.tone} ${active ? "active" : ""}`}
              data-testid={`filter-${key.toLowerCase()}`}
            >
              {meta.label}
              <span>{count}</span>
            </button>
          );
        })}
      </div>

      <section className="recipients-table" data-testid="recipients-table">
        <div className="recipients-head">
          <span>Recipient</span>
          <span>Status</span>
          <span>Sent</span>
          <span>Delivered</span>
          <span>Reason</span>
        </div>
        <AnimatePresence initial={false}>
          {filtered.length === 0 ? (
            <motion.div
              key="empty"
              className="recipients-empty"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              data-testid="recipients-empty"
            >
              <Mail size={18} />
              <b>No recipients match this filter</b>
              <p>Try a different status or send the campaign to see updates.</p>
            </motion.div>
          ) : (
            filtered.map((r, i) => (
              <motion.div
                key={r.id}
                className="recipients-row"
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.18, delay: Math.min(i, 20) * 0.01 }}
                data-testid={`recipient-row-${r.email}`}
              >
                <span title={r.email}>{r.email}</span>
                <span><Status status={r.sending_status} /></span>
                <span>{formatDate(r.sent_at)}</span>
                <span>{formatDate(r.delivered_at)}</span>
                <span className="reason" title={r.failure_reason || ""}>
                  {r.failure_reason || "—"}
                </span>
              </motion.div>
            ))
          )}
        </AnimatePresence>
      </section>
    </Page>
  );
}
