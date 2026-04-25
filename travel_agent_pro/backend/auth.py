import os
import httpx
import logging
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv

# Use absolute path to .env (same pattern as agent.py)
_base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_env_path = os.path.join(_base_dir, ".env")
load_dotenv(_env_path)

logger = logging.getLogger(__name__)
router = APIRouter()

CLIENT_ID = os.getenv("NOTION_CLIENT_ID")
CLIENT_SECRET = os.getenv("NOTION_CLIENT_SECRET")
REDIRECT_URI = os.getenv("NOTION_REDIRECT_URI", "http://localhost:8000/callback")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8501")

@router.get("/login")
async def login():
    """Redirects the user to Notion for authorization."""
    if not CLIENT_ID:
        raise HTTPException(status_code=500, detail="NOTION_CLIENT_ID not configured")
        
    auth_url = (
        f"https://api.notion.com/v1/oauth/authorize?"
        f"client_id={CLIENT_ID}&"
        f"response_type=code&"
        f"owner=user&"
        f"redirect_uri={REDIRECT_URI}"
    )
    return RedirectResponse(auth_url)

@router.get("/callback")
async def callback(code: str):
    """Exchanges the authorization code for an access token."""
    if not CLIENT_ID or not CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="OAuth credentials not configured")

    token_url = "https://api.notion.com/v1/oauth/token"
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            token_url,
            auth=(CLIENT_ID, CLIENT_SECRET),
            json={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI
            }
        )
        
    if response.status_code != 200:
        logger.error(f"Token Error: {response.text}")
        raise HTTPException(status_code=400, detail="Failed to retrieve access token from Notion")
        
    data = response.json()
    access_token = data.get("access_token")
    
    # In a production app, you would store this in a database and associate it with a user session.
    # For this version, we'll redirect back to the frontend with the token as a query parameter.
    # streamlit can then pick it up and store it in session_state.
    
    return RedirectResponse(f"{FRONTEND_URL}/?token={access_token}")
