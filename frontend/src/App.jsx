import { useState, useEffect } from 'react'
import './App.css'

function App() {
  const [url, setUrl] = useState('')
  const [webhookUrl, setWebhookUrl] = useState('http://localhost:5678/webhook/video-complete')
  const [jobId, setJobId] = useState(null)
  const [status, setStatus] = useState('')
  const [videoUrl, setVideoUrl] = useState(null)
  
  const [skipIntervals, setSkipIntervals] = useState([{ start: '', end: '' }])
  
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
  const [channelType, setChannelType] = useState('movie_recap') // 'movie_recap' or 'thriller_story'

  const parseTimeToSeconds = (timeStr) => {
    if (!timeStr) return 0;
    const str = timeStr.toString().replace(':', '.');
    if (str.includes('.')) {
        const parts = str.split('.');
        const mins = parseInt(parts[0]) || 0;
        const secs = parseInt(parts[1]) || 0;
        return mins * 60 + secs;
    }
    return parseFloat(timeStr) || 0;
  }

  const handleSubmit = async (e, language, channelType = 'movie_recap') => {
    e.preventDefault()
    if (!url) return
    setStatus(`Starting ${channelType === 'thriller_story' ? 'Thriller Story' : 'Movie Recap'}...`)
    
    const formattedSkipIntervals = skipIntervals
      .filter(s => s.start !== '' && s.end !== '')
      .map(s => ({
        start: parseTimeToSeconds(s.start),
        end: parseTimeToSeconds(s.end)
      }))

    try {
      const res = await fetch('http://localhost:8000/api/process', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          url, 
          watermark, 
          textWatermark, 
          target_language: language, 
          channel_type: channelType,
          skip_intervals: formattedSkipIntervals,
          webhook_url: webhookUrl || undefined
        })
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
        body: JSON.stringify({ url, watermark, textWatermark, channel_type: channelType })
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

  const handleAddSkip = () => {
    setSkipIntervals([...skipIntervals, { start: '', end: '' }])
  }

  const handleRemoveSkip = (index) => {
    const newSkips = [...skipIntervals]
    newSkips.splice(index, 1)
    setSkipIntervals(newSkips)
  }

  const handleSkipChange = (index, field, value) => {
    const newSkips = [...skipIntervals]
    newSkips[index][field] = value
    setSkipIntervals(newSkips)
  }

  return (
    <div className="container">
      <h1>Automated Movie Recap</h1>
      
      <form className="input-form">
        {/* Channel Mode Switcher at Top */}
        <div style={{ display: 'flex', gap: '12px', marginBottom: '18px' }}>
          <button
            type="button"
            onClick={() => { setChannelType('movie_recap'); setSnapshotImg(null); }}
            style={{
              flex: 1,
              padding: '12px 14px',
              borderRadius: '8px',
              border: channelType === 'movie_recap' ? '2px solid #28a745' : '1px solid #ccc',
              background: channelType === 'movie_recap' ? '#e8f7ec' : '#f9f9f9',
              color: channelType === 'movie_recap' ? '#1e7e34' : '#666',
              fontWeight: channelType === 'movie_recap' ? 'bold' : 'normal',
              cursor: 'pointer',
              textAlign: 'left',
              transition: 'all 0.2s ease'
            }}
          >
            <div style={{ fontSize: '15px' }}>🎬 Channel 1: Movie Recap Mode</div>
            <div style={{ fontSize: '11px', marginTop: '3px', opacity: 0.85 }}>
              Active Logo: <strong>watermark.png</strong> • 100% Video
            </div>
          </button>

          <button
            type="button"
            onClick={() => { setChannelType('thriller_story'); setSnapshotImg(null); }}
            style={{
              flex: 1,
              padding: '12px 14px',
              borderRadius: '8px',
              border: channelType === 'thriller_story' ? '2px solid #dc3545' : '1px solid #ccc',
              background: channelType === 'thriller_story' ? '#fdeeed' : '#f9f9f9',
              color: channelType === 'thriller_story' ? '#c82333' : '#666',
              fontWeight: channelType === 'thriller_story' ? 'bold' : 'normal',
              cursor: 'pointer',
              textAlign: 'left',
              transition: 'all 0.2s ease'
            }}
          >
            <div style={{ fontSize: '15px' }}>🔥 Channel 2: Thriller Story Mode</div>
            <div style={{ fontSize: '11px', marginTop: '3px', opacity: 0.85 }}>
              Active Logo: <strong>watermark thriller.png</strong> • 70/30 AI
            </div>
          </button>
        </div>

        <input 
          type="url" 
          placeholder="Enter YouTube URL" 
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          required
        />

        <input 
          type="url" 
          placeholder="n8n Webhook URL (Optional)" 
          value={webhookUrl}
          onChange={(e) => setWebhookUrl(e.target.value)}
          style={{ marginTop: '10px' }}
        />
        
        <div className="watermark-settings">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
            <h3 style={{ margin: 0 }}>Watermark Settings</h3>
            <span style={{ 
              fontSize: '12px', 
              padding: '3px 8px', 
              borderRadius: '4px', 
              background: channelType === 'thriller_story' ? '#fdeeed' : '#e8f7ec', 
              color: channelType === 'thriller_story' ? '#c82333' : '#1e7e34', 
              fontWeight: 'bold',
              border: `1px solid ${channelType === 'thriller_story' ? '#f5c6cb' : '#c3e6cb'}`
            }}>
              Using: {channelType === 'thriller_story' ? 'watermark thriller.png' : 'watermark.png'}
            </span>
          </div>
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
            {snapshotLoading ? 'Generating Snapshot...' : `Test Snapshot (${channelType === 'thriller_story' ? 'Thriller Logo' : 'Movie Recap Logo'})`}
          </button>
        </div>

        <div className="skip-settings" style={{ marginTop: '20px', padding: '15px', border: '1px solid #ddd', borderRadius: '8px' }}>
          <h3>Skip Video Segments (Optional)</h3>
          <p style={{ fontSize: '12px', color: '#666' }}>Exclude parts of the original video (e.g., promos). Use format MM:SS or MM.SS (like 0.44 or 1:34).</p>
          {skipIntervals.map((skip, idx) => (
            <div key={idx} style={{ display: 'flex', gap: '10px', alignItems: 'center', marginBottom: '10px' }}>
              <input 
                type="text" 
                placeholder="Start (e.g. 0.44)" 
                value={skip.start}
                onChange={(e) => handleSkipChange(idx, 'start', e.target.value)}
                style={{ width: '120px' }}
              />
              <span>to</span>
              <input 
                type="text" 
                placeholder="End (e.g. 1.34)" 
                value={skip.end}
                onChange={(e) => handleSkipChange(idx, 'end', e.target.value)}
                style={{ width: '120px' }}
              />
              {skipIntervals.length > 1 && (
                <button type="button" onClick={() => handleRemoveSkip(idx)} style={{ padding: '5px 10px', background: '#ff4444', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>X</button>
              )}
            </div>
          ))}
          <button type="button" onClick={handleAddSkip} style={{ padding: '5px 10px', background: '#007bff', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>+ Add Skip Interval</button>
        </div>
        
        {snapshotImg && (
          <div className="snapshot-preview">
            <h4>Snapshot Preview</h4>
            <img src={snapshotImg} alt="Snapshot Preview" style={{width: '100%', maxWidth: '600px', border: '1px solid #ccc'}} />
          </div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: '15px', marginTop: '25px' }}>
          {/* Channel 1: Movie Recap */}
          <div style={{ padding: '14px', border: '1px solid #28a745', borderRadius: '8px', background: '#f8fff9' }}>
            <h4 style={{ margin: '0 0 10px 0', color: '#1e7e34', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span>🎬 Channel 1: Movie Recap (100% Video Footage)</span>
            </h4>
            <div style={{ display: 'flex', gap: '10px' }}>
              <button 
                type="button" 
                onClick={(e) => handleSubmit(e, 'english', 'movie_recap')} 
                disabled={!!jobId && !status.includes('Completed') && !status.includes('Error')} 
                className="main-btn" 
                style={{ backgroundColor: '#28a745', flex: 1 }}
              >
                Generate English Movie Recap
              </button>
              <button 
                type="button" 
                onClick={(e) => handleSubmit(e, 'hindi', 'movie_recap')} 
                disabled={!!jobId && !status.includes('Completed') && !status.includes('Error')} 
                className="main-btn"
                style={{ flex: 1 }}
              >
                Generate Hindi Movie Recap
              </button>
            </div>
          </div>

          {/* Channel 2: Thriller Stories */}
          <div style={{ padding: '14px', border: '1px solid #dc3545', borderRadius: '8px', background: '#fff5f5' }}>
            <h4 style={{ margin: '0 0 10px 0', color: '#c82333', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span>🔥 Channel 2: Thriller Story (70% Video + 30% AI Images)</span>
            </h4>
            <p style={{ fontSize: '12px', color: '#666', margin: '0 0 10px 0' }}>
              Uses suspenseful mystery narration, <code>intro_thriller.mp4</code>, thriller watermarks, and smart Cloudflare FLUX.1 scenes for climactic moments.
            </p>
            <button 
              type="button" 
              onClick={(e) => handleSubmit(e, 'english', 'thriller_story')} 
              disabled={!!jobId && !status.includes('Completed') && !status.includes('Error')} 
              className="main-btn" 
              style={{ backgroundColor: '#dc3545', width: '100%', fontWeight: 'bold', fontSize: '15px' }}
            >
              Generate Thriller Story (English + 30% FLUX.1 AI Visuals)
            </button>
          </div>
        </div>
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
