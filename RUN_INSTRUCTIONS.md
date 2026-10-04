# Running the Automated Movie Recap Application

This application consists of a **Python Backend** (video processing), a **React Frontend** (UI), and an **n8n Automation Pipeline** (YouTube publisher). 

---

## ⚡ Quick Start (Copy-Paste Commands)

To run the entire suite, open 3 separate terminal tabs and paste these commands:

**Terminal 1: Start n8n Publisher**
```bash
export N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS=false && npx n8n
```

**Terminal 2: Start Python Backend**
```bash
cd /Users/kedarbhokare/Desktop/code/ytstoryhindiautomation/backend && source venv/bin/activate && uvicorn main:app --reload
```

**Terminal 3: Start React Frontend**
```bash
cd /Users/kedarbhokare/Desktop/code/ytstoryhindiautomation/frontend && npm run dev
```

---

## 1. n8n YouTube Publisher Setup

The n8n workflow acts as a "Receiver". Once the Python backend finishes rendering a video, it automatically pings n8n. n8n then downloads the video over HTTP from the backend and pushes it to YouTube as a Private draft.

- **Access n8n:** `http://localhost:5678`
- **Workflow:** Ensure your "Receiver" workflow is toggled to **Active** in the top right corner.

### 🛠 Troubleshooting n8n Google Credentials
If your YouTube upload node starts failing or saying "Credentials expired / Access Denied", you need to update or re-authorize your Google Cloud App.

1. **Re-authorize in n8n:** 
   - Open your YouTube node in n8n.
   - Click the Credential dropdown and select your existing Google credential.
   - Click **Reconnect** or **Sign in with Google** again.
2. **Google Cloud Console:** 
   - If you get an "Error 403: access_denied" screen, go to the [Google Cloud Console](https://console.cloud.google.com/).
   - Search for **Google Auth Platform** (or OAuth Consent Screen).
   - Go to **Audience** (or Test Users) on the left sidebar.
   - Ensure your exact YouTube email address is listed under **Test Users**.
   - (Note: Because your app is in "Testing" mode, credentials may expire every 7 days. Just click "Sign in with Google" in n8n to refresh them, or click "Publish App" in Google Cloud to stop the 7-day expiration).

---

## 2. Starting the Backend (FastAPI)

The backend handles video downloading, transcription (via Groq Whisper), script rewriting (via Groq LLM), TTS, and synchronization (via FFmpeg). It also serves the completed `.mp4` files statically over HTTP so n8n can access them.

- **API URL:** `http://localhost:8000`
- **Swagger Docs:** `http://localhost:8000/docs`

*Note: Ensure your `config.yaml` and `.env` file (containing `GROQ_API_KEY` and `GROQ_API_KEY_TWO`) are present in the `backend/` directory.*

---

## 3. Starting the Frontend (Vite + React)

The frontend provides the user interface to input YouTube URLs, set watermark properties, manage skip intervals, and trigger the webhook.

- **App URL:** `http://localhost:5173`

When you click "Generate", the frontend passes your n8n Webhook URL to the backend. The backend does the heavy processing, and when finished, silently routes the file to your YouTube channel!

---

## 4. How We Connected YouTube to n8n (From Scratch)

Because n8n is self-hosted, it requires you to create your own Google Cloud app to authorize YouTube uploads. If you ever need to rebuild this from scratch on a new machine, follow these exact steps:

### Step 1: Start the Credential in n8n
1. In your n8n YouTube node, click the **Credential** dropdown and select **Create New Credential** -> **YouTube OAuth2 API**.
2. Copy the **OAuth Redirect URL** (usually `http://localhost:5678/rest/oauth2-credential/callback`). 

### Step 2: Create the Google Cloud App
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a **New Project** (e.g., "n8n YouTube").
3. Search for **YouTube Data API v3** in the top search bar and click **Enable**.

### Step 3: Configure the OAuth Screen
1. Go to **Google Auth Platform** (or APIs & Services -> Credentials).
2. Configure your Consent Screen. Choose **External**, fill in the required App Name/Email fields, and click Save through the Scopes sections.
3. Under the **Audience** (or Test Users) tab, click **+ Add Users** and type the exact email address of your YouTube channel.

### Step 4: Get your Keys
1. Go to the **Clients** (or Credentials) tab.
2. Click **+ Create Credentials** -> **OAuth client ID**.
3. Application type: **Web application**.
4. Under **Authorized redirect URIs**, paste the n8n Redirect URL you copied in Step 1.
5. Click Create. Google will give you a **Client ID** and **Client Secret**.

### Step 5: Connect it to n8n
1. Paste the **Client ID** and **Client Secret** into your n8n window.
2. Click **Sign in with Google**. (If Google warns the app is unverified, click Advanced -> Continue, since you are the developer).
3. The node will now have full permission to upload videos to your channel!
