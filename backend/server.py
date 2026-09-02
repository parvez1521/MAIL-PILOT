from fastapi import FastAPI, APIRouter, HTTPException, Depends, Header, UploadFile, File, Form, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime, timezone, timedelta
from pathlib import Path
from html import escape
from urllib.parse import quote
import asyncio, csv, io, os, re, bcrypt, jwt, uuid, hmac, hashlib, logging
import resend

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
JWT_SECRET = os.environ["JWT_SECRET"]
RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev")
EMAIL_PROVIDER = os.environ.get("EMAIL_PROVIDER", "resend").lower()
WEBHOOK_SECRET = os.environ.get("RESEND_WEBHOOK_SECRET", "")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "").rstrip("/")
LIMIT = 500
logger = logging.getLogger("mailpilot")
logging.basicConfig(level=logging.INFO)

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]
app = FastAPI(title="MailPilot API")
api = APIRouter(prefix="/api")


def now():
    return datetime.now(timezone.utc).isoformat()


def public_user(doc):
    return {"id": str(doc.get("id", "")), "email": doc["email"], "name": doc.get("name", doc["email"].split("@")[0])}


def token_for(user_id):
    return jwt.encode({"sub": user_id, "exp": datetime.now(timezone.utc) + timedelta(days=7)}, JWT_SECRET, algorithm="HS256")


async def current_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Please sign in to continue")
    try:
        payload = jwt.decode(authorization[7:], JWT_SECRET, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Your session has expired")
    user = await db.users.find_one({"id": payload.get("sub")}, {"_id": 0})
    if not user:
        raise HTTPException(401, "User not found")
    return user


class AuthInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: Optional[str] = None


class MailInput(BaseModel):
    recipient: EmailStr
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1)


class UnsubscribeInput(BaseModel):
    email: EmailStr
    token: str


def unsubscribe_token(email: str) -> str:
    return hmac.new(JWT_SECRET.encode(), email.lower().encode(), hashlib.sha256).hexdigest()[:32]


def unsubscribe_link(email: str) -> str:
    base = FRONTEND_URL or ""
    return f"{base}/unsubscribe?email={quote(email)}&t={unsubscribe_token(email)}"


def valid_email(value):
    return bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value))


def html_body(text: str) -> str:
    return f'<div style="font-family:Arial,sans-serif;line-height:1.6;white-space:pre-wrap">{escape(text)}</div>'


def marketing_html(text: str, recipient: str) -> str:
    link = unsubscribe_link(recipient)
    footer = (
        '<hr style="border:none;border-top:1px solid #e2e8f0;margin:28px 0 12px">'
        '<p style="font-size:11px;color:#64748b;font-family:Arial,sans-serif;line-height:1.6">'
        "You are receiving this email because it was sent through MailPilot. "
        f'<a href="{link}" style="color:#2563eb">Unsubscribe</a>.'
        "</p>"
    )
    return html_body(text) + footer


class EmailProviderAdapter:
    name = "base"

    async def send(self, recipient: str, subject: str, html: str, idempotency_key: str, list_unsubscribe: Optional[str] = None) -> dict:
        raise NotImplementedError


class MockEmailProvider(EmailProviderAdapter):
    name = "mock"

    async def send(self, recipient, subject, html, idempotency_key, list_unsubscribe=None):
        return {"provider_id": f"mock_{uuid.uuid4().hex}", "status": "accepted"}


class ResendEmailProvider(EmailProviderAdapter):
    name = "resend"

    def __init__(self):
        if not RESEND_API_KEY:
            raise RuntimeError("RESEND_API_KEY is not configured")
        resend.api_key = RESEND_API_KEY

    async def send(self, recipient, subject, html, idempotency_key, list_unsubscribe=None):
        headers = {"X-MailPilot-Idempotency-Key": idempotency_key}
        if list_unsubscribe:
            headers["List-Unsubscribe"] = f"<{list_unsubscribe}>"
            headers["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
        params = {"from": SENDER_EMAIL, "to": [recipient], "subject": subject, "html": html, "headers": headers}
        result = await asyncio.to_thread(resend.Emails.send, params)
        if not isinstance(result, dict) or not result.get("id"):
            raise RuntimeError("Resend did not return a message id")
        return {"provider_id": result["id"], "status": "accepted"}


def provider() -> EmailProviderAdapter:
    if EMAIL_PROVIDER == "mock":
        return MockEmailProvider()
    return ResendEmailProvider()


def provider_error_message(exc: Exception) -> str:
    text = str(exc)
    lowered = text.lower()
    if "testing email" in lowered or "example.com" in lowered:
        return (
            "Resend blocked this send: example.com and other placeholder domains are not deliverable. "
            "Use a real recipient address for tests."
        )
    if "own email address" in lowered or "you can only send" in lowered or "verify a domain" in lowered:
        return (
            "Resend is in restricted mode: with onboarding@resend.dev you can only send to the account owner's email. "
            "Verify a sender domain at resend.com/domains and set SENDER_EMAIL to send to other recipients."
        )
    if "invalid api key" in lowered or "unauthorized" in lowered or "401" in lowered:
        return "The email provider rejected the request due to an invalid API key. Update RESEND_API_KEY and try again."
    if "rate" in lowered and "limit" in lowered:
        return "The email provider is rate limiting requests. Please wait a moment and try again."
    return "Email provider could not accept this message. Please review the recipient and try again."


@api.post("/auth/register")
async def register(data: AuthInput):
    email = str(data.email).lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(409, "An account with this email already exists")
    user = {
        "id": str(uuid.uuid4()),
        "email": email,
        "name": data.name or email.split("@")[0],
        "password_hash": bcrypt.hashpw(data.password.encode(), bcrypt.gensalt()).decode(),
        "created_at": now(),
    }
    await db.users.insert_one(user)
    return {"user": public_user(user), "token": token_for(user["id"])}


@api.post("/auth/login")
async def login(data: AuthInput):
    user = await db.users.find_one({"email": str(data.email).lower()}, {"_id": 0})
    if not user or not bcrypt.checkpw(data.password.encode(), user["password_hash"].encode()):
        raise HTTPException(401, "Email or password is incorrect")
    return {"user": public_user(user), "token": token_for(user["id"])}


@api.get("/auth/me")
async def me(user=Depends(current_user)):
    return public_user(user)


async def send_transactional(recipient, subject, body, kind, campaign_id=None, recipient_id=None):
    adapter = provider()
    key = f"{kind}:{campaign_id or uuid.uuid4()}:{recipient_id or recipient}"
    return await adapter.send(recipient, subject, html_body(body), key)


async def send_marketing(recipient, subject, body, kind, campaign_id=None, recipient_id=None):
    adapter = provider()
    key = f"{kind}:{campaign_id or uuid.uuid4()}:{recipient_id or recipient}"
    return await adapter.send(recipient, subject, marketing_html(body, recipient), key, list_unsubscribe=unsubscribe_link(recipient))


@api.post("/mail/single")
async def single_mail(data: MailInput, user=Depends(current_user)):
    try:
        result = await send_transactional(str(data.recipient), data.subject, data.body, "single")
    except Exception as exc:
        logger.warning("single-send failure: %s: %s", type(exc).__name__, str(exc)[:200])
        raise HTTPException(400, provider_error_message(exc))
    record = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "recipient": str(data.recipient),
        "subject": data.subject,
        "body": data.body,
        "status": "ACCEPTED",
        "provider_message_id": result["provider_id"],
        "created_at": now(),
    }
    await db.sending_jobs.insert_one(record)
    return {"message": "Single email submitted", "status": "ACCEPTED", "provider_message_id": result["provider_id"]}


@api.post("/mail/test")
async def test_mail(data: MailInput, user=Depends(current_user)):
    try:
        result = await send_transactional(str(data.recipient), data.subject, data.body, "test")
    except Exception as exc:
        logger.warning("test-send failure: %s: %s", type(exc).__name__, str(exc)[:200])
        raise HTTPException(400, provider_error_message(exc))
    sent = now()
    await db.test_emails.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "recipient": str(data.recipient),
        "subject": data.subject,
        "body": data.body,
        "status": "ACCEPTED",
        "provider_message_id": result["provider_id"],
        "sent_at": sent,
    })
    return {"message": "Test email submitted successfully", "status": "ACCEPTED", "provider_message_id": result["provider_id"]}


def parse_recipients(raw: bytes):
    rows = csv.reader(io.StringIO(raw.decode("utf-8-sig")))
    emails, invalid = [], []
    for row in rows:
        for value in row:
            email = value.strip().lower()
            if not email or email in {"email", "email address", "e-mail"}:
                continue
            if valid_email(email):
                emails.append(email)
            else:
                invalid.append(email)
    return list(dict.fromkeys(emails)), invalid


@api.post("/campaigns")
async def create_campaign(
    name: str = Form(...),
    subject: str = Form(...),
    body: str = Form(...),
    file: UploadFile = File(...),
    user=Depends(current_user),
):
    valid, invalid = parse_recipients(await file.read())
    if len(valid) > LIMIT:
        raise HTTPException(400, f"Campaigns are limited to {LIMIT} valid recipients")
    cid = str(uuid.uuid4())
    ts = now()
    campaign = {
        "id": cid,
        "user_id": user["id"],
        "name": name,
        "subject": subject,
        "body": body,
        "recipient_count": len(valid),
        "total_recipients": len(valid),
        "valid_count": len(valid),
        "invalid_count": len(invalid),
        "queued_count": 0,
        "sending_count": 0,
        "sent_count": 0,
        "delivered_count": 0,
        "bounced_count": 0,
        "complained_count": 0,
        "failed_count": 0,
        "suppressed_count": 0,
        "progress_percentage": 0,
        "test_status": "PENDING",
        "test_sent_at": None,
        "bulk_confirmed": False,
        "status": "RECIPIENTS_VALIDATED",
        "created_at": ts,
        "updated_at": ts,
    }
    await db.campaigns.insert_one(campaign)
    if valid:
        await db.recipients.insert_many([
            {
                "id": str(uuid.uuid4()),
                "campaign_id": cid,
                "user_id": user["id"],
                "email": e,
                "sending_status": "QUEUED",
                "provider_message_id": None,
                "sent_at": None,
                "delivered_at": None,
                "bounced_at": None,
                "failure_reason": None,
                "retry_count": 0,
            }
            for e in valid
        ])
    return {"campaign": {k: v for k, v in campaign.items() if k != "_id"}, "invalid_emails": invalid}


@api.get("/campaigns")
async def campaigns(user=Depends(current_user)):
    return await db.campaigns.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(50)


@api.post("/campaigns/{campaign_id}/test")
async def campaign_test(campaign_id: str, recipient: EmailStr = Form(...), user=Depends(current_user)):
    campaign = await db.campaigns.find_one({"id": campaign_id, "user_id": user["id"]}, {"_id": 0})
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    try:
        adapter = provider()
        key = f"campaign_test:{campaign_id}:{recipient}"
        result = await adapter.send(
            str(recipient),
            campaign["subject"],
            marketing_html(campaign["body"], str(recipient)),
            key,
            list_unsubscribe=unsubscribe_link(str(recipient)),
        )
    except Exception as exc:
        logger.warning("campaign-test failure: %s: %s", type(exc).__name__, str(exc)[:200])
        raise HTTPException(400, provider_error_message(exc))
    sent = now()
    await db.test_emails.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "campaign_id": campaign_id,
        "recipient": str(recipient),
        "status": "ACCEPTED",
        "provider_message_id": result["provider_id"],
        "sent_at": sent,
    })
    await db.campaigns.update_one(
        {"id": campaign_id},
        {"$set": {"test_status": "SENT", "test_sent_at": sent, "status": "TEST_SENT", "updated_at": sent}},
    )
    return {"message": "Test email submitted successfully", "status": "ACCEPTED", "provider_message_id": result["provider_id"]}


@api.post("/campaigns/{campaign_id}/confirm")
async def confirm_campaign(campaign_id: str, user=Depends(current_user)):
    result = await db.campaigns.update_one(
        {"id": campaign_id, "user_id": user["id"], "test_status": "SENT", "bulk_confirmed": False},
        {"$set": {"bulk_confirmed": True, "status": "READY_TO_SEND", "updated_at": now()}},
    )
    if not result.modified_count:
        raise HTTPException(400, "Send a test email before confirming")
    return {"message": "Campaign is ready to send", "status": "READY_TO_SEND"}


async def refresh_counts(campaign_id: str):
    campaign = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
    if not campaign:
        return
    total = campaign.get("total_recipients", 0) or 0
    counts = await db.recipients.aggregate([
        {"$match": {"campaign_id": campaign_id}},
        {"$group": {"_id": "$sending_status", "count": {"$sum": 1}}},
    ]).to_list(20)
    summary = {x["_id"]: x["count"] for x in counts}
    processed = total - summary.get("QUEUED", 0) - summary.get("SENDING", 0)
    pct = round((processed / total) * 100, 2) if total else 100
    await db.campaigns.update_one(
        {"id": campaign_id},
        {"$set": {
            "queued_count": summary.get("QUEUED", 0),
            "sending_count": summary.get("SENDING", 0),
            "sent_count": summary.get("SENT", 0),
            "delivered_count": summary.get("DELIVERED", 0),
            "bounced_count": summary.get("BOUNCED", 0),
            "complained_count": summary.get("COMPLAINED", 0),
            "failed_count": summary.get("FAILED", 0),
            "suppressed_count": summary.get("SUPPRESSED", 0),
            "progress_percentage": pct,
            "updated_at": now(),
        }},
    )


async def process_job(job_id: str):
    job = await db.sending_jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        return
    campaign = await db.campaigns.find_one({"id": job["campaign_id"], "user_id": job["user_id"]}, {"_id": 0})
    if not campaign:
        return
    await db.campaigns.update_one({"id": job["campaign_id"]}, {"$set": {"status": "SENDING", "updated_at": now()}})
    recipients = await db.recipients.find(
        {"campaign_id": job["campaign_id"], "sending_status": "QUEUED"}, {"_id": 0}
    ).to_list(LIMIT)
    adapter = provider()
    for rec in recipients:
        if await db.suppressions.find_one({"email": rec["email"]}):
            await db.recipients.update_one(
                {"id": rec["id"], "sending_status": "QUEUED"},
                {"$set": {"sending_status": "SUPPRESSED"}},
            )
            await refresh_counts(job["campaign_id"])
            continue
        success, reason = False, ""
        for attempt in range(3):
            try:
                await db.recipients.update_one(
                    {"id": rec["id"], "sending_status": "QUEUED"},
                    {"$set": {"sending_status": "SENDING"}, "$inc": {"retry_count": 1}},
                )
                key = f"campaign:{job['campaign_id']}:{rec['id']}"
                result = await adapter.send(
                    rec["email"],
                    campaign["subject"],
                    marketing_html(campaign["body"], rec["email"]),
                    key,
                    list_unsubscribe=unsubscribe_link(rec["email"]),
                )
                await db.recipients.update_one(
                    {"id": rec["id"]},
                    {"$set": {"sending_status": "SENT", "provider_message_id": result["provider_id"], "sent_at": now()}},
                )
                success = True
                break
            except Exception as exc:
                reason = provider_error_message(exc)
                logger.warning("send retry %s failure: %s", attempt, str(exc)[:200])
                await asyncio.sleep(1 * (attempt + 1))
        if not success:
            await db.recipients.update_one(
                {"id": rec["id"]},
                {"$set": {"sending_status": "FAILED", "failure_reason": reason}},
            )
        await refresh_counts(job["campaign_id"])
        await asyncio.sleep(0.25)
    await db.sending_jobs.update_one({"id": job["id"]}, {"$set": {"status": "COMPLETED", "completed_at": now()}})
    await db.campaigns.update_one({"id": job["campaign_id"]}, {"$set": {"status": "COMPLETED", "updated_at": now()}})


@api.post("/campaigns/{campaign_id}/send")
async def send_campaign(campaign_id: str, background_tasks: BackgroundTasks, user=Depends(current_user)):
    campaign = await db.campaigns.find_one(
        {"id": campaign_id, "user_id": user["id"], "bulk_confirmed": True, "test_status": "SENT"}, {"_id": 0}
    )
    if not campaign:
        raise HTTPException(400, "Confirm the test email before sending")
    if campaign["total_recipients"] > LIMIT:
        raise HTTPException(400, "Campaign exceeds the recipient limit")
    if campaign["status"] in {"SENDING", "COMPLETED"}:
        raise HTTPException(409, "This campaign has already been submitted")
    campaign_emails = await db.recipients.distinct("email", {"campaign_id": campaign_id})
    suppressed = await db.suppressions.find({"email": {"$in": campaign_emails}}, {"_id": 0}).to_list(LIMIT)
    suppressed_emails = {x["email"] for x in suppressed}
    if suppressed_emails:
        await db.recipients.update_many(
            {"campaign_id": campaign_id, "email": {"$in": list(suppressed_emails)}, "sending_status": "QUEUED"},
            {"$set": {"sending_status": "SUPPRESSED"}},
        )
    job = {"id": str(uuid.uuid4()), "campaign_id": campaign_id, "user_id": user["id"], "status": "QUEUED", "created_at": now()}
    await db.sending_jobs.insert_one(job)
    await db.campaigns.update_one(
        {"id": campaign_id},
        {"$set": {
            "status": "SENDING",
            "queued_count": campaign["total_recipients"] - len(suppressed_emails),
            "suppressed_count": len(suppressed_emails),
            "updated_at": now(),
        }},
    )
    background_tasks.add_task(process_job, job["id"])
    return {"message": "Campaign queued for delivery", "status": "SENDING", "job_id": job["id"]}


@api.get("/campaigns/{campaign_id}")
async def campaign_detail(campaign_id: str, user=Depends(current_user)):
    campaign = await db.campaigns.find_one({"id": campaign_id, "user_id": user["id"]}, {"_id": 0})
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    campaign["recipients"] = await db.recipients.find(
        {"campaign_id": campaign_id, "user_id": user["id"]}, {"_id": 0}
    ).to_list(LIMIT)
    return campaign


@api.get("/campaigns/{campaign_id}/progress")
async def campaign_progress(campaign_id: str, user=Depends(current_user)):
    campaign = await db.campaigns.find_one({"id": campaign_id, "user_id": user["id"]}, {"_id": 0})
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    return {
        "id": campaign["id"],
        "status": campaign["status"],
        "total_recipients": campaign.get("total_recipients", 0),
        "queued_count": campaign.get("queued_count", 0),
        "sending_count": campaign.get("sending_count", 0),
        "sent_count": campaign.get("sent_count", 0),
        "delivered_count": campaign.get("delivered_count", 0),
        "bounced_count": campaign.get("bounced_count", 0),
        "complained_count": campaign.get("complained_count", 0),
        "failed_count": campaign.get("failed_count", 0),
        "suppressed_count": campaign.get("suppressed_count", 0),
        "progress_percentage": campaign.get("progress_percentage", 0),
        "updated_at": campaign.get("updated_at"),
    }


@api.get("/unsubscribe/verify")
async def unsubscribe_verify(email: EmailStr, t: str):
    address = str(email).lower()
    expected = unsubscribe_token(address)
    if not hmac.compare_digest(expected, t):
        raise HTTPException(400, "This unsubscribe link is invalid or has expired.")
    existing = await db.suppressions.find_one({"email": address})
    return {"email": address, "already_unsubscribed": bool(existing)}


@api.post("/unsubscribe")
async def unsubscribe(data: UnsubscribeInput):
    address = str(data.email).lower()
    expected = unsubscribe_token(address)
    if not hmac.compare_digest(expected, data.token):
        raise HTTPException(400, "This unsubscribe link is invalid or has expired.")
    await db.suppressions.update_one(
        {"email": address},
        {"$set": {"email": address, "created_at": now(), "source": "unsubscribe"}},
        upsert=True,
    )
    return {"message": "You have been unsubscribed", "email": address}


@api.post("/webhooks/resend")
async def resend_webhook(request: Request):
    body = await request.body()
    supplied = request.headers.get("x-webhook-secret", "")
    if WEBHOOK_SECRET and not hmac.compare_digest(supplied, WEBHOOK_SECRET):
        raise HTTPException(401, "Invalid webhook signature")
    try:
        event = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid webhook payload")
    event_type = event.get("type", "")
    data = event.get("data", {}) or {}
    provider_id = data.get("email_id") or data.get("id")
    if provider_id:
        updates = {"provider_event": event_type}
        if event_type == "email.sent":
            updates["sending_status"] = "SENT"
        elif event_type == "email.delivered":
            updates["sending_status"] = "DELIVERED"
            updates["delivered_at"] = now()
        elif event_type == "email.bounced":
            updates["sending_status"] = "BOUNCED"
            updates["bounced_at"] = now()
            updates["failure_reason"] = "provider reported bounce"
        elif event_type == "email.complained":
            updates["sending_status"] = "COMPLAINED"
            updates["failure_reason"] = "recipient marked as spam"
            if data.get("to"):
                addr = (data["to"][0] if isinstance(data["to"], list) else data["to"]).lower()
                await db.suppressions.update_one(
                    {"email": addr},
                    {"$set": {"email": addr, "created_at": now(), "source": "complaint"}},
                    upsert=True,
                )
        elif event_type == "email.failed":
            updates["sending_status"] = "FAILED"
            updates["failure_reason"] = str(data.get("reason", "provider failure"))[:240]
        recipient = await db.recipients.find_one_and_update(
            {"provider_message_id": provider_id}, {"$set": updates}
        )
        if recipient and recipient.get("campaign_id"):
            await refresh_counts(recipient["campaign_id"])
    return {"received": True}


@api.get("/usage")
async def usage(user=Depends(current_user)):
    latest = await db.campaigns.find_one({"user_id": user["id"]}, {"_id": 0}, sort=[("created_at", -1)])
    return {"limit": LIMIT, "used": latest.get("recipient_count", 0) if latest else 0}


app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=False,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.recipients.create_index([("campaign_id", 1), ("email", 1)], unique=True)
    await db.recipients.create_index("provider_message_id", sparse=True)
    await db.suppressions.create_index("email", unique=True)


@app.on_event("shutdown")
async def shutdown():
    client.close()
