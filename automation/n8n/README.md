# ViralLoop — n8n Campaign Discovery Sync

This folder contains the official, importable n8n workflow for orchestrating **Automated Content Rewards Campaign Discovery** for ViralLoop.

---

## 1. Architecture & Design Principles

```
  [ Manual Run Trigger ]         [ Daily Schedule Trigger (9 AM) ]
            \                               /
             v                             v
           [ Node: Workflow Configuration ]
           (API_BASE_URL, MAX_CAMPAIGNS, REFRESH_EXISTING)
                          |
                          v
           [ Node: Check Concurrency Lock ] ---> [ If Busy? ] ---> (Abort: Run in Progress)
                          | (Idle)
                          v
           [ Node: Check Auth Status ] --------> [ Auth Required? ] -> (Abort: Login Required)
                          | (OK)
                          v
           [ Node: Trigger Campaign Discovery ]
           (Calls POST /api/campaign-discovery/start)
                          |
                          v
           [ Node: Build Execution Summary ]
           (Generates Markdown & JSON run audit)
```

### Separation of Concerns:
- **FastAPI + Playwright (`backend/campaign_discovery/`):** Handles all browser navigation, DOM parsing, deduplication, normalization, and local file storage (`backend/data/campaigns.json`).
- **n8n (`automation/n8n/`):** Orchestrates triggers (cron & manual), verifies authentication, prevents overlapping runs via server concurrency locks, handles API error codes, and formats run summaries.
- **Source of Truth:** [backend/data/campaigns.json](file:///Users/kedarbhokare/Desktop/code/ytstoryhindiautomation/backend/data/campaigns.json).

---

## 2. Quick Start Guide

### Step 1: Start the ViralLoop FastAPI Backend
```bash
cd backend
./venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
Verify the API is running:
```bash
curl http://127.0.0.1:8000/api/campaign-discovery/status
```

### Step 2: Start n8n
Ensure Node.js 22 is active (if using `nvm`):
```bash
export PATH="/Users/kedarbhokare/.nvm/versions/node/v22.23.2/bin:$PATH"
n8n start
```
The n8n Web UI will be available at: `http://localhost:5678/`

---

## 3. Importing the Workflow

### Via CLI:
```bash
export PATH="/Users/kedarbhokare/.nvm/versions/node/v22.23.2/bin:$PATH"
n8n import:workflow --input=automation/n8n/campaign_discovery_sync.json
```

### Via n8n Web UI:
1. Open `http://localhost:5678/` in your browser.
2. In the left navigation, click **Workflows**.
3. In the top right corner, click **Add Workflow** $\to$ **Import from File...**
4. Select `automation/n8n/campaign_discovery_sync.json`.

---

## 4. Workflow Configuration

Double-click the **Workflow Configuration** node in the n8n canvas to customize runtime parameters:

| Parameter | Default | Description |
|---|---|---|
| `API_BASE_URL` | `http://127.0.0.1:8000` | The base URL of the ViralLoop FastAPI backend. |
| `MAX_CAMPAIGNS` | `10` | Maximum new campaign pages to open and extract per run. |
| `REFRESH_EXISTING` | `false` | When `false`, campaigns already saved in `campaigns.json` are skipped. Set to `true` to re-scrape existing campaigns. |
| `ENFORCE_AUTHENTICATION` | `false` | When `false`, allows public campaign discovery. When `true`, stops the workflow with `NEEDS_AUTHENTICATION` if the session is unauthenticated. |

---

## 5. Execution & Scheduling

### Manual Execution:
- In the n8n Web UI, open the workflow and click **Test workflow** (or click the **Manual Run** node and select **Execute step**).
- Or from CLI:
  ```bash
  export PATH="/Users/kedarbhokare/.nvm/versions/node/v22.23.2/bin:$PATH"
  n8n execute --id=VLDiscovSync0001
  ```

### Enabling Daily Schedule:
1. In the top right of the workflow editor, toggle the switch from **Inactive** to **Active**.
2. By default, the **Daily Schedule** node triggers every day at 9:00 AM (`0 9 * * *`). You can change the cron expression or interval directly in the node.

---

## 6. Execution Monitoring & Error Handling

### Viewing Execution History:
- In the left sidebar of n8n, click **Executions** to view previous runs, durations, and output data.

### Handled Failure Scenarios:

1. **Backend Server Unavailable (`ECONNREFUSED`):**
   - The workflow captures the connection failure, prevents n8n from crashing, and outputs a `FAILED` status report.

2. **Overlapping Execution Attempt:**
   - The backend server enforces an execution lock (`CampaignDiscoveryService._lock`).
   - If a second discovery run is triggered while another is active, the backend returns `HTTP 409 Conflict`.
   - The n8n workflow routes to the **Abort - Run in Progress** branch and exits gracefully.

3. **Unauthenticated Session (when `ENFORCE_AUTHENTICATION: true`):**
   - The workflow queries `GET /api/campaign-discovery/auth-status`.
   - If not logged in, it routes to **Abort - Login Required** and returns instructions to log in.

4. **Troubleshooting Authentication:**
   - To manually log in to Content Rewards in a headed Chromium browser window, call:
     ```bash
     curl -X POST http://127.0.0.1:8000/api/campaign-discovery/manual-login
     ```
   - Log in manually. The persistent profile is stored in `backend/data/browser_profile/` and will be reused for all future runs.

