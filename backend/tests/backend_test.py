"""MailPilot Phase 2 backend regression tests.

Some tests are provider-conditional (see markers). Caller controls
EMAIL_PROVIDER in /app/backend/.env.
"""
import os
import uuid
import time
import hmac
import hashlib
import re
import requests
import pytest

def _load_frontend_env():
    p = "/app/frontend/.env"
    if os.path.exists(p):
        with open(p) as fh:
            for line in fh:
                if line.startswith("REACT_APP_BACKEND_URL"):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _load_frontend_env() or "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL not set"

_env = {}
_env_path = "/app/backend/.env"
if os.path.exists(_env_path):
    with open(_env_path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            _env[k.strip()] = v.strip().strip('"').strip("'")
JWT_SECRET = _env.get("JWT_SECRET", "")
EMAIL_PROVIDER = _env.get("EMAIL_PROVIDER", "resend").lower()
WEBHOOK_SECRET = _env.get("RESEND_WEBHOOK_SECRET", "")
WH_HDR = {"x-webhook-secret": WEBHOOK_SECRET}


def unsubscribe_token(email: str) -> str:
    return hmac.new(JWT_SECRET.encode(), email.lower().encode(), hashlib.sha256).hexdigest()[:32]


def register_user():
    email = f"test_{uuid.uuid4().hex}@example.com"
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/register", json={"email": email, "password": "testpass123"}, timeout=30)
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s, email, token


# -------------------- Auth --------------------
def test_register_login_me_and_401():
    s, email, _ = register_user()
    me = s.get(f"{BASE_URL}/api/auth/me", timeout=15)
    assert me.status_code == 200
    assert me.json()["email"] == email

    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "testpass123"}, timeout=15)
    assert r.status_code == 200
    assert r.json()["user"]["email"] == email

    r = requests.get(f"{BASE_URL}/api/campaigns", timeout=15)
    assert r.status_code == 401
    assert "application/json" in r.headers.get("content-type", "")
    assert "detail" in r.json()


# -------------------- Provider error mapping (only when provider=resend) --------------------
@pytest.mark.skipif(EMAIL_PROVIDER != "resend", reason="Provider error mapping only runs with EMAIL_PROVIDER=resend")
def test_provider_error_returns_json_400_not_502():
    s, _, _ = register_user()
    r = s.post(
        f"{BASE_URL}/api/mail/single",
        json={"recipient": "someone@example.com", "subject": "Hi", "body": "Hello"},
        timeout=30,
    )
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:200]}"
    assert "application/json" in r.headers.get("content-type", "")
    assert isinstance(r.json().get("detail"), str)
    assert "<html" not in r.text.lower()


# -------------------- 500 recipient limit --------------------
def test_campaign_rejects_over_500_recipients():
    s, _, _ = register_user()
    rows = ("email\n" + "\n".join(f"user{i}@example.com" for i in range(501))).encode()
    r = s.post(
        f"{BASE_URL}/api/campaigns",
        data={"name": "big", "subject": "S", "body": "B"},
        files={"file": ("big.csv", rows, "text/csv")},
        timeout=30,
    )
    assert r.status_code == 400


# -------------------- Bulk gate --------------------
def test_bulk_send_blocked_until_test_and_confirm():
    s, _, _ = register_user()
    csv = b"email\nx1@example.com\nx2@example.com\n"
    r = s.post(
        f"{BASE_URL}/api/campaigns",
        data={"name": "gate", "subject": "S", "body": "B"},
        files={"file": ("r.csv", csv, "text/csv")},
        timeout=30,
    )
    assert r.status_code == 200
    cid = r.json()["campaign"]["id"]

    r = s.post(f"{BASE_URL}/api/campaigns/{cid}/send", timeout=30)
    assert r.status_code == 400

    r = s.post(f"{BASE_URL}/api/campaigns/{cid}/confirm", timeout=30)
    assert r.status_code == 400


# -------------------- Mock happy path (progress polling + webhook) --------------------
@pytest.mark.skipif(EMAIL_PROVIDER != "mock", reason="Full send loop requires EMAIL_PROVIDER=mock")
def test_full_bulk_happy_path_with_progress_and_webhooks():
    s, _, _ = register_user()
    emails = [f"rcpt{i}_{uuid.uuid4().hex[:6]}@example.com" for i in range(5)]
    csv = ("email\n" + "\n".join(emails)).encode()
    r = s.post(
        f"{BASE_URL}/api/campaigns",
        data={"name": "happy", "subject": "Hello", "body": "Body"},
        files={"file": ("h.csv", csv, "text/csv")},
        timeout=30,
    )
    assert r.status_code == 200
    cid = r.json()["campaign"]["id"]

    r = s.post(f"{BASE_URL}/api/campaigns/{cid}/test", data={"recipient": emails[0]}, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ACCEPTED"

    r = s.post(f"{BASE_URL}/api/campaigns/{cid}/confirm", timeout=30)
    assert r.status_code == 200
    assert r.json()["status"] == "READY_TO_SEND"

    r = s.post(f"{BASE_URL}/api/campaigns/{cid}/send", timeout=30)
    assert r.status_code in (200, 202)
    body = r.json()
    assert body["status"] == "SENDING"
    assert body.get("job_id")

    final = None
    for _ in range(30):
        p = s.get(f"{BASE_URL}/api/campaigns/{cid}/progress", timeout=15).json()
        if p["status"] == "COMPLETED":
            final = p
            break
        time.sleep(1)
    assert final is not None, "campaign did not complete within 30s"
    assert final["sent_count"] == 5
    assert final["progress_percentage"] == 100

    detail = s.get(f"{BASE_URL}/api/campaigns/{cid}", timeout=15).json()
    recs = detail["recipients"]
    assert len(recs) == 5
    pmid_map = {r["email"]: r["provider_message_id"] for r in recs}

    r = requests.post(
        f"{BASE_URL}/api/webhooks/resend",
        headers=WH_HDR, json={"type": "email.delivered", "data": {"email_id": pmid_map[emails[0]]}}, timeout=15,
    )
    assert r.status_code == 200
    r = requests.post(
        f"{BASE_URL}/api/webhooks/resend",
        headers=WH_HDR, json={"type": "email.bounced", "data": {"email_id": pmid_map[emails[1]]}}, timeout=15,
    )
    assert r.status_code == 200
    r = requests.post(
        f"{BASE_URL}/api/webhooks/resend",
        headers=WH_HDR, json={"type": "email.complained", "data": {"email_id": pmid_map[emails[2]], "to": [emails[2]]}}, timeout=15,
    )
    assert r.status_code == 200
    r = requests.post(
        f"{BASE_URL}/api/webhooks/resend",
        headers=WH_HDR, json={"type": "email.failed", "data": {"email_id": pmid_map[emails[3]], "reason": "smtp reject"}}, timeout=15,
    )
    assert r.status_code == 200

    time.sleep(1)
    detail = s.get(f"{BASE_URL}/api/campaigns/{cid}", timeout=15).json()
    status_by_email = {r["email"]: r["sending_status"] for r in detail["recipients"]}
    reason_by_email = {r["email"]: r.get("failure_reason") for r in detail["recipients"]}
    assert status_by_email[emails[0]] == "DELIVERED"
    assert status_by_email[emails[1]] == "BOUNCED"
    assert status_by_email[emails[2]] == "COMPLAINED", f"got {status_by_email[emails[2]]}"
    assert status_by_email[emails[3]] == "FAILED"
    assert reason_by_email[emails[3]] and "smtp" in reason_by_email[emails[3]].lower()

    prog = s.get(f"{BASE_URL}/api/campaigns/{cid}/progress", timeout=15).json()
    assert prog["complained_count"] == 1
    assert prog["bounced_count"] == 1
    assert prog["delivered_count"] == 1
    assert prog["failed_count"] == 1

    # Second campaign — complained email should be auto-cleaned before insertion
    fresh = f"fresh_{uuid.uuid4().hex[:6]}@example.com"
    csv2 = f"email\n{emails[2]}\n{fresh}\n".encode()
    r = s.post(
        f"{BASE_URL}/api/campaigns",
        data={"name": "supp", "subject": "S", "body": "B"},
        files={"file": ("s.csv", csv2, "text/csv")}, timeout=30,
    )
    body2 = r.json()
    assert body2["auto_cleaned_count"] == 1, body2
    assert emails[2] in body2["auto_cleaned_emails"]
    assert body2["campaign"]["valid_count"] == 1


# -------------------- Unsubscribe HMAC flow --------------------
def test_unsubscribe_hmac_flow():
    email = f"unsub_{uuid.uuid4().hex[:8]}@example.com"

    r = requests.get(f"{BASE_URL}/api/unsubscribe/verify", params={"email": email, "t": "BAD"}, timeout=15)
    assert r.status_code == 400

    tok = unsubscribe_token(email)
    r = requests.get(f"{BASE_URL}/api/unsubscribe/verify", params={"email": email, "t": tok}, timeout=15)
    assert r.status_code == 200
    assert r.json()["already_unsubscribed"] is False

    r = requests.post(f"{BASE_URL}/api/unsubscribe", json={"email": email, "token": tok}, timeout=15)
    assert r.status_code == 200

    r = requests.get(f"{BASE_URL}/api/unsubscribe/verify", params={"email": email, "t": tok}, timeout=15)
    assert r.status_code == 200
    assert r.json()["already_unsubscribed"] is True


# -------------------- Security: no API key in frontend bundle --------------------
def test_no_resend_key_in_frontend_bundle():
    r = requests.get(BASE_URL + "/", timeout=20)
    assert r.status_code == 200
    js_paths = re.findall(r'/static/js/[^\s"\'<>]+\.js', r.text)
    checked = 0
    for path in js_paths[:6]:
        js = requests.get(BASE_URL + path, timeout=20).text
        checked += 1
        assert "re_hf2" not in js
        # The literal env-var name may appear as UI copy (DomainSetup notice); only the
        # actual key material (long re_ prefix) must be absent. `re_` used as JS identifier
        # prefix (e.g. re_reason) is not a leak.
        assert not re.search(r"\bre_[A-Za-z0-9]{20,}", js)
    assert checked > 0
