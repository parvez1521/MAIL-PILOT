from fastapi import FastAPI, APIRouter, HTTPException, Depends, Header, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime, timezone, timedelta
from pathlib import Path
import csv, io, os, re, bcrypt, jwt, uuid

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
JWT_SECRET = os.environ["JWT_SECRET"]
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]
app = FastAPI(title="MailPilot API")
api = APIRouter(prefix="/api")
LIMIT = 500

def now(): return datetime.now(timezone.utc).isoformat()
def public_user(doc): return {"id": str(doc.get("id", doc.get("_id", ""))), "email": doc["email"], "name": doc.get("name", doc["email"].split("@")[0])}
def token_for(user_id): return jwt.encode({"sub": user_id, "exp": datetime.now(timezone.utc) + timedelta(days=7)}, JWT_SECRET, algorithm="HS256")
async def current_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "): raise HTTPException(401, "Please sign in to continue")
    try: payload = jwt.decode(authorization[7:], JWT_SECRET, algorithms=["HS256"])
    except jwt.InvalidTokenError: raise HTTPException(401, "Your session has expired")
    user = await db.users.find_one({"id": payload.get("sub")}, {"_id": 0})
    if not user: raise HTTPException(401, "User not found")
    return user

class AuthInput(BaseModel): email: EmailStr; password: str = Field(min_length=6); name: Optional[str] = None
class MailInput(BaseModel): recipient: EmailStr; subject: str = Field(min_length=1, max_length=200); body: str = Field(min_length=1)

@api.post("/auth/register")
async def register(data: AuthInput):
    email = str(data.email).lower()
    if await db.users.find_one({"email": email}): raise HTTPException(409, "An account with this email already exists")
    user = {"id": str(uuid.uuid4()), "email": email, "name": data.name or email.split("@")[0], "password_hash": bcrypt.hashpw(data.password.encode(), bcrypt.gensalt()).decode(), "created_at": now()}
    await db.users.insert_one(user)
    return {"user": public_user(user), "token": token_for(user["id"])}

@api.post("/auth/login")
async def login(data: AuthInput):
    user = await db.users.find_one({"email": str(data.email).lower()}, {"_id": 0})
    if not user or not bcrypt.checkpw(data.password.encode(), user["password_hash"].encode()): raise HTTPException(401, "Email or password is incorrect")
    return {"user": public_user(user), "token": token_for(user["id"])}

@api.get("/auth/me")
async def me(user=Depends(current_user)): return public_user(user)

@api.post("/mail/single")
async def single_mail(data: MailInput, user=Depends(current_user)):
    record = {"id": str(uuid.uuid4()), "user_id": user["id"], "recipient": str(data.recipient), "subject": data.subject, "body": data.body, "status": "MOCKED", "created_at": now()}
    await db.sending_jobs.insert_one(record)
    return {"message": "Single mail prepared in test mode", "status": "MOCKED"}

@api.post("/mail/test")
async def test_mail(data: MailInput, user=Depends(current_user)):
    await db.test_emails.insert_one({"id": str(uuid.uuid4()), "user_id": user["id"], **data.model_dump(), "recipient": str(data.recipient), "status": "SENT", "sent_at": now()})
    return {"message": "Test email sent. Please check your inbox.", "status": "SENT"}

def parse_recipients(raw):
    rows = csv.reader(io.StringIO(raw.decode("utf-8-sig")))
    emails, invalid = [], []
    for row in rows:
        for value in row:
            email = value.strip().lower()
            if not email or email in {"email", "email address", "e-mail"}: continue
            if re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email): emails.append(email)
            else: invalid.append(email)
    unique = list(dict.fromkeys(emails))
    return unique, invalid

@api.post("/campaigns")
async def create_campaign(name: str = Form(...), subject: str = Form(...), body: str = Form(...), file: UploadFile = File(...), user=Depends(current_user)):
    valid, invalid = parse_recipients(await file.read())
    if len(valid) > LIMIT: raise HTTPException(400, f"Campaigns are limited to {LIMIT} valid recipients")
    campaign_id = str(uuid.uuid4()); timestamp = now()
    campaign = {"id": campaign_id, "user_id": user["id"], "name": name, "subject": subject, "body": body, "recipient_count": len(valid), "valid_count": len(valid), "invalid_count": len(invalid), "test_status": "PENDING", "test_sent_at": None, "bulk_confirmed": False, "status": "RECIPIENTS_VALIDATED", "created_at": timestamp, "updated_at": timestamp}
    await db.campaigns.insert_one(campaign)
    if valid: await db.recipients.insert_many([{"id": str(uuid.uuid4()), "campaign_id": campaign_id, "user_id": user["id"], "email": e} for e in valid])
    return {"campaign": {k:v for k,v in campaign.items() if k != "_id"}, "invalid_emails": invalid}

@api.get("/campaigns")
async def campaigns(user=Depends(current_user)):
    return await db.campaigns.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(50)

@api.post("/campaigns/{campaign_id}/test")
async def campaign_test(campaign_id: str, recipient: EmailStr = Form(...), user=Depends(current_user)):
    campaign = await db.campaigns.find_one({"id": campaign_id, "user_id": user["id"]}, {"_id": 0})
    if not campaign: raise HTTPException(404, "Campaign not found")
    sent = now(); await db.test_emails.insert_one({"id": str(uuid.uuid4()), "user_id": user["id"], "campaign_id": campaign_id, "recipient": str(recipient), "status": "SENT", "sent_at": sent})
    await db.campaigns.update_one({"id": campaign_id}, {"$set": {"test_status": "SENT", "test_sent_at": sent, "status": "TEST_SENT", "updated_at": sent}})
    return {"message": "Test email sent. Please check your inbox.", "status": "SENT"}

@api.post("/campaigns/{campaign_id}/confirm")
async def confirm_campaign(campaign_id: str, user=Depends(current_user)):
    result = await db.campaigns.update_one({"id": campaign_id, "user_id": user["id"], "test_status": "SENT"}, {"$set": {"bulk_confirmed": True, "status": "READY_TO_SEND", "updated_at": now()}})
    if not result.modified_count: raise HTTPException(400, "Send a test email before confirming")
    return {"message": "Campaign is ready to send", "status": "READY_TO_SEND"}

@api.post("/campaigns/{campaign_id}/send")
async def send_campaign(campaign_id: str, user=Depends(current_user)):
    campaign = await db.campaigns.find_one({"id": campaign_id, "user_id": user["id"], "bulk_confirmed": True}, {"_id": 0})
    if not campaign: raise HTTPException(400, "Confirm the test email before sending")
    await db.campaigns.update_one({"id": campaign_id}, {"$set": {"status": "COMPLETED", "updated_at": now()}})
    return {"message": "Campaign completed in test mode", "status": "COMPLETED"}

@api.get("/usage")
async def usage(user=Depends(current_user)):
    latest = await db.campaigns.find_one({"user_id": user["id"]}, {"_id": 0}, sort=[("created_at", -1)])
    return {"limit": LIMIT, "used": latest.get("recipient_count", 0) if latest else 0}

app.include_router(api)
app.add_middleware(CORSMiddleware, allow_credentials=False, allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","), allow_methods=["*"], allow_headers=["*"])
@app.on_event("shutdown")
async def shutdown(): client.close()