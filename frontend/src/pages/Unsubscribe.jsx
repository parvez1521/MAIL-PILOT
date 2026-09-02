import { useEffect, useState } from "react";
import { useSearchParams, NavLink } from "react-router-dom";
import { motion } from "framer-motion";
import { Check, Mail, Loader2, ArrowRight, AlertTriangle } from "lucide-react";
import { api } from "../lib/apiClient";

export default function Unsubscribe() {
  const [params] = useSearchParams();
  const email = params.get("email") || "";
  const token = params.get("t") || "";
  const [state, setState] = useState("checking");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!email || !token) {
      setState("invalid");
      return;
    }
    api
      .get(`/unsubscribe/verify`, { params: { email, t: token } })
      .then((r) => setState(r.data.already_unsubscribed ? "done" : "ready"))
      .catch((e) => {
        setError(e?.response?.data?.detail || "This unsubscribe link is invalid.");
        setState("invalid");
      });
  }, [email, token]);

  async function confirm() {
    setState("submitting");
    try {
      await api.post(`/unsubscribe`, { email, token });
      setState("done");
    } catch (e) {
      setError(e?.response?.data?.detail || "Something went wrong. Please try again.");
      setState("invalid");
    }
  }

  return (
    <main className="unsub-shell">
      <motion.div
        className="unsub-card"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
      >
        <div className="unsub-mark">
          <span className="logo-mark">
            <Mail size={20} />
          </span>
          MailPilot
        </div>

        {state === "checking" && (
          <div className="unsub-body">
            <Loader2 size={22} className="spin" />
            <h1>Checking your link…</h1>
            <p className="muted">This will only take a moment.</p>
          </div>
        )}

        {state === "ready" && (
          <div className="unsub-body">
            <span className="large-icon"><Mail size={22} /></span>
            <h1>Unsubscribe from MailPilot emails?</h1>
            <p className="muted">
              We will stop sending marketing emails from this workspace to
              <b> {email}</b>. You can resubscribe later by asking the sender.
            </p>
            <button
              className="primary-btn"
              data-testid="unsubscribe-confirm-button"
              onClick={confirm}
            >
              Confirm unsubscribe <ArrowRight size={17} />
            </button>
          </div>
        )}

        {state === "submitting" && (
          <div className="unsub-body">
            <Loader2 size={22} className="spin" />
            <h1>Removing you from the list…</h1>
          </div>
        )}

        {state === "done" && (
          <motion.div
            className="unsub-body"
            initial={{ scale: 0.96 }}
            animate={{ scale: 1 }}
            transition={{ type: "spring", stiffness: 300, damping: 20 }}
          >
            <span className="success-badge"><Check size={22} /></span>
            <h1 data-testid="unsubscribe-success">You are unsubscribed.</h1>
            <p className="muted">
              <b>{email}</b> will no longer receive marketing campaigns from this workspace.
            </p>
          </motion.div>
        )}

        {state === "invalid" && (
          <div className="unsub-body">
            <span className="error-badge"><AlertTriangle size={22} /></span>
            <h1 data-testid="unsubscribe-error">Unsubscribe link is invalid</h1>
            <p className="muted">{error || "The link may have been altered or expired."}</p>
            <NavLink to="/" className="secondary-btn">
              Back to MailPilot
            </NavLink>
          </div>
        )}
      </motion.div>
    </main>
  );
}
