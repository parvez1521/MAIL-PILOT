import { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import {
  Users,
  Upload,
  Check,
  AlertTriangle,
  ArrowRight,
  Loader2,
  Send,
  Sparkles,
  Mail,
} from "lucide-react";
import { api, auth, errorText, isValidEmail } from "../lib/apiClient";
import { Page, Status } from "../components/Layout";

const STEP_LABELS = ["Details", "Validate", "Preview", "Test email", "Confirm", "Complete"];

const fadeSlide = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -8 },
  transition: { duration: 0.22, ease: "easeOut" },
};

function Steps({ step }) {
  const reduce = useReducedMotion();
  return (
    <div className="steps" data-testid="workflow-steps">
      {STEP_LABELS.map((label, i) => {
        const idx = i + 1;
        const done = step > idx;
        const active = step === idx;
        return (
          <motion.div
            key={label}
            className={`step ${done ? "done" : ""} ${active ? "active" : ""}`}
            data-testid={`workflow-step-${idx}`}
            initial={false}
            animate={{ scale: active && !reduce ? 1.04 : 1 }}
            transition={{ type: "spring", stiffness: 320, damping: 22 }}
          >
            <span>{done ? "✓" : idx}</span>
            <small>{label}</small>
          </motion.div>
        );
      })}
    </div>
  );
}

function DetailsStep({ form, setForm, onSubmit, error, submitting }) {
  const [drag, setDrag] = useState(false);
  const inputRef = useRef(null);
  function handleDrop(e) {
    e.preventDefault();
    setDrag(false);
    const file = e.dataTransfer.files?.[0];
    if (file) setForm((f) => ({ ...f, file }));
  }
  return (
    <motion.section className="form-section" {...fadeSlide}>
      <div className="form-intro">
        <span className="large-icon">
          <Users size={22} />
        </span>
        <div>
          <h2>Campaign details</h2>
          <p>Start with the message, then upload your CSV of recipients.</p>
        </div>
      </div>
      <form className="mail-form" onSubmit={onSubmit}>
        <label>
          Campaign name
          <input
            data-testid="campaign-name-input"
            required
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
        </label>
        <label>
          Subject
          <input
            data-testid="campaign-subject-input"
            required
            value={form.subject}
            onChange={(e) => setForm({ ...form, subject: e.target.value })}
          />
        </label>
        <label>
          Email body
          <textarea
            data-testid="campaign-body-input"
            required
            value={form.body}
            onChange={(e) => setForm({ ...form, body: e.target.value })}
          />
        </label>
        <label
          className={`upload-box ${drag ? "dragging" : ""} ${form.file ? "has-file" : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDrag(true);
          }}
          onDragLeave={() => setDrag(false)}
          onDrop={handleDrop}
        >
          <Upload size={20} />
          <b>{form.file?.name || (drag ? "Drop the CSV here" : "Upload your CSV")}</b>
          <small>One email per row · maximum 500 valid recipients</small>
          <input
            ref={inputRef}
            data-testid="campaign-csv-input"
            required
            type="file"
            accept=".csv"
            onChange={(e) => setForm({ ...form, file: e.target.files[0] })}
          />
        </label>
        {error && (
          <motion.div className="error" data-testid="bulk-error" {...fadeSlide}>
            {error}
          </motion.div>
        )}
        <button className="primary-btn" data-testid="campaign-continue-button" disabled={submitting}>
          {submitting ? (
            <>
              <Loader2 size={17} className="spin" /> Validating…
            </>
          ) : (
            <>
              Validate recipients <ArrowRight size={17} />
            </>
          )}
        </button>
      </form>
    </motion.section>
  );
}

function ValidateStep({ data, onNext }) {
  const cleaned = data.auto_cleaned_count || 0;
  return (
    <motion.div {...fadeSlide}>
      <div className="count-grid">
        <div>
          <strong data-testid="valid-recipient-count">{data.campaign.valid_count}</strong>
          <span>Valid recipients</span>
        </div>
        <div>
          <strong data-testid="invalid-recipient-count">{data.campaign.invalid_count}</strong>
          <span>Invalid entries</span>
        </div>
        <div>
          <strong data-testid="auto-cleaned-count">{cleaned}</strong>
          <span>Auto-cleaned (bounces / suppressions)</span>
        </div>
      </div>
      {cleaned > 0 && (
        <motion.div
          className="notice ok-notice"
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          data-testid="auto-cleaned-notice"
        >
          <Sparkles size={18} />
          <div>
            <b>{cleaned} recipient{cleaned === 1 ? "" : "s"} auto-cleaned</b>
            <p>
              {data.auto_cleaned_emails?.slice(0, 3).join(", ")}
              {cleaned > 3 ? `, and ${cleaned - 3} more` : ""} previously bounced, complained, or unsubscribed.
              We removed them so your reputation stays healthy.
            </p>
          </div>
        </motion.div>
      )}
      <button
        className="primary-btn"
        data-testid="review-preview-button"
        onClick={onNext}
      >
        Review campaign <ArrowRight size={17} />
      </button>
    </motion.div>
  );
}

function PreviewStep({ data, onNext }) {
  return (
    <motion.div {...fadeSlide}>
      <div className="preview-box">
        <p>PREVIEW</p>
        <h3>{data.campaign.subject}</h3>
        <div>{data.campaign.body}</div>
      </div>
      <button className="primary-btn" data-testid="preview-test-button" onClick={onNext}>
        Continue to test email <ArrowRight size={17} />
      </button>
    </motion.div>
  );
}

function TestStep({ test, setTest, onSend, error, sending }) {
  return (
    <motion.div {...fadeSlide}>
      <div className="notice">
        <AlertTriangle size={20} />
        <b>Before sending this campaign, you must send a test email.</b>
      </div>
      <label>
        Test recipient email
        <input
          data-testid="campaign-test-recipient-input"
          type="email"
          value={test}
          onChange={(e) => setTest(e.target.value)}
          placeholder="you@example.com"
        />
      </label>
      {error && (
        <motion.div className="error" data-testid="campaign-test-error" {...fadeSlide}>
          {error}
        </motion.div>
      )}
      <button
        className="primary-btn"
        data-testid="campaign-test-send-button"
        onClick={onSend}
        disabled={sending}
      >
        {sending ? (
          <>
            <Loader2 size={17} className="spin" /> Sending test…
          </>
        ) : (
          <>
            Send test email <ArrowRight size={17} />
          </>
        )}
      </button>
    </motion.div>
  );
}

function ConfirmStep({ onConfirm, onEdit, confirming }) {
  return (
    <motion.div {...fadeSlide}>
      <motion.div
        className="success large-success"
        data-testid="campaign-test-sent-message"
        initial={{ opacity: 0, scale: 0.96 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.3 }}
      >
        <Check size={18} /> Test email sent. Please check your inbox before continuing.
      </motion.div>
      <div className="confirm-actions">
        <button
          className="secondary-btn"
          data-testid="campaign-edit-button"
          onClick={onEdit}
          disabled={confirming}
        >
          Edit campaign
        </button>
        <button
          className="primary-btn"
          data-testid="campaign-confirm-button"
          onClick={onConfirm}
          disabled={confirming}
        >
          {confirming ? (
            <>
              <Loader2 size={17} className="spin" /> Preparing…
            </>
          ) : (
            <>
              Yes, continue to bulk send <ArrowRight size={17} />
            </>
          )}
        </button>
      </div>
    </motion.div>
  );
}

function ReadyStep({ onSend, sending, total }) {
  return (
    <motion.div {...fadeSlide}>
      <div className="ready-panel">
        <span className="ready-icon">
          <Send size={20} />
        </span>
        <div>
          <h3>Ready to send</h3>
          <p>
            {total} recipient{total === 1 ? "" : "s"} will be queued for delivery through Resend.
            You can watch progress on the next screen.
          </p>
        </div>
      </div>
      <button
        className="primary-btn"
        data-testid="campaign-send-button"
        onClick={onSend}
        disabled={sending}
      >
        {sending ? (
          <>
            <Loader2 size={17} className="spin" /> Queueing…
          </>
        ) : (
          <>
            Send campaign <ArrowRight size={17} />
          </>
        )}
      </button>
    </motion.div>
  );
}

function AnimatedCounter({ value }) {
  const [display, setDisplay] = useState(value);
  useEffect(() => {
    if (display === value) return;
    const start = display;
    const diff = value - start;
    const duration = 500;
    const t0 = performance.now();
    let raf;
    const tick = (t) => {
      const p = Math.min(1, (t - t0) / duration);
      setDisplay(Math.round(start + diff * p));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value]); // eslint-disable-line
  return <>{display}</>;
}

function ProgressStep({ campaignId, onStatus }) {
  const [detail, setDetail] = useState(null);
  const stop = useRef(false);
  useEffect(() => {
    stop.current = false;
    let timer;
    const tick = async () => {
      try {
        const r = await api.get(`/campaigns/${campaignId}/progress`, auth());
        if (stop.current) return;
        setDetail(r.data);
        onStatus?.(r.data.status);
        if (["QUEUED", "READY_TO_SEND", "SENDING"].includes(r.data.status)) {
          timer = setTimeout(tick, 2000);
        }
      } catch {
        timer = setTimeout(tick, 3500);
      }
    };
    tick();
    return () => {
      stop.current = true;
      if (timer) clearTimeout(timer);
    };
  }, [campaignId]);

  const total = detail?.total_recipients || 0;
  const sent = (detail?.sent_count || 0) + (detail?.delivered_count || 0);
  const pct = useMemo(() => {
    if (!detail) return 0;
    return Math.min(100, Math.round(detail.progress_percentage || 0));
  }, [detail]);
  const isDone = detail?.status === "COMPLETED";

  return (
    <motion.div {...fadeSlide}>
      <div className="progress-head">
        <div>
          <p className="eyebrow">LIVE PROGRESS</p>
          <h2>{isDone ? "Campaign completed" : "Sending your campaign"}</h2>
          <p className="muted">
            {isDone
              ? "All recipients have been processed. Provider events will keep delivery counts fresh."
              : "This screen updates automatically every two seconds until the queue is drained."}
          </p>
        </div>
        <Status status={detail?.status || "SENDING"} />
      </div>

      <div className="progress-bar" data-testid="campaign-progress-bar">
        <motion.span
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.6, ease: "easeOut" }}
        />
      </div>
      <div className="progress-meta">
        <span data-testid="progress-percentage">{pct}%</span>
        <span>
          {sent} of {total} sent
        </span>
      </div>

      <div className="progress-grid">
        <div>
          <b data-testid="progress-sent">
            <AnimatedCounter value={detail?.sent_count || 0} />
          </b>
          <small>Sent</small>
        </div>
        <div>
          <b data-testid="progress-delivered">
            <AnimatedCounter value={detail?.delivered_count || 0} />
          </b>
          <small>Delivered</small>
        </div>
        <div>
          <b data-testid="progress-bounced">
            <AnimatedCounter value={detail?.bounced_count || 0} />
          </b>
          <small>Bounced</small>
        </div>
        <div>
          <b data-testid="progress-complained">
            <AnimatedCounter value={detail?.complained_count || 0} />
          </b>
          <small>Complained</small>
        </div>
        <div>
          <b data-testid="progress-failed">
            <AnimatedCounter value={detail?.failed_count || 0} />
          </b>
          <small>Failed</small>
        </div>
        <div>
          <b data-testid="progress-suppressed">
            <AnimatedCounter value={detail?.suppressed_count || 0} />
          </b>
          <small>Suppressed</small>
        </div>
      </div>

      <AnimatePresence>
        {isDone && (
          <motion.div
            className="complete-state"
            data-testid="campaign-complete-message"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.35 }}
          >
            <motion.span
              initial={{ scale: 0.7 }}
              animate={{ scale: 1 }}
              transition={{ type: "spring", stiffness: 260, damping: 18 }}
            >
              <Check size={24} />
            </motion.span>
            <h2>Campaign completed</h2>
            <p>
              <Sparkles size={13} /> Delivery events will keep bouncing in from Resend.
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

export default function Bulk() {
  const [step, setStep] = useState(1);
  const [form, setForm] = useState({ name: "", subject: "", body: "", file: null });
  const [data, setData] = useState(null);
  const [test, setTest] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [sending, setSending] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [dispatching, setDispatching] = useState(false);
  const [liveStatus, setLiveStatus] = useState(null);

  async function upload(e) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    const fd = new FormData();
    Object.entries(form).forEach(([k, v]) => v != null && fd.append(k, v));
    try {
      const r = await api.post("/campaigns", fd, {
        ...auth(),
        headers: { ...auth().headers, "Content-Type": "multipart/form-data" },
      });
      setData(r.data);
      setStep(2);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setSubmitting(false);
    }
  }

  async function sendTest() {
    if (!isValidEmail(test)) {
      setError("Enter a valid test recipient email");
      return;
    }
    setError("");
    setSending(true);
    try {
      await api.post(
        `/campaigns/${data.campaign.id}/test`,
        new URLSearchParams({ recipient: test }),
        { ...auth(), headers: { ...auth().headers, "Content-Type": "application/x-www-form-urlencoded" } },
      );
      setData({ ...data, campaign: { ...data.campaign, status: "TEST_SENT" } });
      setStep(5);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setSending(false);
    }
  }

  async function confirm() {
    setConfirming(true);
    try {
      await api.post(`/campaigns/${data.campaign.id}/confirm`, {}, auth());
      setData({ ...data, campaign: { ...data.campaign, status: "READY_TO_SEND" } });
      setStep(6);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setConfirming(false);
    }
  }

  async function dispatch() {
    setDispatching(true);
    try {
      await api.post(`/campaigns/${data.campaign.id}/send`, {}, auth());
      setStep(7);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setDispatching(false);
    }
  }

  return (
    <Page title="Build a bulk campaign." subtitle="A simple review process keeps every send intentional.">
      <Steps step={step} />
      <AnimatePresence mode="wait">
        {step === 1 && (
          <DetailsStep
            key="s1"
            form={form}
            setForm={setForm}
            onSubmit={upload}
            error={error}
            submitting={submitting}
          />
        )}
        {data && step > 1 && (
          <motion.section
            key={`s${step}`}
            className="review-section"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
          >
            <div className="review-top">
              <div>
                <p className="eyebrow">CAMPAIGN CHECKPOINT</p>
                <h2>{data.campaign.name}</h2>
              </div>
              <Status status={liveStatus || (step === 7 ? "SENDING" : data.campaign.status)} />
            </div>
            {step === 2 && <ValidateStep data={data} onNext={() => setStep(3)} />}
            {step === 3 && <PreviewStep data={data} onNext={() => setStep(4)} />}
            {step === 4 && (
              <TestStep
                test={test}
                setTest={setTest}
                onSend={sendTest}
                error={error}
                sending={sending}
              />
            )}
            {step === 5 && (
              <ConfirmStep
                onConfirm={confirm}
                onEdit={() => {
                  setError("");
                  setStep(1);
                }}
                confirming={confirming}
              />
            )}
            {step === 6 && (
              <ReadyStep
                onSend={dispatch}
                sending={dispatching}
                total={data.campaign.valid_count}
              />
            )}
            {step === 7 && <ProgressStep campaignId={data.campaign.id} onStatus={setLiveStatus} />}
          </motion.section>
        )}
      </AnimatePresence>
    </Page>
  );
}
