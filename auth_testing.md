# MailPilot authentication testing

1. Register a new user with `POST /api/auth/register` using an email and password of at least six characters.
2. Login with `POST /api/auth/login` and use the returned bearer token for `GET /api/auth/me`.
3. Verify protected campaign endpoints reject requests without the bearer token.
4. Verify campaign responses only contain the authenticated user's records.