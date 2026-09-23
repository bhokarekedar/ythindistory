import { useState, useEffect } from 'react'
import './App.css'

function App() {
  const [url, setUrl] = useState('')
  const [jobId, setJobId] = useState(null)
  const [status, setStatus] = useState('')
  const [videoUrl, setVideoUrl] = useState(null)
  
  const [watermark, setWatermark] = useState({
    topLeft: { enabled: false, offsetX: 10, offsetY: 10, size: 50 },
    topRight: { enabled: false, offsetX: 10, offsetY: 10, size: 50 },
    bottomLeft: { enabled: false, offsetX: 10, offsetY: 10, size: 50 },
    bottomRight: { enabled: false, offsetX: 10, offsetY: 10, size: 50 }
  })
  const [textWatermark, setTextWatermark] = useState({
    topLeft: { enabled: false, offsetX: 10, offsetY: 10, size: 50 },
    topRight: { enabled: false, offsetX: 10, offsetY: 10, size: 50 },
    bottomLeft: { enabled: false, offsetX: 10, offsetY: 10, size: 50 },
    bottomRight: { enabled: false, offsetX: 10, offsetY: 10, size: 50 }
  })
  const [snapshotImg, setSnapshotImg] = useState(null)
  const [snapshotLoading, setSnapshotLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!url) return
    setStatus('Starting...')
    try {
      const res = await fetch('http://localhost:8000/api/process', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, watermark, textWatermark })
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

  const handleSnapshot = async () => {
    if (!url) {
      alert("Please enter a YouTube URL first.")
      return
    }
    setSnapshotLoading(true)
    setSnapshotImg(null)
    try {
      const res = await fetch('http://localhost:8000/api/snapshot', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, watermark, textWatermark })
      })
      const data = await res.json()
      if (data.error) {
        alert("Snapshot Error: " + data.error)
      } else if (data.image) {
        setSnapshotImg(data.image)
      }
    } catch (err) {
      alert("Snapshot Request Failed: " + err.message)
    } finally {
      setSnapshotLoading(false)
    }
  }

  const handleWatermarkChange = (corner, field, value) => {
    setWatermark(prev => ({
      ...prev,
      [corner]: {
        ...prev[corner],
        [field]: field === 'enabled' ? value : parseInt(value) || 0
      }
    }))
  }

  const handleTextWatermarkChange = (corner, field, value) => {
    setTextWatermark(prev => ({
      ...prev,
      [corner]: {
        ...prev[corner],
        [field]: field === 'enabled' ? value : parseInt(value) || 0
      }
    }))
  }

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
        
        <div className="watermark-settings">
          <h3>Watermark Settings</h3>
          <div className="corners-grid">
            {['topLeft', 'topRight', 'bottomLeft', 'bottomRight'].map(corner => (
              <div key={corner} className="corner-box">
                <label>
                  <input 
                    type="checkbox" 
                    checked={watermark[corner].enabled}
                    onChange={(e) => handleWatermarkChange(corner, 'enabled', e.target.checked)}
                  />
                  {corner}
                </label>
                {watermark[corner].enabled && (
                  <div className="corner-inputs">
                    <label>X: <input type="number" value={watermark[corner].offsetX} onChange={e => handleWatermarkChange(corner, 'offsetX', e.target.value)} /></label>
                    <label>Y: <input type="number" value={watermark[corner].offsetY} onChange={e => handleWatermarkChange(corner, 'offsetY', e.target.value)} /></label>
                    <label>Size: <input type="number" value={watermark[corner].size} onChange={e => handleWatermarkChange(corner, 'size', e.target.value)} /></label>
                  </div>
                )}
              </div>
            ))}
          </div>

          <h3>Text Watermark Settings</h3>
          <div className="corners-grid">
            {['topLeft', 'topRight', 'bottomLeft', 'bottomRight'].map(corner => (
              <div key={`text-${corner}`} className="corner-box">
                <label>
                  <input 
                    type="checkbox" 
                    checked={textWatermark[corner].enabled}
                    onChange={(e) => handleTextWatermarkChange(corner, 'enabled', e.target.checked)}
                  />
                  {corner}
                </label>
                {textWatermark[corner].enabled && (
                  <div className="corner-inputs">
                    <label>X: <input type="number" value={textWatermark[corner].offsetX} onChange={e => handleTextWatermarkChange(corner, 'offsetX', e.target.value)} /></label>
                    <label>Y: <input type="number" value={textWatermark[corner].offsetY} onChange={e => handleTextWatermarkChange(corner, 'offsetY', e.target.value)} /></label>
                    <label>Size: <input type="number" value={textWatermark[corner].size} onChange={e => handleTextWatermarkChange(corner, 'size', e.target.value)} /></label>
                  </div>
                )}
              </div>
            ))}
          </div>

          <button type="button" onClick={handleSnapshot} disabled={snapshotLoading} className="snapshot-btn">
            {snapshotLoading ? 'Generating Snapshot...' : 'Test Snapshot (1-min mark)'}
          </button>
        </div>
        
        {snapshotImg && (
          <div className="snapshot-preview">
            <h4>Snapshot Preview</h4>
            <img src={snapshotImg} alt="Snapshot Preview" style={{width: '100%', maxWidth: '600px', border: '1px solid #ccc'}} />
          </div>
        )}

        <button type="submit" disabled={!!jobId && !status.includes('Completed') && !status.includes('Error')} className="main-btn">
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
