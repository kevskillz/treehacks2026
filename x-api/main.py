import os
import hmac
import hashlib
import base64
import threading
import time
from flask import Flask, request, redirect, jsonify
from xdk import Client
from xdk.oauth2_auth import OAuth2PKCEAuth
from supabase import create_client, Client as SupabaseClient
from datetime import datetime, timezone
import requests
from requests_oauthlib import OAuth1
import uuid

from dotenv import load_dotenv
load_dotenv()


# XAI Config
XAI_API_KEY = os.getenv("XAI_API_KEY")
XAI_URL = "https://api.x.ai/v1/chat/completions"

def generate_grok_response(system_content, user_content):
    """Helper to generate text using Grok"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {XAI_API_KEY}",
    }
    
    data = {
        "model": "grok-4-1-fast", 
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content}
        ],
        "max_tokens": 100,
        "temperature": 0.5, # Balance creativity/speed
        "stream": False
    }
    
    try:
        resp = requests.post(XAI_URL, headers=headers, json=data, timeout=5)
        resp.raise_for_status()
        result = resp.json()
        return result['choices'][0]['message']['content'].strip()
    except Exception as e:
        print(f"   ⚠️ Grok generation failed: {e}")
        return None

app = Flask(__name__)

# Supabase Config
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

try:
    supabase: SupabaseClient = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"Error initializing Supabase client: {e}")
    supabase = None

# Configuration
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

# API Key and Secret (Consumer Key/Secret) - REQUIRED for Webhooks & OAuth 1.0a
# Find this in Developer Portal -> "Keys and tokens" -> "API Key and Secret"
CONSUMER_KEY = os.getenv("CONSUMER_KEY")
CONSUMER_SECRET = os.getenv("CONSUMER_SECRET")

# Access Token & Secret (OAuth 1.0a user token) - REQUIRED for subscription
# Find this in Developer Portal -> "Keys and tokens" -> "Access Token and Secret"
ACCESS_TOKEN_SECRET = os.getenv("ACCESS_TOKEN_SECRET")

# Webhook environment name (from Developer Portal -> Account Activity API)
WEBHOOK_ENV = os.getenv("WEBHOOK_ENV", "dev")

# Ensure this matches your X App settings exactly
REDIRECT_URI = "http://127.0.0.1:8080/callback"
SCOPES = ["tweet.read", "tweet.write", "users.read", "offline.access", "dm.read", "dm.write"]

# Demo Mode Configuration
# Paste your token here if you want to skip the auth step during the demo
## IMPORTANT AS FUCK
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")

# Global storage for auth instance (required for PKCE)
auth_store = {}

# Polling state
polling_thread = None
polling_active = False
last_seen_id = None

@app.route("/post-tweet")
def post_tweet():
    """Start the OAuth flow for tweeting"""
    auth = OAuth2PKCEAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope=SCOPES
    )
    # Store auth instance to preserve PKCE verifier
    auth_store['current'] = auth
    auth_store['action'] = 'tweet'
    print(auth_store)
    return redirect(auth.get_authorization_url())

@app.route("/send-dm")
def send_dm():
    """Start the OAuth flow for sending a DM"""
    auth = OAuth2PKCEAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope=SCOPES
    )
    auth_store['current'] = auth
    auth_store['action'] = 'dm'
    return redirect(auth.get_authorization_url())

@app.route("/callback/")
def callback():
    """Handle X callback, get token, and perform action"""
    auth = auth_store.get('current')
    action = auth_store.get('action')
    
    if not auth:
        return jsonify({"error": "No auth flow found. Visit /start-auth, /post-tweet, or /send-dm first."}), 400

    try:
        # Exchange code for access token
        tokens = auth.fetch_token(authorization_response=request.url)
        # Store tokens globally so the webhook can use them later
        auth_store['tokens'] = tokens

        # DEBUG: Print full token response to diagnose 403 issues
        print("\n" + "="*50)
        print("FULL TOKEN RESPONSE:")
        for k, v in tokens.items():
            if k == 'access_token':
                print(f"  {k}: {v[:20]}...{v[-10:]}")
            else:
                print(f"  {k}: {v}")
        print("="*50 + "\n")

        access_token = tokens["access_token"]

        if action == 'tweet':
            tweet_text = "Been working on aggregating stuff for y'all at https://free-stuff-eta.vercel.app/ - so many free resources for builders!"

            # Use requests directly with user-context OAuth2 token
            resp = requests.post(
                "https://api.x.com/2/tweets",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={"text": tweet_text},
            )
            print(f"Tweet API response: {resp.status_code} {resp.text}")

            if resp.status_code in (200, 201):
                return jsonify({
                    "status": "Tweet posted successfully",
                    "data": resp.json()
                })
            else:
                return jsonify({
                    "error": f"Tweet API returned {resp.status_code}",
                    "details": resp.json()
                }), resp.status_code
            
        elif action == 'dm':
            participant_id = "1944199676497981440"
            text_message = "Appreciate the ping about dark mode on FreeSauce! Working on implementing it soon."

            dm_client = Client(access_token=access_token)
            response = dm_client.direct_messages.create_by_participant_id(participant_id, body={"text": text_message})

            return jsonify({
                "status": "DM sent successfully",
                "data": response.data
            })

        return jsonify({"error": f"Unknown action: {action}"}), 400

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/webhooks', methods=['GET', 'POST'])
def webhook_request():
    # Handle GET request (CRC challenge)
    if request.method == 'GET':
        crc_token = request.args.get('crc_token')
        print(f"CRC Token rece  ived: {crc_token}")
        if crc_token is None:
            print("Error: No crc_token found in the request.")
            return jsonify({'error': 'No crc_token'}), 400

        # Creates HMAC SHA-256 hash from incoming token and your consumer secret
        sha256_hash_digest = hmac.new(
            CONSUMER_SECRET.encode('utf-8'),
            msg=crc_token.encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()

        # Construct response data with base64 encoded hash
        response = {
            'response_token': 'sha256=' + base64.b64encode(sha256_hash_digest).decode('utf-8')
        }

        # Returns properly formatted json response
        print('response', response)
        return jsonify(response)

    elif request.method == 'POST':
        # Stub - we'll implement webhook event handling here
        print("Got POST request")
        
        try:
            data = request.json
            print("Webhook Data:", data)
            
            # Check for different event types
            if 'tweet_create_events' in data:
                for event in data['tweet_create_events']:
                    # Filter out self-replies/tweets if needed, or just log them
                    user = event.get('user', {}).get('screen_name')
                    text = event.get('text', '')
                    
                    if event.get('in_reply_to_status_id'):
                        print(f"👉 EVENT: Reply Tweet from @{user} (to @{event.get('in_reply_to_screen_name')})")
                        print(f"   Text: {text}")

                    else:
                        print(f"👉 EVENT: New Tweet from @{user}")
                        print(f"   Text: {text}")
                        
            elif 'favorite_events' in data:
                for event in data['favorite_events']:
                    liker = event.get('user', {}).get('screen_name')
                    tweet = event.get('favorited_status', {})
                    text = tweet.get('text', '')
                    
                    if tweet.get('in_reply_to_status_id'):
                        print(f"👉 EVENT: Like from @{liker} (on a Reply)")
                    else:
                        print(f"👉 EVENT: Like from @{liker} (on a Tweet)")
                    print(f"   Liked Tweet: {text}")

                    fav_count = tweet.get('favorite_count', 0)
                    
                    should_upload = False
                    if fav_count <= 1: 
                        should_upload = True
                        print(f"   Like count is {fav_count} (triggers upload for count=1)")
                    
                    if should_upload and supabase:
                        try:
                            # 1. CREATE PROJECT FIRST
                            print("   Attempting to create a Project for this tweet...")
                            REPO_CONFIG_ID = "aaaaaaaa-0000-0000-0000-000000000001" 
                            new_project_id = str(uuid.uuid4())
                            
                            # Generate Dynamic Title & Description
                            print("   🤖 Generating project details with Grok...")
                            
                            proj_title = generate_grok_response(
                                "You are a project manager. Generate a concise 3-5 word title for a software project based on this feature request.", 
                                text
                            ) or text[:30] # Fallback
                            
                            proj_desc = generate_grok_response(
                                "You are a technical product owner. Summarize this tweet into a professional 1-sentence feature description.", 
                                text
                            ) or text # Fallback
                            
                            print(f"   Generated Title: {proj_title}")
                            
                            project_data = {
                                "id": new_project_id,
                                "title": proj_title, 
                                "description": proj_desc,
                                "repo_config_id": REPO_CONFIG_ID,
                                "ticket_type": "feature",
                                "status": "pending",
                                "tweet_count": 1,
                                "severity_score": 5
                            }
                            
                            proj_response = supabase.table("projects").insert(project_data).execute()
                            
                            if proj_response.data:
                                print(f"   ✅ Project created successfully: {new_project_id}")
                                
                                # 2. CREATE TWEET (Linked to the new Project)
                                tweet_author_data = tweet.get('user', {})
                                
                                tweet_data = {
                                    "tweet_id": tweet.get('id_str'),
                                    "tweet_text": text,
                                    "tweet_author_id": tweet_author_data.get('id_str'),
                                    "tweet_author_username": tweet_author_data.get('screen_name'),
                                    "tweet_created_at": datetime.now(timezone.utc).isoformat(),
                                    "project_id": new_project_id, # Link to the just-created project
                                    "likes_count": 1,
                                    "retweets_count": 0,
                                    "replies_count": 0,
                                    "processed": False
                                }
                                
                                print(f"   Uploading to Supabase: {tweet_data['tweet_id']}")
                                
                                # Check if tweet already exists
                                existing_tweet = supabase.table("tweets").select("id").eq("tweet_id", tweet_data["tweet_id"]).execute()
                                
                                if existing_tweet.data and len(existing_tweet.data) > 0:
                                    print(f"   ⚠️ Tweet {tweet_data['tweet_id']} already exists. Skipping upload.")
                                else:
                                    response = supabase.table("tweets").insert(tweet_data).execute()
                                    
                                    if response.data:
                                        print("   ✅ Tweet uploaded to Supabase successfully.")
                                        
                                        # 3. SEND DM
                                        token_to_use = None
                                        if 'tokens' in auth_store:
                                            token_to_use = auth_store['tokens']['access_token']
                                        elif ACCESS_TOKEN:
                                            token_to_use = ACCESS_TOKEN
                                            print("   Using Hardcoded Access Token")

                                        if token_to_use:
                                            try:
                                                print(f"   Attempting to DM tweet author @{tweet_data['tweet_author_username']}...")
                                                dm_client = Client(access_token=token_to_use)
                                                author_id = tweet_data['tweet_author_id']
                                                
                                                # Generate Dynamic DM
                                                print("   🤖 Generating DM response with Grok...")
                                                dm_text = generate_grok_response(
                                                    "You are a helpful app developer. Write a friendly, 1-sentence DM to a user thanking them for their idea and mentioning you're starting work on it. Do not include hashtags.",
                                                    f"User Idea: {text}"
                                                )
                                                
                                                if not dm_text:
                                                    dm_text = "Just saw the idea you left on the app - working on implementing this right now; thanks for the feedback!"
                                                
                                                dm_client.direct_messages.create_by_participant_id(
                                                    participant_id=author_id, 
                                                    body={"text": dm_text}
                                                )
                                                print(f"   ✅ DM Sent to @{tweet_data['tweet_author_username']}!")
                                            except Exception as dm_error:
                                                print(f"   ❌ Failed to send DM: {dm_error}")
                                        else:
                                            print("   ⚠️ Cannot send DM: No active session or hardcoded token.")
                                    else:
                                        print("   ⚠️ No data returned from Supabase tweet insert.")
                            else:
                                print("   ❌ Failed to create Project (no data returned). Cannot insert tweet.")
                                
                        except Exception as db_err:
                            print(f"   ❌ Failed to upload to Supabase: {db_err}")
                        
            elif 'follow_events' in data:
                for event in data['follow_events']:
                    target = event.get('target', {}).get('screen_name')
                    source = event.get('source', {}).get('screen_name')
                    print(f"👉 EVENT: Follow (@{source} followed @{target})")
                 
        except Exception as e:
            print(f"Error parsing webhook: {e}")
            
        return 'Event received', 200

    # Got an invalid method
    return 'Method Not Allowed', 405

def process_mention(tweet, author):
    """Process a single mention from the v2 API: create project, store tweet, send DM."""
    text = tweet.get('text', '')
    tweet_id = tweet.get('id')
    author_id = tweet.get('author_id')
    author_username = author.get('username', 'unknown')
    like_count = tweet.get('public_metrics', {}).get('like_count', 0)

    print(f"\n👉 Processing mention from @{author_username}: {text}")

    if not supabase:
        print("   ❌ Supabase not initialized. Skipping.")
        return

    try:
        # 1. CREATE PROJECT
        REPO_CONFIG_ID = "aaaaaaaa-0000-0000-0000-000000000001"
        new_project_id = str(uuid.uuid4())

        print("   🤖 Generating project details with Grok...")
        proj_title = generate_grok_response(
            "You are a project manager. Generate a concise 3-5 word title for a software project based on this feature request.",
            text
        ) or text[:30]

        proj_desc = generate_grok_response(
            "You are a technical product owner. Summarize this tweet into a professional 1-sentence feature description.",
            text
        ) or text

        print(f"   Generated Title: {proj_title}")

        project_data = {
            "id": new_project_id,
            "title": proj_title,
            "description": proj_desc,
            "repo_config_id": REPO_CONFIG_ID,
            "ticket_type": "feature",
            "status": "pending",
            "tweet_count": 1,
            "severity_score": 5
        }

        proj_response = supabase.table("projects").insert(project_data).execute()

        if not proj_response.data:
            print("   ❌ Failed to create Project (no data returned).")
            return

        print(f"   ✅ Project created: {new_project_id}")

        # 2. CREATE TWEET (linked to project)
        tweet_data = {
            "tweet_id": tweet_id,
            "tweet_text": text,
            "tweet_author_id": author_id,
            "tweet_author_username": author_username,
            "tweet_created_at": tweet.get('created_at', datetime.now(timezone.utc).isoformat()),
            "project_id": new_project_id,
            "likes_count": like_count,
            "retweets_count": 0,
            "replies_count": 0,
            "processed": False
        }

        existing_tweet = supabase.table("tweets").select("id").eq("tweet_id", tweet_id).execute()
        if existing_tweet.data and len(existing_tweet.data) > 0:
            print(f"   ⚠️ Tweet {tweet_id} already exists. Skipping.")
            return

        response = supabase.table("tweets").insert(tweet_data).execute()
        if not response.data:
            print("   ⚠️ No data returned from Supabase tweet insert.")
            return

        print("   ✅ Tweet uploaded to Supabase.")

        # 3. SEND DM to the mention author (using OAuth 1.0a)
        try:
            print(f"   Attempting to DM @{author_username}...")
            dm_text = generate_grok_response(
                "You are a helpful app developer. Write a friendly, 1-sentence DM to a user thanking them for their idea and mentioning you're starting work on it. Do not include hashtags.",
                f"User Idea: {text}"
            )
            if not dm_text:
                dm_text = "Just saw the idea you left on the app - working on implementing this right now; thanks for the feedback!"

            dm_oauth = OAuth1(
                CONSUMER_KEY,
                client_secret=CONSUMER_SECRET,
                resource_owner_key=ACCESS_TOKEN,
                resource_owner_secret=ACCESS_TOKEN_SECRET,
            )
            dm_resp = requests.post(
                f"https://api.x.com/2/dm_conversations/with/{author_id}/messages",
                auth=dm_oauth,
                json={"text": dm_text},
            )
            if dm_resp.status_code in (200, 201):
                print(f"   ✅ DM Sent to @{author_username}!")
            else:
                print(f"   ❌ DM failed: {dm_resp.status_code} {dm_resp.text}")
        except Exception as dm_error:
            print(f"   ❌ Failed to send DM: {dm_error}")

    except Exception as e:
        print(f"   ❌ Error processing mention: {e}")


def poll_mentions():
    """Background loop that polls GET /2/users/:id/mentions every 30 seconds."""
    global polling_active, last_seen_id

    oauth = OAuth1(
        CONSUMER_KEY,
        client_secret=CONSUMER_SECRET,
        resource_owner_key=ACCESS_TOKEN,
        resource_owner_secret=ACCESS_TOKEN_SECRET,
    )

    # Get authenticated user's ID
    me_resp = requests.get("https://api.x.com/2/users/me", auth=oauth)
    if me_resp.status_code != 200:
        print(f"❌ Failed to get user ID: {me_resp.status_code} {me_resp.text}")
        polling_active = False
        return

    my_id = me_resp.json()['data']['id']
    my_username = me_resp.json()['data'].get('username', '???')
    print(f"✅ Polling mentions for @{my_username} (ID: {my_id})")

    first_poll = last_seen_id is None

    while polling_active:
        try:
            params = {
                "query": f"@{my_username}",
                "tweet.fields": "public_metrics,created_at",
                "expansions": "author_id",
                "user.fields": "username",
                "max_results": 10,
            }
            if last_seen_id:
                params["since_id"] = last_seen_id

            resp = requests.get(
                "https://api.x.com/2/tweets/search/recent",
                auth=oauth,
                params=params,
            )

            print(f"   [DEBUG] Search status={resp.status_code} body={resp.text[:500]}")

            if resp.status_code == 429:
                reset = resp.headers.get("x-rate-limit-reset")
                wait = int(reset) - int(time.time()) + 1 if reset else 60
                print(f"⏳ Rate limited. Waiting {wait}s...")
                time.sleep(max(wait, 1))
                continue

            if resp.status_code != 200:
                print(f"⚠️ Mentions API error: {resp.status_code} {resp.text}")
                time.sleep(5)
                continue

            data = resp.json()
            tweets = data.get('data', [])
            includes = data.get('includes', {})
            users_map = {u['id']: u for u in includes.get('users', [])}

            if tweets:
                # Update last_seen_id to the newest tweet (first in list)
                last_seen_id = tweets[0]['id']

                if first_poll:
                    print(f"📌 First poll: recorded last_seen_id={last_seen_id}, skipping {len(tweets)} old mention(s).")
                    first_poll = False
                else:
                    print(f"🔔 Found {len(tweets)} new mention(s)!")
                    for tw in tweets:
                        author = users_map.get(tw['author_id'], {"username": "unknown"})
                        process_mention(tw, author)
            else:
                if first_poll:
                    print("📌 First poll: no existing mentions found.")
                    first_poll = False
                else:
                    print("   No new mentions.")

        except Exception as e:
            print(f"❌ Polling error: {e}")

        time.sleep(5)

    print("🛑 Polling stopped.")


@app.route("/start-polling")
def start_polling():
    global polling_thread, polling_active
    if polling_active:
        return jsonify({"status": "Polling is already running."})

    polling_active = True
    polling_thread = threading.Thread(target=poll_mentions, daemon=True)
    polling_thread.start()
    return jsonify({"status": "Polling started. Checking mentions every 30 seconds."})


@app.route("/stop-polling")
def stop_polling():
    global polling_active
    if not polling_active:
        return jsonify({"status": "Polling is not running."})

    polling_active = False
    return jsonify({"status": "Polling stopped."})


if __name__ == "__main__":
    app.run(port=8080, debug=True)
