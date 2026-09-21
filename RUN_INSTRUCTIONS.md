# Running the English-to-Hindi Movie Recap Application

To run this application locally, you will need to start both the Python Backend and the React Frontend. You should open two separate terminal windows.

---

## 1. Starting the Backend (FastAPI)

The backend handles video downloading, transcription (via Groq), translation (via Groq), TTS (via Piper), and synchronization (via FFmpeg).

**Steps:**
1. Open a new terminal window.
2. Navigate to the backend directory:
   ```bash
   cd /Users/kedarbhokare/Desktop/code/ytstoryhindiautomation/backend
   ```
3. Activate the Python virtual environment:
   ```bash
   source venv/bin/activate
   ```
4. Start the FastAPI server using Uvicorn:
   ```bash
   uvicorn main:app --reload
   ```

The backend API will now be running at `http://localhost:8000`.

*Note: Ensure your `.env` file is present in the `backend/` directory with your `GROQ_API_KEY` before starting.*

---

## 2. Starting the Frontend (Vite + React)

The frontend provides the user interface to input YouTube URLs and view progress.

**Steps:**
1. Open a second, new terminal window.
2. Navigate to the frontend directory:
   ```bash
   cd /Users/kedarbhokare/Desktop/code/ytstoryhindiautomation/frontend
   ```
3. Start the Vite development server:
   ```bash
   npm run dev
   ```

The frontend UI will now be available in your browser, typically at `http://localhost:5173`. Open that URL to use the application!
