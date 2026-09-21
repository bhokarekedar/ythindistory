import { useState, useEffect } from 'react'
import './App.css'

function App() {
  const [url, setUrl] = useState('')
  const [jobId, setJobId] = useState(null)
  const [status, setStatus] = useState('')
  const [videoUrl, setVideoUrl] = useState(null)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!url) return
    setStatus('Starting...')
    try {
      const res = await fetch('http://localhost:8000/api/process', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url })
      })
      const data = await res.json()
      setJobId(data.job_id)
      setStatus('Initializing...')
    } catch (err) {
      setStatus(`Error: ${err.message}`)
    }
  }

  useEffect(() => {
    let interval
    if (jobId && !status.includes('Completed') && !status.includes('Error')) {
      interval = setInterval(async () => {
        try {
          const res = await fetch(`http://localhost:8000/api/status/${jobId}`)
          const data = await res.json()
          setStatus(data.status)
          if (data.status.includes('Completed')) {
            const path = data.status.split(': ')[1]
            setVideoUrl(path)
          }
        } catch (err) {
          console.error(err)
        }
      }, 2000)
    }
    return () => clearInterval(interval)
  }, [jobId, status])

  return (
    <div className="container">
      <h1>Automated English-to-Hindi Movie Recap</h1>
      
      <form onSubmit={handleSubmit} className="input-form">
        <input 
          type="url" 
          placeholder="Enter YouTube URL" 
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          required
        />
        <button type="submit" disabled={!!jobId && !status.includes('Completed') && !status.includes('Error')}>
          Generate Hindi Video
        </button>
      </form>

      {status && (
        <div className="status-container">
          <h3>Status:</h3>
          <p className="status-text">{status}</p>
        </div>
      )}

      {videoUrl && (
        <div className="video-container">
          <h3>Final Video Saved At:</h3>
          <code>{videoUrl}</code>
        </div>
      )}
    </div>
  )
}

export default App
