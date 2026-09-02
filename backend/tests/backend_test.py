import os
import uuid
import io
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")


def test_auth_and_protected_flow():
    email = f"test_{uuid.uuid4().hex}@example.com"
    password = "testpass123"
    s = requests.Session()
    registered = s.post(f"{BASE_URL}/api/auth/register", json={"email": email, "password": password, "name": "Regression"})
    assert registered.status_code == 200
    token = registered.json()["token"]
    assert registered.json()["user"]["email"] == email
    assert s.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()["email"] == email
    assert s.get(f"{BASE_URL}/api/campaigns").status_code == 401


def test_mocked_single_and_test_mail():
    email = f"test_{uuid.uuid4().hex}@example.com"
    s = requests.Session()
    token = s.post(f"{BASE_URL}/api/auth/register", json={"email": email, "password": "testpass123"}).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"recipient": "recipient@example.com", "subject": "Hello", "body": "Body"}
    assert s.post(f"{BASE_URL}/api/mail/single", json=payload, headers=headers).json()["status"] == "MOCKED"
    assert s.post(f"{BASE_URL}/api/mail/test", json=payload, headers=headers).json()["status"] == "SENT"


def test_campaign_validation_preview_test_confirm_send():
    email = f"test_{uuid.uuid4().hex}@example.com"
    s = requests.Session()
    token = s.post(f"{BASE_URL}/api/auth/register", json={"email": email, "password": "testpass123"}).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    files = {"file": ("recipients.csv", io.BytesIO(b"email\nA@example.com\na@example.com\nnot-an-email\nB@example.com\n"), "text/csv")}
    data = {"name": "Test campaign", "subject": "Subject", "body": "Message"}
    created = s.post(f"{BASE_URL}/api/campaigns", data=data, files=files, headers=headers)
    assert created.status_code == 200
    campaign = created.json()["campaign"]
    # Campaign CSV validation: duplicates are removed and malformed values count as invalid.
    assert (campaign["valid_count"], campaign["invalid_count"], campaign["recipient_count"]) == (2, 1, 2)
    cid = campaign["id"]
    assert s.post(f"{BASE_URL}/api/campaigns/{cid}/confirm", headers=headers).status_code == 400
    assert s.post(f"{BASE_URL}/api/campaigns/{cid}/test", data={"recipient": "recipient@example.com"}, headers=headers).json()["status"] == "SENT"
    assert s.post(f"{BASE_URL}/api/campaigns/{cid}/confirm", headers=headers).json()["status"] == "READY_TO_SEND"
    assert s.post(f"{BASE_URL}/api/campaigns/{cid}/send", headers=headers).json()["status"] == "COMPLETED"


def test_campaign_rejects_over_limit():
    email = f"test_{uuid.uuid4().hex}@example.com"
    s = requests.Session()
    token = s.post(f"{BASE_URL}/api/auth/register", json={"email": email, "password": "testpass123"}).json()["token"]
    rows = ("\n".join(f"user{i}@example.com" for i in range(501))).encode()
    response = s.post(f"{BASE_URL}/api/campaigns", data={"name": "Too many", "subject": "S", "body": "B"}, files={"file": ("too-many.csv", rows, "text/csv")}, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 400