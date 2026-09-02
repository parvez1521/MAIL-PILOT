import axios from "axios";

export const api = axios.create({ baseURL: `${process.env.REACT_APP_BACKEND_URL}/api` });

export const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem("mailpilot_token")}` },
});

export const errorText = (e) => {
  const d = e?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (d && typeof d === "object" && d.message) return d.message;
  return "Something went wrong. Please try again.";
};

export const isValidEmail = (v) =>
  /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test((v || "").trim());
