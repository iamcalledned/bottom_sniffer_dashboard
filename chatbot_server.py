from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
import os
import httpx
import jwt
import json
import redis
import logging
import asyncio
from jwt.algorithms import RSAAlgorithm
import datetime

# Load config
load_dotenv()
COGNITO_DOMAIN = os.getenv("COGNITO_DOMAIN")
COGNITO_APP_CLIENT_ID = os.getenv("COGNITO_APP_CLIENT_ID")
COGNITO_USER_POOL_ID = os.getenv("COGNITO_USER_POOL_ID")
REDIRECT_URI = os.getenv("REDIRECT_URI")

# Redis Setup
redis_client = redis.Redis(host="localhost", port=6379, db=0)

# Logging
logging.basicConfig(level=logging.INFO)

# FastAPI app
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.urandom(24).hex())

@app.get("/login")
async def login(request: Request):
    state = os.urandom(24).hex()
    request.session['state'] = state
    code_challenge = "dummy_challenge"  # You should generate one using PKCE
    request.session['verifier'] = "dummy_verifier"

    cognito_login_url = (
        f"{COGNITO_DOMAIN}/login"
        f"?response_type=code&client_id={COGNITO_APP_CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}&state={state}&code_challenge={code_challenge}"
        f"&code_challenge_method=S256"
    )

    return RedirectResponse(cognito_login_url)


@app.get("/callback")
async def callback(request: Request, code: str = "", state: str = ""):
    stored_state = request.session.get('state')
    verifier = request.session.get('verifier')

    if state != stored_state or not verifier:
        raise HTTPException(status_code=400, detail="Invalid session state or missing verifier")

    token_url = f"{COGNITO_DOMAIN}/oauth2/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "authorization_code",
        "client_id": COGNITO_APP_CLIENT_ID,
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "code_verifier": verifier
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(token_url, headers=headers, data=data)

    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Token exchange failed")

    id_token = resp.json()["id_token"]
    decoded = await validate_token(id_token)

    session_id = os.urandom(24).hex()
    session_data = {
        "email": decoded.get("email", "unknown"),
        "username": decoded.get("cognito:username", "unknown"),
        "session_id": session_id
    }

    request.session["session_id"] = session_id
    redis_client.set(session_id, json.dumps(session_data), ex=3600)

    response = RedirectResponse(url="/chat.html")
    response.set_cookie("session_id", session_id, httponly=True)
    return response


@app.post("/chat")
async def chat(request: Request):
    body = await request.json()
    user_input = body.get("message")
    session_id = request.cookies.get("session_id")

    if not session_id or not redis_client.exists(session_id):
        raise HTTPException(status_code=401, detail="Session not found or expired")

    # TODO: Add real AI/LLM logic here
    reply = f"You said: {user_input}"
    return JSONResponse(content={"response": reply})


@app.get("/get_session_data")
async def get_session_data(request: Request):
    session_id = request.cookies.get("session_id")
    if not session_id:
        raise HTTPException(status_code=401, detail="No session cookie set")

    data = redis_client.get(session_id)
    if not data:
        raise HTTPException(status_code=404, detail="Session not found")

    return JSONResponse(content=json.loads(data))


@app.get("/api/status2")
async def server_status2():
    try:
        # Perform a lightweight check (e.g., return a success message)
        return JSONResponse(content={"status": "ok"}, status_code=200)
    except Exception as e:
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)


# Token Validation
async def validate_token(id_token: str):
    jwks_url = f"https://cognito-idp.us-east-1.amazonaws.com/{COGNITO_USER_POOL_ID}/.well-known/jwks.json"
    async with httpx.AsyncClient() as client:
        resp = await client.get(jwks_url)
    jwks = resp.json()

    headers = jwt.get_unverified_header(id_token)
    kid = headers["kid"]
    key = [k for k in jwks["keys"] if k["kid"] == kid][0]
    pem = RSAAlgorithm.from_jwk(json.dumps(key))

    decoded = jwt.decode(
        id_token,
        pem,
        algorithms=["RS256"],
        audience=COGNITO_APP_CLIENT_ID
    )
    return decoded


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("chatbot_server:app", host="0.0.0.0", port=8010, reload=True)
