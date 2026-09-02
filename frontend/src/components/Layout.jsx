import { motion } from "framer-motion";

export function Page({ title, subtitle, children }) {
  return (
    <motion.main
      className="page"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
    >
      <div className="page-heading">
        <div>
          <p className="eyebrow">MAILPILOT / WORKSPACE</p>
          <h1 data-testid="page-title">{title}</h1>
          <p className="subtitle">{subtitle}</p>
        </div>
      </div>
      {children}
    </motion.main>
  );
}

export function Status({ status }) {
  const value = (status || "DRAFT").toString();
  return (
    <span
      className={`status ${value.toLowerCase()}`}
      data-testid={`status-${value.toLowerCase()}`}
    >
      {value.replaceAll("_", " ")}
    </span>
  );
}
