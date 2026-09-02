"""
Security audit tests for MailPilot iteration 8: SEC-001..SEC-004 + regression.
Some tests require EMAIL_PROVIDER=resend (SEC-002), others require mock (SEC-003, e2e).
Skip logic reads EMAIL_PROVIDER dynamically from backend .env at test time.
"""
import os
import io
import time
import uuid
import hmac
import json
import hashlib
import pytest
import requests
from pathlib import Path
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
from dotenv import dotenv_values

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://email-workflow-13.preview.emergentagent.com").rstrip("/")
BACKEND_ENV = dotenv_values(Path("/app/backend/.env"))
WEBHOOK_SECRET = BACKEND_ENV.get("RESEND_WEBHOOK_SECRET", "")
JWT_SECRET = BACKEND_ENV.get("JWT_SECRET", "")
EMAIL_PROVIDER = (BACKEND_ENV.get("EMAIL_PROVIDER") or "resend").lower()
MONGO_URL = BACKEND_ENV.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = BACKEND_ENV.get("DB_NAME", "test_database")

API = f"{BASE_URL}/api"


def _rand_email(prefix="user"):
    return f"TEST_{prefix}_{uuid.uuid4().hex[:10]}@example.com"


def _register(email=None):
    email = email or _rand_email()
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "testpass123", "name": "T"})
    assert r.status_code == 200, r.text
    tok = r.json()["token"]
    return email, tok, r.json()["user"]["id"]


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


# --------------------------- SEC-001 -----------------------------------
class TestSEC001WebhookFailClosed:
    def test_no_headers_401(self):
        r = requests.post(f"{API}/webhooks/resend", json={"type": "email.complained", "data": {"to": ["evil@x.com"]}})
        assert r.status_code == 401, r.text

    def test_wrong_secret_401(self):
        r = requests.post(f"{API}/webhooks/resend",
                          headers={"x-webhook-secret": "wrong-secret"},
                          json={"type": "email.complained", "data": {"to": ["evil@x.com"]}})
        assert r.status_code == 401

    def test_malformed_svix_signature_401(self):
        r = requests.post(f"{API}/webhooks/resend",
                          headers={
                              "svix-id": "msg_1",
                              "svix-timestamp": str(int(time.time())),
                              "svix-signature": "v1,not-a-valid-base64-sig",
                          },
                          json={"type": "email.complained", "data": {"to": ["evil@x.com"]}})
        assert r.status_code == 401

    def test_no_suppression_or_recipient_side_effect_after_401(self):
        # verify neither of the emails used above are in db.suppressions and no recipient marked
        async def check():
            c = AsyncIOMotorClient(MONGO_URL)
            db = c[DB_NAME]
            supp = await db.suppressions.find_one({"email": "evil@x.com"})
            c.close()
            return supp
        assert asyncio.run(check()) is None

    def test_correct_shared_secret_processes_complaint(self):
        assert WEBHOOK_SECRET, "RESEND_WEBHOOK_SECRET missing from .env"
        addr = _rand_email("sec001complain").lower()
        payload = {"type": "email.complained", "data": {"to": [addr], "email_id": f"missing_{uuid.uuid4().hex}"}}
        r = requests.post(f"{API}/webhooks/resend",
                          headers={"x-webhook-secret": WEBHOOK_SECRET},
                          json=payload)
        assert r.status_code == 200, r.text

        async def check():
            c = AsyncIOMotorClient(MONGO_URL)
            db = c[DB_NAME]
            supp = await db.suppressions.find_one({"email": addr})
            await db.suppressions.delete_one({"email": addr})
            c.close()
            return supp
        supp = asyncio.run(check())
        assert supp is not None, "complaint webhook should have upserted suppression"
        assert supp["source"] == "complaint"

    def test_correct_shared_secret_updates_recipient_bounced(self):
        # need a recipient to exist with a known provider_message_id; use direct mongo insert
        assert WEBHOOK_SECRET
        provider_id = f"seed_{uuid.uuid4().hex}"
        rid = str(uuid.uuid4())
        email, tok, uid = _register()
        campaign_id = str(uuid.uuid4())

        async def seed():
            c = AsyncIOMotorClient(MONGO_URL)
            db = c[DB_NAME]
            await db.campaigns.insert_one({"id": campaign_id, "user_id": uid, "total_recipients": 1})
            await db.recipients.insert_one({
                "id": rid, "campaign_id": campaign_id, "user_id": uid,
                "email": "target@x.com", "sending_status": "SENT",
                "provider_message_id": provider_id,
            })
            c.close()
        asyncio.run(seed())

        r = requests.post(f"{API}/webhooks/resend",
                          headers={"x-webhook-secret": WEBHOOK_SECRET},
                          json={"type": "email.bounced", "data": {"email_id": provider_id}})
        assert r.status_code == 200

        async def check_and_cleanup():
            c = AsyncIOMotorClient(MONGO_URL)
            db = c[DB_NAME]
            rec = await db.recipients.find_one({"id": rid})
            await db.recipients.delete_many({"campaign_id": campaign_id})
            await db.campaigns.delete_one({"id": campaign_id})
            c.close()
            return rec
        rec = asyncio.run(check_and_cleanup())
        assert rec["sending_status"] == "BOUNCED"


# --------------------------- SEC-002 -----------------------------------
class TestSEC002DomainOwnership:
    @pytest.mark.skipif(EMAIL_PROVIDER != "resend", reason="Requires EMAIL_PROVIDER=resend")
    def test_cross_tenant_domain_isolation(self):
        _, tokA, uidA = _register()
        _, tokB, uidB = _register()
        dom_id = f"dom_A_{uuid.uuid4().hex[:8]}"

        async def insert():
            c = AsyncIOMotorClient(MONGO_URL)
            db = c[DB_NAME]
            await db.owned_domains.insert_one({
                "user_id": uidA, "domain_id": dom_id, "name": "a.example.com", "created_at": "now"
            })
            c.close()
        asyncio.run(insert())

        try:
            # (a) GET list as B does not include dom_A
            r = requests.get(f"{API}/settings/domains", headers=_hdr(tokB))
            assert r.status_code == 200, r.text
            body = r.json()
            listed = [d.get("id") for d in body.get("domains", [])]
            assert dom_id not in listed

            # (b) DELETE as B returns 404 and row remains
            r = requests.delete(f"{API}/settings/domains/{dom_id}", headers=_hdr(tokB))
            assert r.status_code == 404, f"expected 404 got {r.status_code}: {r.text}"

            async def still_present():
                c = AsyncIOMotorClient(MONGO_URL)
                db = c[DB_NAME]
                row = await db.owned_domains.find_one({"user_id": uidA, "domain_id": dom_id})
                c.close()
                return row
            assert asyncio.run(still_present()) is not None

            # (c) GET /dom_A and POST /verify as B → 404
            r = requests.get(f"{API}/settings/domains/{dom_id}", headers=_hdr(tokB))
            assert r.status_code == 404, r.text
            r = requests.post(f"{API}/settings/domains/{dom_id}/verify", headers=_hdr(tokB))
            assert r.status_code == 404, r.text
        finally:
            async def cleanup():
                c = AsyncIOMotorClient(MONGO_URL)
                db = c[DB_NAME]
                await db.owned_domains.delete_many({"domain_id": dom_id})
                c.close()
            asyncio.run(cleanup())


# --------------------------- SEC-003 -----------------------------------
class TestSEC003SuppressionScope:
    @pytest.mark.skipif(EMAIL_PROVIDER != "mock", reason="Requires EMAIL_PROVIDER=mock for send-loop")
    def test_suppression_scoped_per_user(self):
        # Users C, D
        emailC, tokC, uidC = _register()
        emailD, tokD, uidD = _register()

        # C runs a 2-recipient campaign
        def run_campaign(tok, recipients):
            csv_bytes = ("email\n" + "\n".join(recipients)).encode()
            files = {"file": ("r.csv", csv_bytes, "text/csv")}
            data = {"name": "c", "subject": "s", "body": "b"}
            r = requests.post(f"{API}/campaigns", headers=_hdr(tok), files=files, data=data)
            assert r.status_code == 200, r.text
            cid = r.json()["campaign"]["id"]
            # test → confirm → send
            r = requests.post(f"{API}/campaigns/{cid}/test",
                              headers=_hdr(tok),
                              data={"recipient": "tester@example.com"})
            assert r.status_code == 200, r.text
            r = requests.post(f"{API}/campaigns/{cid}/confirm", headers=_hdr(tok))
            assert r.status_code == 200, r.text
            r = requests.post(f"{API}/campaigns/{cid}/send", headers=_hdr(tok))
            assert r.status_code == 200, r.text
            # poll
            for _ in range(30):
                pr = requests.get(f"{API}/campaigns/{cid}/progress", headers=_hdr(tok)).json()
                if pr.get("status") == "COMPLETED":
                    break
                time.sleep(0.5)
            return cid

        _suf = uuid.uuid4().hex[:8]
        foo_email = f"foo_{_suf}@x.com"
        bar_email = f"bar_{_suf}@x.com"
        baz_email = f"baz_{_suf}@x.com"
        c_recips = [foo_email, bar_email]
        d_recips = [baz_email]
        run_campaign(tokC, c_recips)
        run_campaign(tokD, d_recips)

        # get recipient provider_message_ids to build a webhook for foo and baz
        async def get_pid(uid, email):
            c = AsyncIOMotorClient(MONGO_URL)
            db = c[DB_NAME]
            rec = await db.recipients.find_one({"user_id": uid, "email": email})
            c.close()
            return rec

        foo_rec = asyncio.run(get_pid(uidC, foo_email))
        baz_rec = asyncio.run(get_pid(uidD, baz_email))
        assert foo_rec and foo_rec.get("provider_message_id"), "foo recipient not sent"
        assert baz_rec and baz_rec.get("provider_message_id"), "baz recipient not sent"

        # complaint webhook for foo (email.complained will upsert suppression using data.to)
        r = requests.post(f"{API}/webhooks/resend",
                          headers={"x-webhook-secret": WEBHOOK_SECRET},
                          json={"type": "email.complained",
                                "data": {"to": [foo_email], "email_id": foo_rec["provider_message_id"]}})
        assert r.status_code == 200

        # bounce webhook for baz
        r = requests.post(f"{API}/webhooks/resend",
                          headers={"x-webhook-secret": WEBHOOK_SECRET},
                          json={"type": "email.bounced",
                                "data": {"email_id": baz_rec["provider_message_id"]}})
        assert r.status_code == 200

        # (a) suppressions for C only lists foo
        rc = requests.get(f"{API}/suppressions", headers=_hdr(tokC))
        assert rc.status_code == 200
        emails_c = set(rc.json().get("emails", []))
        assert foo_email in emails_c
        assert baz_email not in emails_c
        assert bar_email not in emails_c

        # (b) suppressions for D only lists baz
        rd = requests.get(f"{API}/suppressions", headers=_hdr(tokD))
        assert rd.status_code == 200
        emails_d = set(rd.json().get("emails", []))
        assert baz_email in emails_d
        assert foo_email not in emails_d


# --------------------------- SEC-004 -----------------------------------
class TestSEC004UploadCap:
    def test_reject_1mb_csv_with_413(self):
        _, tok, uid = _register()
        # Build ~1.1MB CSV of fake emails
        buf = io.StringIO()
        buf.write("email\n")
        # each line ~26 bytes -> need ~42k lines for 1.1MB
        i = 0
        while buf.tell() < 1_100_000:
            buf.write(f"user{i:08d}@example.com\n")
            i += 1
        payload = buf.getvalue().encode()
        assert len(payload) > 1_000_000

        files = {"file": ("big.csv", payload, "text/csv")}
        data = {"name": "big", "subject": "s", "body": "b"}
        r = requests.post(f"{API}/campaigns", headers=_hdr(tok), files=files, data=data)
        assert r.status_code == 413, f"expected 413, got {r.status_code}: {r.text[:200]}"

        # verify no campaign was created for this user
        async def check():
            c = AsyncIOMotorClient(MONGO_URL)
            db = c[DB_NAME]
            n = await db.campaigns.count_documents({"user_id": uid})
            c.close()
            return n
        assert asyncio.run(check()) == 0

    def test_accept_small_csv(self):
        _, tok, uid = _register()
        csv_bytes = b"email\na@x.com\nb@x.com\nc@x.com\n"
        files = {"file": ("small.csv", csv_bytes, "text/csv")}
        data = {"name": "small", "subject": "s", "body": "b"}
        r = requests.post(f"{API}/campaigns", headers=_hdr(tok), files=files, data=data)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["campaign"]["valid_count"] == 3


# --------------------------- Regression --------------------------------
class TestRegression:
    @pytest.mark.skipif(EMAIL_PROVIDER != "mock", reason="Needs mock provider")
    def test_full_happy_path(self):
        _, tok, _ = _register()
        csv_bytes = b"email\nalice@x.com\nbob@x.com\n"
        files = {"file": ("r.csv", csv_bytes, "text/csv")}
        data = {"name": "hp", "subject": "s", "body": "b"}
        r = requests.post(f"{API}/campaigns", headers=_hdr(tok), files=files, data=data)
        assert r.status_code == 200
        cid = r.json()["campaign"]["id"]

        r = requests.post(f"{API}/campaigns/{cid}/test", headers=_hdr(tok),
                          data={"recipient": "tester@example.com"})
        assert r.status_code == 200
        r = requests.post(f"{API}/campaigns/{cid}/confirm", headers=_hdr(tok))
        assert r.status_code == 200
        r = requests.post(f"{API}/campaigns/{cid}/send", headers=_hdr(tok))
        assert r.status_code == 200

        for _ in range(40):
            pr = requests.get(f"{API}/campaigns/{cid}/progress", headers=_hdr(tok)).json()
            if pr.get("status") == "COMPLETED":
                assert pr["progress_percentage"] == 100
                return
            time.sleep(0.5)
        pytest.fail("Campaign did not reach COMPLETED in time")

    def test_unsubscribe_bad_token(self):
        r = requests.post(f"{API}/unsubscribe", json={"email": "a@x.com", "token": "bad"})
        assert r.status_code == 400

    def test_unsubscribe_good_token(self):
        email = _rand_email("unsub").lower()
        token = hmac.new(JWT_SECRET.encode(), email.encode(), hashlib.sha256).hexdigest()[:32]
        r = requests.get(f"{API}/unsubscribe/verify", params={"email": email, "t": token})
        assert r.status_code == 200
        r = requests.post(f"{API}/unsubscribe", json={"email": email, "token": token})
        assert r.status_code == 200
        # cleanup
        async def cleanup():
            c = AsyncIOMotorClient(MONGO_URL)
            db = c[DB_NAME]
            await db.suppressions.delete_one({"email": email})
            c.close()
        asyncio.run(cleanup())
