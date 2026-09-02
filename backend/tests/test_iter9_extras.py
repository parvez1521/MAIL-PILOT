"""Iteration 9 — extra coverage: user isolation, mandatory test gate ordering,
CSV validation (valid/invalid/dupe), and 500-recipient CSV accept-exactly-500.

Runs under EMAIL_PROVIDER=mock (require mock for /test path without a verified sender)."""
import os
import io
import uuid
import time
import requests
import pytest

def _env():
    d = {}
    with open("/app/backend/.env") as fh:
        for l in fh:
            l = l.strip()
            if "=" in l and not l.startswith("#"):
                k, v = l.split("=", 1)
                d[k] = v.strip('"').strip("'")
    return d

ENV = _env()
BASE = "https://email-workflow-13.preview.emergentagent.com"
API = BASE + "/api"
EMAIL_PROVIDER = ENV.get("EMAIL_PROVIDER", "resend").lower()


def _reg():
    e = f"t_{uuid.uuid4().hex[:10]}@example.com"
    r = requests.post(f"{API}/auth/register", json={"email": e, "password": "testpass123"})
    assert r.status_code == 200
    return r.json()["token"]


def _hdr(t):
    return {"Authorization": f"Bearer {t}"}


# ---------- User isolation ----------
def test_cross_tenant_campaign_returns_404_everywhere():
    tokA = _reg()
    tokB = _reg()

    csv = b"email\na1@example.com\na2@example.com\n"
    r = requests.post(f"{API}/campaigns", headers=_hdr(tokA),
                      files={"file": ("a.csv", csv, "text/csv")},
                      data={"name": "iso", "subject": "s", "body": "b"})
    assert r.status_code == 200, r.text
    cid = r.json()["campaign"]["id"]

    # As B, all these endpoints must be 404
    routes_get = [
        f"/campaigns/{cid}",
        f"/campaigns/{cid}/progress",
        f"/campaigns/{cid}/recipients",
        f"/campaigns/{cid}/events",
    ]
    for path in routes_get:
        r = requests.get(f"{API}{path}", headers=_hdr(tokB))
        assert r.status_code == 404, f"GET {path} expected 404, got {r.status_code}"

    routes_post = [
        (f"/campaigns/{cid}/test", {"recipient": "x@example.com"}, "data"),
        (f"/campaigns/{cid}/confirm", {}, "data"),
        (f"/campaigns/{cid}/send", {}, "data"),
    ]
    for path, payload, mode in routes_post:
        kw = {"headers": _hdr(tokB)}
        kw["data"] = payload
        r = requests.post(f"{API}{path}", **kw)
        assert r.status_code == 404, f"POST {path} expected 404, got {r.status_code}: {r.text[:120]}"

    # B's campaign list must not include A's campaign
    r = requests.get(f"{API}/campaigns", headers=_hdr(tokB))
    assert r.status_code == 200
    ids = {c["id"] for c in (r.json().get("campaigns") or r.json())}
    assert cid not in ids


# ---------- Mandatory test gate ----------
@pytest.mark.skipif(EMAIL_PROVIDER != "mock", reason="/test path needs mock provider")
def test_send_requires_test_and_confirm_in_order():
    tok = _reg()
    csv = b"email\ng1@example.com\ng2@example.com\n"
    r = requests.post(f"{API}/campaigns", headers=_hdr(tok),
                      files={"file": ("g.csv", csv, "text/csv")},
                      data={"name": "gate", "subject": "S", "body": "B"})
    cid = r.json()["campaign"]["id"]

    # Send without /test -> 400
    r = requests.post(f"{API}/campaigns/{cid}/send", headers=_hdr(tok))
    assert r.status_code == 400

    # Do /test with valid recipient
    r = requests.post(f"{API}/campaigns/{cid}/test", headers=_hdr(tok),
                      data={"recipient": "tester@example.com"})
    assert r.status_code == 200

    # Send without /confirm -> still 400
    r = requests.post(f"{API}/campaigns/{cid}/send", headers=_hdr(tok))
    assert r.status_code == 400

    # /confirm then /send succeeds
    r = requests.post(f"{API}/campaigns/{cid}/confirm", headers=_hdr(tok))
    assert r.status_code == 200
    r = requests.post(f"{API}/campaigns/{cid}/send", headers=_hdr(tok))
    assert r.status_code in (200, 202)
    body = r.json()
    assert body["status"] == "SENDING"

    # Double-send while SENDING/COMPLETED -> 409
    # try immediately
    r2 = requests.post(f"{API}/campaigns/{cid}/send", headers=_hdr(tok))
    if r2.status_code != 409:
        # if it already completed, retry
        for _ in range(15):
            r2 = requests.post(f"{API}/campaigns/{cid}/send", headers=_hdr(tok))
            if r2.status_code == 409:
                break
            time.sleep(0.5)
    assert r2.status_code == 409, f"expected 409 on double-send, got {r2.status_code}: {r2.text[:120]}"


# ---------- CSV validation: dedupe + invalid counting ----------
def test_csv_validation_valid_invalid_and_dupe_counts():
    tok = _reg()
    # 3 valid, 1 dupe (of the first), 2 invalid ("not-an-email", "@x")
    csv = b"email\na@example.com\nb@example.com\nc@example.com\na@example.com\nnot-an-email\n@x\n"
    r = requests.post(f"{API}/campaigns", headers=_hdr(tok),
                      files={"file": ("v.csv", csv, "text/csv")},
                      data={"name": "val", "subject": "s", "body": "b"})
    assert r.status_code == 200, r.text
    body = r.json()
    c = body["campaign"]
    assert c["valid_count"] == 3, f"expected 3 unique valid, got {c['valid_count']}"
    # invalid_count should be >= 2 (both malformed rows)
    assert c["invalid_count"] >= 2

    # Verify no dupe in recipients collection
    r = requests.get(f"{API}/campaigns/{c['id']}/recipients", headers=_hdr(tok))
    assert r.status_code == 200
    body = r.json()
    recs = body.get("recipients", body if isinstance(body, list) else [])
    emails = [x["email"] for x in recs]
    assert len(emails) == len(set(emails)), "duplicate recipients present"
    assert len(emails) == 3


# ---------- 500 accept-exactly-500 ----------
def test_csv_accepts_exactly_500():
    tok = _reg()
    lines = ["email"] + [f"u{i}_{uuid.uuid4().hex[:4]}@example.com" for i in range(500)]
    csv = ("\n".join(lines) + "\n").encode()
    r = requests.post(f"{API}/campaigns", headers=_hdr(tok),
                      files={"file": ("500.csv", csv, "text/csv")},
                      data={"name": "cap", "subject": "s", "body": "b"})
    assert r.status_code == 200, r.text
    assert r.json()["campaign"]["valid_count"] == 500


# ---------- Sending method: personal_mailbox coming soon ----------
def test_personal_mailbox_returns_coming_soon_400():
    tok = _reg()
    r = requests.put(f"{API}/settings/sending-method",
                     headers={**_hdr(tok), "Content-Type": "application/json"},
                     json={"method": "personal_mailbox"})
    assert r.status_code == 400
    body = r.json()
    detail = (body.get("detail") or "").lower()
    assert "coming" in detail or "soon" in detail


# ---------- Suppression at send time (mock) ----------
@pytest.mark.skipif(EMAIL_PROVIDER != "mock", reason="Requires mock provider send loop")
def test_seeded_suppression_marks_recipient_suppressed():
    from motor.motor_asyncio import AsyncIOMotorClient
    import asyncio

    tok = _reg()
    supp_email = f"supp_{uuid.uuid4().hex[:8]}@x.com"
    ok_email = f"ok_{uuid.uuid4().hex[:8]}@x.com"

    # Seed suppression AFTER campaign creation (else auto-clean removes it before insertion)
    csv = f"email\n{supp_email}\n{ok_email}\n".encode()
    r = requests.post(f"{API}/campaigns", headers=_hdr(tok),
                      files={"file": ("s.csv", csv, "text/csv")},
                      data={"name": "sup", "subject": "s", "body": "b"})
    assert r.status_code == 200
    cid = r.json()["campaign"]["id"]
    assert r.json()["campaign"]["valid_count"] == 2  # both inserted

    # Now seed suppression for supp_email before /send
    async def seed():
        c = AsyncIOMotorClient(ENV["MONGO_URL"])
        db = c[ENV["DB_NAME"]]
        await db.suppressions.update_one(
            {"email": supp_email},
            {"$set": {"email": supp_email, "source": "seeded_test"}},
            upsert=True,
        )
        c.close()
    asyncio.run(seed())

    # test, confirm, send
    r = requests.post(f"{API}/campaigns/{cid}/test", headers=_hdr(tok),
                      data={"recipient": "tester@example.com"})
    assert r.status_code == 200
    r = requests.post(f"{API}/campaigns/{cid}/confirm", headers=_hdr(tok))
    assert r.status_code == 200
    r = requests.post(f"{API}/campaigns/{cid}/send", headers=_hdr(tok))
    assert r.status_code in (200, 202)

    # poll to complete
    for _ in range(30):
        pr = requests.get(f"{API}/campaigns/{cid}/progress", headers=_hdr(tok)).json()
        if pr.get("status") == "COMPLETED":
            break
        time.sleep(0.5)

    r = requests.get(f"{API}/campaigns/{cid}/recipients", headers=_hdr(tok))
    body = r.json()
    recs = body.get("recipients", body if isinstance(body, list) else [])
    status = {x["email"]: x["sending_status"] for x in recs}
    assert status.get(supp_email) == "SUPPRESSED", f"expected SUPPRESSED, got {status.get(supp_email)}"
    assert status.get(ok_email) in ("SENT", "DELIVERED"), f"expected SENT/DELIVERED, got {status.get(ok_email)}"


# ---------- Recipients filter ----------
@pytest.mark.skipif(EMAIL_PROVIDER != "mock", reason="Needs mock send")
def test_recipients_filter_by_status():
    tok = _reg()
    emails = [f"r{i}_{uuid.uuid4().hex[:5]}@example.com" for i in range(3)]
    csv = ("email\n" + "\n".join(emails)).encode()
    r = requests.post(f"{API}/campaigns", headers=_hdr(tok),
                      files={"file": ("f.csv", csv, "text/csv")},
                      data={"name": "fil", "subject": "s", "body": "b"})
    cid = r.json()["campaign"]["id"]
    requests.post(f"{API}/campaigns/{cid}/test", headers=_hdr(tok),
                  data={"recipient": "tester@example.com"})
    requests.post(f"{API}/campaigns/{cid}/confirm", headers=_hdr(tok))
    requests.post(f"{API}/campaigns/{cid}/send", headers=_hdr(tok))
    for _ in range(30):
        pr = requests.get(f"{API}/campaigns/{cid}/progress", headers=_hdr(tok)).json()
        if pr.get("status") == "COMPLETED":
            break
        time.sleep(0.5)

    r = requests.get(f"{API}/campaigns/{cid}/recipients?status=SENT", headers=_hdr(tok))
    assert r.status_code == 200
    body = r.json()
    recs = body.get("recipients", body if isinstance(body, list) else [])
    if recs:
        for rec in recs:
            assert rec["sending_status"] == "SENT"


# ---------- Single mail mock accepted ----------
@pytest.mark.skipif(EMAIL_PROVIDER != "mock", reason="Only test mock behaviour here")
def test_single_mail_mock_returns_mock_pmid():
    tok = _reg()
    r = requests.post(f"{API}/mail/single", headers={**_hdr(tok), "Content-Type": "application/json"},
                      json={"recipient": "someone@example.com", "subject": "Hi", "body": "Hello"})
    assert r.status_code == 200, r.text
    body = r.json()
    pmid = body.get("provider_message_id") or ""
    assert pmid.startswith("mock_"), f"expected mock_ prefix, got {pmid}"
