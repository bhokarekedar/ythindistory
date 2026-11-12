import { useState, useEffect } from 'react'
import './App.css'

const RECAP_WEBHOOK_URL = 'http://localhost:5678/webhook/video-complete'
const THRILLER_WEBHOOK_URL = 'http://localhost:5678/webhook/2a1c46d4-d081-420d-af06-7cc5d94ddaa6'

function App() {
  const [url, setUrl] = useState('')
  const [webhookUrl, setWebhookUrl] = useState(RECAP_WEBHOOK_URL)
  const [jobId, setJobId] = useState(null)
  const [status, setStatus] = useState('')
  const [videoUrl, setVideoUrl] = useState(null)
  const [evaluation, setEvaluation] = useState(null)
  
  const [skipIntervals, setSkipIntervals] = useState([{ start: '', end: '' }])
  
  const [watermark, setWatermark] = useState({
    topLeft: { enabled: false, offsetX: 10, offsetY: 10, size: 180 },
    topRight: { enabled: false, offsetX: 10, offsetY: 10, size: 180 },
    bottomLeft: { enabled: false, offsetX: 10, offsetY: 10, size: 180 },
    bottomRight: { enabled: false, offsetX: 10, offsetY: 10, size: 180 }
  })
  const [textWatermark, setTextWatermark] = useState({
    topLeft: { enabled: false, offsetX: 10, offsetY: 10, size: 180 },
    topRight: { enabled: false, offsetX: 10, offsetY: 10, size: 180 },
    bottomLeft: { enabled: false, offsetX: 10, offsetY: 10, size: 180 },
    bottomRight: { enabled: false, offsetX: 10, offsetY: 10, size: 180 }
  })
  const [snapshotImg, setSnapshotImg] = useState(null)
  const [snapshotLoading, setSnapshotLoading] = useState(false)
  const [channelType, setChannelType] = useState('movie_recap') // 'movie_recap', 'thriller_story', 'full_movie', or 'cartoon_story'
  const [scriptText, setScriptText] = useState('')
  const [storyTitle, setStoryTitle] = useState('')
  const [storageStats, setStorageStats] = useState({ temp_size: '...', output_size: '...' })
  const [datasetCount, setDatasetCount] = useState(0)
  const [cleaning, setCleaning] = useState(false)
  const [burnSubtitles, setBurnSubtitles] = useState(true)
  const [localMovies, setLocalMovies] = useState([])

  // Script Review & Dynamic Resume State
  const [waitingReview, setWaitingReview] = useState(false)
  const [scriptInfo, setScriptInfo] = useState(null)
  const [showScriptEditor, setShowScriptEditor] = useState(false)
  const [scriptSegments, setScriptSegments] = useState([])
  const [scriptFilter, setScriptFilter] = useState('')
  const [isResuming, setIsResuming] = useState(false)
  const [isSavingScript, setIsSavingScript] = useState(false)
  const [scriptSaveMessage, setScriptSaveMessage] = useState('')

  // Visual Storyboard Review & Scene Regeneration State
  const [waitingVisualReview, setWaitingVisualReview] = useState(false)
  const [showVisualReview, setShowVisualReview] = useState(false)
  const [visualData, setVisualData] = useState(null)
  const [visualPrompts, setVisualPrompts] = useState({})
  const [regeneratingSegId, setRegeneratingSegId] = useState(null)
  const [isRenderingFinal, setIsRenderingFinal] = useState(false)

  const fetchStorage = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/storage-stats')
      const data = await res.json()
      setStorageStats(data)
    } catch (e) {
      console.error(e)
    }
  }

  const fetchDatasets = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/training-datasets')
      const data = await res.json()
      setDatasetCount(data.total_datasets || 0)
    } catch (e) {
      console.error(e)
    }
  }

  const fetchLocalMovies = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/local-movies')
      const data = await res.json()
      setLocalMovies(data.movies || [])
    } catch (e) {
      console.error(e)
    }
  }

  useEffect(() => {
    fetchStorage()
    fetchDatasets()
    fetchLocalMovies()
  }, [status])

  const handleClearStorage = async () => {
    if (!window.confirm("Are you sure you want to delete all temporary and output cache files to free disk space?")) return
    setCleaning(true)
    try {
      await fetch('http://localhost:8000/api/cleanup', { method: 'POST' })
      await fetchStorage()
      alert("All temp and output cache cleared successfully!")
    } catch (err) {
      alert("Cleanup failed: " + err.message)
    } finally {
      setCleaning(false)
    }
  }

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
    if (channelType === 'cartoon_story') {
      if (!scriptText.trim()) {
        alert("Please paste your story script in the script box.")
        return
      }
    } else {
      if (!url) {
        alert("Please enter a YouTube URL or file path.")
        return
      }
    }

    const modeLabels = {
      full_movie: 'Full Movie Recap',
      thriller_story: 'Thriller Story',
      cartoon_story: 'Cartoon AI Story',
      movie_recap: 'Movie Recap'
    }
    setStatus(`Starting ${modeLabels[channelType] || 'Video Process'}...`)
    
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
          url: url || '', 
          script_text: channelType === 'cartoon_story' ? scriptText : undefined,
          story_title: channelType === 'cartoon_story' ? storyTitle : undefined,
          watermark, 
          textWatermark, 
          target_language: language, 
          channel_type: channelType,
          skip_intervals: formattedSkipIntervals,
          webhook_url: webhookUrl || undefined,
          burn_subtitles: burnSubtitles
        })
      })
      const data = await res.json()
      setJobId(data.job_id)
      setStatus('Initializing...')
      setEvaluation(null)
      setWaitingReview(false)
      setScriptInfo(null)
      setShowScriptEditor(false)
      setScriptSegments([])
    } catch (err) {
      setStatus(`Error: ${err.message}`)
    }
  }

  const handleResume = async () => {
    if (!jobId) return
    setIsResuming(true)
    try {
      const res = await fetch(`http://localhost:8000/api/resume/${jobId}`, {
        method: 'POST'
      })
      const data = await res.json()
      setStatus('Resuming pipeline: generating voiceover and rendering video...')
      setWaitingReview(false)
      setShowScriptEditor(false)
    } catch (err) {
      alert(`Error resuming pipeline: ${err.message}`)
    } finally {
      setIsResuming(false)
    }
  }

  const handleCancelJob = async () => {
    if (!window.confirm("Do you want to discard this paused job and start fresh?")) return
    if (jobId) {
      try {
        await fetch(`http://localhost:8000/api/cancel/${jobId}`, { method: 'POST' })
      } catch (e) {
        console.error(e)
      }
    }
    setJobId(null)
    setStatus('')
    setWaitingReview(false)
    setWaitingVisualReview(false)
    setShowVisualReview(false)
    setVisualData(null)
    setScriptInfo(null)
    setShowScriptEditor(false)
  }

  const fetchVisualData = async (jid) => {
    try {
      const targetId = jid || jobId
      if (!targetId) return
      const res = await fetch(`http://localhost:8000/api/visual-review/${targetId}`)
      if (res.ok) {
        const data = await res.json()
        setVisualData(data)
        const initPrompts = {}
        data.segments.forEach(s => {
          initPrompts[s.id] = s.image_prompt || ''
        })
        setVisualPrompts(initPrompts)
      }
    } catch (e) {
      console.error("Error loading visual review data:", e)
    }
  }

  const handleRegenerateScene = async (segId) => {
    if (!jobId) return
    const p = visualPrompts[segId]
    setRegeneratingSegId(segId)
    try {
      const res = await fetch(`http://localhost:8000/api/regenerate-scene-image/${jobId}/${segId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: p })
      })
      const data = await res.json()
      if (data.status === 'success' && data.image_url) {
        setVisualData(prev => {
          if (!prev) return prev
          return {
            ...prev,
            segments: prev.segments.map(s => s.id === segId ? { ...s, image_url: data.image_url, image_prompt: p } : s)
          }
        })
      } else {
        alert("Failed to regenerate image: " + (data.detail || "Unknown error"))
      }
    } catch (e) {
      alert("Error regenerating image: " + e.message)
    } finally {
      setRegeneratingSegId(null)
    }
  }

  const handleRenderFinalVideo = async () => {
    if (!jobId) return
    setIsRenderingFinal(true)
    try {
      const res = await fetch(`http://localhost:8000/api/render-final-video/${jobId}`, {
        method: 'POST'
      })
      const data = await res.json()
      setStatus('Rendering final 1080p video with subtitles...')
      setShowVisualReview(false)
    } catch (e) {
      alert("Error starting final video render: " + e.message)
    } finally {
      setIsRenderingFinal(false)
    }
  }

  const handleOpenScriptEditor = async () => {
    if (!jobId) return
    setShowScriptEditor(true)
    setScriptSaveMessage('')
    try {
      const res = await fetch(`http://localhost:8000/api/script/${jobId}`)
      const data = await res.json()
      setScriptSegments(data.segments || [])
    } catch (err) {
      alert(`Error loading script: ${err.message}`)
    }
  }

  const handleSaveScript = async () => {
    if (!jobId) return
    setIsSavingScript(true)
    setScriptSaveMessage('')
    try {
      const res = await fetch(`http://localhost:8000/api/script/${jobId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ segments: scriptSegments })
      })
      const data = await res.json()
      setScriptSaveMessage(`✅ Script saved (${scriptSegments.length} segments)! Click 'Resume' below when ready.`)
    } catch (err) {
      setScriptSaveMessage(`❌ Error saving script: ${err.message}`)
    } finally {
      setIsSavingScript(false)
    }
  }

  useEffect(() => {
    let interval
    if (jobId && !status.includes('Completed') && !status.includes('Error') && !status.includes('Rejected')) {
      interval = setInterval(async () => {
        try {
          const res = await fetch(`http://localhost:8000/api/status/${jobId}`)
          const data = await res.json()
          setStatus(data.status)
          if (data.evaluation) {
            setEvaluation(data.evaluation)
          }
          if (data.waiting_review) {
            setWaitingReview(true)
            setScriptInfo({
              scriptPath: data.script_path,
              videoId: data.video_id,
              channelType: data.channel_type
            })
          } else {
            setWaitingReview(false)
          }
          if (data.waiting_visual_review) {
            setWaitingVisualReview(true)
            if (!visualData) {
              fetchVisualData(jobId)
            }
          } else {
            setWaitingVisualReview(false)
          }
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
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px', flexWrap: 'wrap', gap: '10px' }}>
        <h1 style={{ margin: 0, fontSize: '26px' }}>Automated Video Studio</h1>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ fontSize: '12px', color: '#155724', background: '#d4edda', padding: '6px 12px', borderRadius: '6px', border: '1px solid #c3e6cb' }} title="Permanently saved scripts for LLM fine-tuning (never cleared by temp/output cleanup)">
            📚 Datasets: <b>{datasetCount}</b>
          </span>
          <span style={{ fontSize: '12px', color: '#555', background: '#f1f3f5', padding: '6px 12px', borderRadius: '6px', border: '1px solid #dee2e6' }}>
            💾 Temp: <b>{storageStats.temp_size}</b> | Output: <b>{storageStats.output_size}</b>
          </span>
          <button 
            type="button" 
            onClick={handleClearStorage} 
            disabled={cleaning}
            style={{ 
              padding: '6px 12px', 
              fontSize: '12px', 
              background: '#6c757d', 
              color: 'white', 
              border: 'none', 
              borderRadius: '6px', 
              cursor: 'pointer',
              fontWeight: 'bold',
              transition: 'background 0.2s'
            }}
            onMouseOver={(e) => e.target.style.background = '#5a6268'}
            onMouseOut={(e) => e.target.style.background = '#6c757d'}
          >
            {cleaning ? 'Cleaning...' : '🧹 Clear Storage'}
          </button>
        </div>
      </div>
      
      <form className="input-form">
        {/* Channel Mode Switcher at Top */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '12px', marginBottom: '18px' }}>
          <button
            type="button"
            onClick={() => { 
              setChannelType('movie_recap'); 
              setSnapshotImg(null); 
              setWebhookUrl(RECAP_WEBHOOK_URL);
            }}
            style={{
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
              Film Explanations • 100% Video • <strong>watermark.png</strong>
            </div>
          </button>

          <button
            type="button"
            onClick={() => { 
              setChannelType('thriller_story'); 
              setSnapshotImg(null); 
              setWebhookUrl(THRILLER_WEBHOOK_URL);
            }}
            style={{
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
            <div style={{ fontSize: '15px' }}>🔥 Channel 2: Real Stories Mode</div>
            <div style={{ fontSize: '11px', marginTop: '3px', opacity: 0.85 }}>
              True Incidents • 70/30 AI • <strong>watermark thriller.png</strong>
            </div>
          </button>

          <button
            type="button"
            onClick={() => { 
              setChannelType('full_movie'); 
              setSnapshotImg(null); 
              setWebhookUrl(''); // Auto-upload stopped for full movie local testing
              fetchLocalMovies();
            }}
            style={{
              padding: '12px 14px',
              borderRadius: '8px',
              border: channelType === 'full_movie' ? '2px solid #0284c7' : '1px solid #ccc',
              background: channelType === 'full_movie' ? '#f0f9ff' : '#f9f9f9',
              color: channelType === 'full_movie' ? '#0284c7' : '#666',
              fontWeight: channelType === 'full_movie' ? 'bold' : 'normal',
              cursor: 'pointer',
              textAlign: 'left',
              transition: 'all 0.2s ease'
            }}
          >
            <div style={{ fontSize: '15px' }}>🎥 Channel 3: Full Movie Recap</div>
            <div style={{ fontSize: '11px', marginTop: '3px', opacity: 0.85 }}>
              Local Movie (.mkv/.mp4) • Subtitles • LLM Script
            </div>
          </button>

          <button
            type="button"
            onClick={() => { 
              setChannelType('cartoon_story'); 
              setSnapshotImg(null); 
              setWebhookUrl(''); // Preserved in output folder until fine-tuned
            }}
            style={{
              padding: '12px 14px',
              borderRadius: '8px',
              border: channelType === 'cartoon_story' ? '2px solid #f59e0b' : '1px solid #ccc',
              background: channelType === 'cartoon_story' ? '#fffbeb' : '#f9f9f9',
              color: channelType === 'cartoon_story' ? '#b45309' : '#666',
              fontWeight: channelType === 'cartoon_story' ? 'bold' : 'normal',
              cursor: 'pointer',
              textAlign: 'left',
              transition: 'all 0.2s ease'
            }}
          >
            <div style={{ fontSize: '15px' }}>🎨 Channel 4: Cartoon Story Mode</div>
            <div style={{ fontSize: '11px', marginTop: '3px', opacity: 0.85 }}>
              Pasted Script • 100% Cartoon AI Images • FLUX.1 Anim
            </div>
          </button>
        </div>

        {channelType === 'cartoon_story' ? (
          <div style={{ marginBottom: '16px', textAlign: 'left', width: '100%' }}>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 'bold', color: '#fbbf24', marginBottom: '6px' }}>
              🏷️ Story Title (Optional):
            </label>
            <input 
              type="text" 
              placeholder="e.g. Do Animals Get Bored?" 
              value={storyTitle}
              onChange={(e) => setStoryTitle(e.target.value)}
              style={{
                width: '100%',
                boxSizing: 'border-box',
                padding: '12px 14px',
                borderRadius: '8px',
                border: '1px solid #4b5563',
                background: '#1f2937',
                color: '#ffffff',
                fontSize: '14px',
                marginBottom: '14px',
                outline: 'none'
              }}
            />

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
              <label style={{ fontSize: '13px', fontWeight: 'bold', color: '#fbbf24' }}>
                📝 Paste Story Script or JSON Storyboard:
              </label>
              {(scriptText.trim().startsWith('[') || scriptText.trim().startsWith('{')) && (
                <span style={{ fontSize: '11px', background: '#065f46', color: '#34d399', padding: '2px 8px', borderRadius: '12px', fontWeight: 'bold' }}>
                  ⚡ JSON Mode Detected
                </span>
              )}
            </div>
            <textarea 
              rows={9}
              placeholder="Paste either:&#10;1. Raw script / markdown text (e.g. # Story Title... [HOOK] ...)&#10;2. Pre-structured JSON scenes [ { &quot;id&quot;: 1, &quot;text&quot;: &quot;...&quot;, &quot;image_prompt&quot;: &quot;...&quot; } ]&#10;&#10;If JSON is pasted, the pipeline bypasses LLM decoding, uses your exact prompts, and measures real audio timestamps!"
              value={scriptText}
              onChange={(e) => setScriptText(e.target.value)}
              required
              style={{
                width: '100%',
                boxSizing: 'border-box',
                padding: '14px',
                borderRadius: '8px',
                border: (scriptText.trim().startsWith('[') || scriptText.trim().startsWith('{')) ? '1.5px solid #10b981' : '1.5px solid #f59e0b',
                background: '#181e2b',
                color: '#ffffff',
                fontSize: '14px',
                fontFamily: (scriptText.trim().startsWith('[') || scriptText.trim().startsWith('{')) ? 'monospace' : 'Inter, system-ui, sans-serif',
                resize: 'vertical',
                minHeight: '180px',
                lineHeight: '1.6',
                outline: 'none'
              }}
            />
          </div>
        ) : (
          <input 
            type={channelType === 'full_movie' ? 'text' : 'url'} 
            placeholder={channelType === 'full_movie' ? "Enter local movie file path (e.g. /path/to/movie.mkv) or YouTube URL" : "Enter YouTube URL"} 
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            required
          />
        )}

        {channelType === 'full_movie' && localMovies.length > 0 && (
          <div style={{ marginTop: '8px', marginBottom: '10px', display: 'flex', flexWrap: 'wrap', gap: '8px', alignItems: 'center' }}>
            <span style={{ fontSize: '12px', fontWeight: 'bold', color: '#0369a1' }}>📂 Detected Movies in backend:</span>
            {localMovies.map((m, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => setUrl(m.path)}
                style={{
                  fontSize: '11px',
                  padding: '4px 10px',
                  borderRadius: '16px',
                  border: url === m.path ? '1px solid #0284c7' : '1px solid #cbd5e1',
                  background: url === m.path ? '#e0f2fe' : '#ffffff',
                  color: url === m.path ? '#0369a1' : '#475569',
                  cursor: 'pointer',
                  fontWeight: url === m.path ? 'bold' : 'normal',
                  boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
                  transition: 'all 0.15s ease'
                }}
                title={m.path}
              >
                🎬 {m.name} ({m.size_mb} MB)
              </button>
            ))}
          </div>
        )}

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
              background: channelType === 'thriller_story' ? '#fdeeed' : channelType === 'full_movie' ? '#e0f2fe' : '#e8f7ec', 
              color: channelType === 'thriller_story' ? '#c82333' : channelType === 'full_movie' ? '#0369a1' : '#1e7e34', 
              fontWeight: 'bold',
              border: `1px solid ${channelType === 'thriller_story' ? '#f5c6cb' : channelType === 'full_movie' ? '#bae6fd' : '#c3e6cb'}`
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

        {/* On-Screen Captions Toggle */}
        <div style={{
          padding: '12px 16px',
          background: '#f8fafc',
          border: '1px solid #e2e8f0',
          borderRadius: '8px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginTop: '15px'
        }}>
          <div>
            <div style={{ fontWeight: '600', fontSize: '14px', color: '#1e293b', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span>💬 Burn-In Styled Captions</span>
              <span style={{ fontSize: '11px', background: '#e0f2fe', color: '#0369a1', padding: '2px 8px', borderRadius: '12px', fontWeight: 'bold' }}>
                ⭐️ Highly Recommended for Facebook
              </span>
            </div>
            <div style={{ fontSize: '12px', color: '#64748b', marginTop: '3px' }}>
              Hardcodes crisp bold subtitles (white text + black outline) at bottom-center. Essential since 85% of Facebook users watch on mute.
            </div>
          </div>
          <label style={{ position: 'relative', display: 'inline-block', width: '48px', height: '26px', cursor: 'pointer', margin: 0 }}>
            <input
              type="checkbox"
              checked={burnSubtitles}
              onChange={(e) => setBurnSubtitles(e.target.checked)}
              style={{ opacity: 0, width: 0, height: 0 }}
            />
            <span style={{
              position: 'absolute', cursor: 'pointer', top: 0, left: 0, right: 0, bottom: 0,
              backgroundColor: burnSubtitles ? '#2563eb' : '#cbd5e1',
              transition: '.2s', borderRadius: '26px'
            }}>
              <span style={{
                position: 'absolute', content: '""', height: '20px', width: '20px', left: burnSubtitles ? '24px' : '4px', bottom: '3px',
                backgroundColor: 'white', transition: '.2s', borderRadius: '50%',
                boxShadow: '0 1px 3px rgba(0,0,0,0.3)'
              }} />
            </span>
          </label>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '15px', marginTop: '20px' }}>
          {/* Channel 1: Movie Recap Only */}
          {channelType === 'movie_recap' && (
            <div style={{ padding: '16px', border: '1px solid #28a745', borderRadius: '8px', background: '#f8fff9' }}>
              <h4 style={{ margin: '0 0 10px 0', color: '#1e7e34', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span>🎬 Channel 1: Movie Recap (100% Video Footage)</span>
              </h4>
              <div style={{ display: 'flex', gap: '10px' }}>
                <button 
                  type="button" 
                  onClick={(e) => handleSubmit(e, 'english', 'movie_recap')} 
                  disabled={!!jobId && !status.includes('Completed') && !status.includes('Error') && !status.includes('Rejected')} 
                  className="main-btn" 
                  style={{ backgroundColor: '#28a745', flex: 1 }}
                >
                  Generate English Movie Recap
                </button>
                <button 
                  type="button" 
                  onClick={(e) => handleSubmit(e, 'hindi', 'movie_recap')} 
                  disabled={!!jobId && !status.includes('Completed') && !status.includes('Error') && !status.includes('Rejected')} 
                  className="main-btn"
                  style={{ flex: 1 }}
                >
                  Generate Hindi Movie Recap
                </button>
              </div>
            </div>
          )}

          {/* Channel 2: Thriller Stories Only */}
          {channelType === 'thriller_story' && (
            <div style={{ padding: '16px', border: '1px solid #dc3545', borderRadius: '8px', background: '#fff5f5' }}>
              <h4 style={{ margin: '0 0 10px 0', color: '#c82333', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span>🔥 Channel 2: Thriller Story (70% Video + 30% AI Images)</span>
              </h4>
              <p style={{ fontSize: '12px', color: '#666', margin: '0 0 12px 0' }}>
                Uses suspenseful mystery narration, <code>intro_thriller.mp4</code>, thriller watermarks, and smart Cloudflare FLUX.1 scenes for climactic moments.
              </p>
              <div style={{ display: 'flex', gap: '10px' }}>
                <button 
                  type="button" 
                  onClick={(e) => handleSubmit(e, 'english', 'thriller_story')} 
                  disabled={!!jobId && !status.includes('Completed') && !status.includes('Error') && !status.includes('Rejected')} 
                  className="main-btn" 
                  style={{ backgroundColor: '#dc3545', flex: 1, fontWeight: 'bold', fontSize: '15px' }}
                >
                  Generate English Thriller Story (30% AI)
                </button>
                <button 
                  type="button" 
                  onClick={(e) => handleSubmit(e, 'hindi', 'thriller_story')} 
                  disabled={!!jobId && !status.includes('Completed') && !status.includes('Error') && !status.includes('Rejected')} 
                  className="main-btn" 
                  style={{ backgroundColor: '#6f42c1', flex: 1, fontWeight: 'bold', fontSize: '15px' }}
                >
                  Generate Hindi Thriller Story (30% AI)
                </button>
              </div>
            </div>
          )}

          {/* Channel 3: Full Movie to Recap */}
          {channelType === 'full_movie' && (
            <div style={{ padding: '16px', border: '1px solid #0284c7', borderRadius: '8px', background: '#f0f9ff' }}>
              <h4 style={{ margin: '0 0 10px 0', color: '#0369a1', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span>🎥 Channel 3: Full Movie to Production Recap Script</span>
              </h4>
              <p style={{ fontSize: '12px', color: '#475569', margin: '0 0 12px 0' }}>
                Extracts studio dialogues directly from container subtitles (.srt/.ass) without Whisper noise hallucinations, then crafts a 3-act YouTube recap script.
                <br /><strong>⏸️ The pipeline automatically pauses at review stage</strong> so you can inspect and polish the narration before audio and video are generated.
              </p>
              <div style={{ display: 'flex', gap: '10px' }}>
                <button 
                  type="button" 
                  onClick={(e) => handleSubmit(e, 'english', 'full_movie')} 
                  disabled={!!jobId && !status.includes('Completed') && !status.includes('Error') && !status.includes('Rejected')} 
                  className="main-btn" 
                  style={{ backgroundColor: '#0284c7', flex: 1, fontWeight: 'bold', fontSize: '15px' }}
                >
                  Generate English Movie Recap Script
                </button>
                <button 
                  type="button" 
                  onClick={(e) => handleSubmit(e, 'hindi', 'full_movie')} 
                  disabled={!!jobId && !status.includes('Completed') && !status.includes('Error') && !status.includes('Rejected')} 
                  className="main-btn" 
                  style={{ backgroundColor: '#0891b2', flex: 1, fontWeight: 'bold', fontSize: '15px' }}
                >
                  Generate Hindi Movie Recap Script
                </button>
              </div>
            </div>
          )}

          {/* Channel 4: Cartoon Stories (100% AI Images) */}
          {channelType === 'cartoon_story' && (
            <div style={{ padding: '16px', border: '1px solid #f59e0b', borderRadius: '8px', background: '#fffbeb' }}>
              <h4 style={{ margin: '0 0 10px 0', color: '#b45309', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span>🎨 Channel 4: Cartoon Story (100% AI Images & Narration)</span>
              </h4>
              <p style={{ fontSize: '12px', color: '#78350f', margin: '0 0 12px 0' }}>
                Transforms your pasted script into a fully illustrated cartoon video. The LLM decodes the script into sequential narrative scenes, crafts vivid cartoon prompts for Cloudflare FLUX.1, synthesizes voiceover, and animates every moment with smooth Ken Burns motion.
                <br /><strong>⏸️ Auto-pauses at review</strong> so you can review both the text and image prompts before generating visuals.
              </p>
              <div style={{ display: 'flex', gap: '10px' }}>
                <button 
                  type="button" 
                  onClick={(e) => handleSubmit(e, 'english', 'cartoon_story')} 
                  disabled={!!jobId && !status.includes('Completed') && !status.includes('Error') && !status.includes('Rejected')} 
                  className="main-btn" 
                  style={{ backgroundColor: '#d97706', flex: 1, fontWeight: 'bold', fontSize: '15px' }}
                >
                  Generate English Cartoon Story (100% AI)
                </button>
                <button 
                  type="button" 
                  onClick={(e) => handleSubmit(e, 'hindi', 'cartoon_story')} 
                  disabled={!!jobId && !status.includes('Completed') && !status.includes('Error') && !status.includes('Rejected')} 
                  className="main-btn" 
                  style={{ backgroundColor: '#7c3aed', flex: 1, fontWeight: 'bold', fontSize: '15px' }}
                >
                  Generate Hindi Cartoon Story (100% AI)
                </button>
              </div>
            </div>
          )}
        </div>
      </form>

      {status && (
        <div className="status-container">
          <h3>Status:</h3>
          <p className="status-text">{status}</p>
          {jobId && (channelType === 'cartoon_story' || status.includes('cartoon') || waitingVisualReview) && (
            <div style={{ marginTop: '12px', display: 'flex', gap: '10px' }}>
              <button
                type="button"
                onClick={() => {
                  setShowVisualReview(true)
                  fetchVisualData(jobId)
                }}
                style={{
                  background: '#f59e0b',
                  color: '#000',
                  border: 'none',
                  borderRadius: '6px',
                  padding: '9px 18px',
                  fontWeight: 'bold',
                  cursor: 'pointer',
                  fontSize: '13px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px'
                }}
              >
                🖼️ Open Visual Storyboard Studio (Review & Regenerate Scenes)
              </button>
            </div>
          )}
        </div>
      )}

      {waitingReview && (
        <div className="review-action-card">
          <div className="review-header">
            <span className="review-badge">⏸️ SCRIPT READY — MANUAL REVIEW & FIXES REQUIRED</span>
            <h2 className="review-title">Review Narration Script Before Audio & Video</h2>
            <p className="review-subtitle">
              The AI has completed script translation. Please inspect and correct any character names, clues, or dialogue before synthesizing voiceover and rendering video.
            </p>
            {scriptInfo?.scriptPath && (
              <div className="review-path-box">
                <span className="path-label">Script File:</span>
                <code>{scriptInfo.scriptPath}</code>
              </div>
            )}
          </div>

          <div className="review-actions-row" style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
            <button
              type="button"
              className="btn-resume-pipeline"
              onClick={handleResume}
              disabled={isResuming}
              style={{ flex: 2, minWidth: '260px' }}
            >
              {isResuming ? '⏳ Resuming...' : '▶️ OK, Resume Pipeline (Generate Audio & Video)'}
            </button>
            <button
              type="button"
              className="btn-open-editor"
              onClick={() => {
                if (!showScriptEditor) handleOpenScriptEditor()
                else setShowScriptEditor(false)
              }}
              style={{ flex: 1, minWidth: '180px' }}
            >
              {showScriptEditor ? 'Hide Script Editor' : '📝 Open Script Editor in UI'}
            </button>
            <button
              type="button"
              onClick={handleCancelJob}
              style={{
                backgroundColor: '#dc2626',
                color: '#ffffff',
                border: 'none',
                borderRadius: '8px',
                padding: '12px 18px',
                fontWeight: 'bold',
                cursor: 'pointer',
                fontSize: '14px',
                display: 'flex',
                alignItems: 'center',
                gap: '6px'
              }}
              title="Discard this job and start with a fresh or new script"
            >
              🗑️ Discard & Start Fresh Script
            </button>
          </div>

          {showScriptEditor && (
            <div className="script-editor-container">
              <div className="editor-toolbar">
                <input
                  type="text"
                  placeholder="🔍 Search words or names (e.g. Paige, Corner, Colin, shed)..."
                  value={scriptFilter}
                  onChange={(e) => setScriptFilter(e.target.value)}
                  className="editor-search-input"
                />
                <button
                  type="button"
                  className="btn-save-script"
                  onClick={handleSaveScript}
                  disabled={isSavingScript}
                >
                  {isSavingScript ? 'Saving...' : '💾 Save Changes to Script'}
                </button>
              </div>

              {scriptSaveMessage && (
                <div className={`script-save-msg ${scriptSaveMessage.startsWith('✅') ? 'success' : 'error'}`}>
                  {scriptSaveMessage}
                </div>
              )}

              <div className="segments-scroll-list">
                {scriptSegments
                  .filter(s => {
                    if (!scriptFilter.trim()) return true
                    const q = scriptFilter.toLowerCase()
                    const eng = (s.english || s.hindi || s.hi || s.text || '').toLowerCase()
                    const orig = (s.original_text || '').toLowerCase()
                    return eng.includes(q) || orig.includes(q) || String(s.id).includes(q)
                  })
                  .map((seg) => {
                    const textField = seg.english !== undefined ? 'english' : seg.hindi !== undefined ? 'hindi' : seg.hi !== undefined ? 'hi' : 'text'
                    return (
                      <div key={seg.id} className="segment-card">
                        <div className="segment-meta">
                          <span className="segment-id">#{seg.id}</span>
                          <span className="segment-time">[{seg.start.toFixed(1)}s - {seg.end.toFixed(1)}s]</span>
                          {seg.original_text && (
                            <span className="segment-original" title={seg.original_text}>
                              Orig: {seg.original_text}
                            </span>
                          )}
                        </div>
                        <textarea
                          className="segment-textarea"
                          rows={2}
                          value={seg[textField] || ''}
                          onChange={(e) => {
                            const val = e.target.value
                            setScriptSegments(prev => prev.map(p => p.id === seg.id ? { ...p, [textField]: val } : p))
                          }}
                        />
                        {(seg.image_prompt !== undefined || seg.use_ai_image) && (
                          <div style={{ marginTop: '8px' }}>
                            <div style={{ fontSize: '11px', fontWeight: 'bold', color: '#b45309', marginBottom: '3px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                              <span>🎨 AI Image Prompt (Cloudflare FLUX.1):</span>
                            </div>
                            <textarea
                              className="segment-textarea"
                              rows={2}
                              style={{ border: '1px solid #fcd34d', background: '#fffbeb', fontSize: '12px' }}
                              placeholder="Visual scene prompt for FLUX.1..."
                              value={seg.image_prompt || ''}
                              onChange={(e) => {
                                const val = e.target.value
                                setScriptSegments(prev => prev.map(p => p.id === seg.id ? { ...p, image_prompt: val, use_ai_image: true } : p))
                              }}
                            />
                          </div>
                        )}
                      </div>
                    )
                  })}
              </div>

              <div className="editor-bottom-bar">
                <button
                  type="button"
                  className="btn-save-script"
                  onClick={handleSaveScript}
                  disabled={isSavingScript}
                >
                  {isSavingScript ? 'Saving...' : '💾 Save Changes'}
                </button>
                <button
                  type="button"
                  className="btn-resume-pipeline"
                  onClick={handleResume}
                  disabled={isResuming}
                >
                  {isResuming ? '⏳ Resuming...' : '▶️ Looks Good! Resume Pipeline'}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {waitingVisualReview && (
        <div className="review-action-card" style={{ border: '2px solid #f59e0b', background: '#1c1917', margin: '20px 0' }}>
          <div className="review-header">
            <span className="review-badge" style={{ background: '#f59e0b', color: '#000', fontWeight: 'bold' }}>
              🎨 VISUAL SCENES READY — MANUAL REVIEW & REGENERATE
            </span>
            <h2 className="review-title" style={{ color: '#fbbf24' }}>
              Review & Fine-Tune Cartoon Scenes Before Final Render
            </h2>
            <p className="review-subtitle">
              All 16:9 images have been generated! Inspect each scene beat, edit any prompts to fix limbs or characters, and regenerate scenes with 1-click.
            </p>
          </div>
          <div className="review-actions-row" style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
            <button
              type="button"
              className="btn-resume-pipeline"
              onClick={() => {
                setShowVisualReview(true)
                fetchVisualData(jobId)
              }}
              style={{ background: '#f59e0b', color: '#000', fontWeight: 'bold', fontSize: '15px', flex: 2, minWidth: '260px' }}
            >
              🖼️ Open Visual Storyboard & Prompt Studio ({visualData?.segments?.length || 'Scenes'})
            </button>
            <button
              type="button"
              onClick={handleCancelJob}
              style={{
                backgroundColor: '#dc2626',
                color: '#ffffff',
                border: 'none',
                borderRadius: '8px',
                padding: '12px 18px',
                fontWeight: 'bold',
                cursor: 'pointer',
                fontSize: '14px'
              }}
            >
              🗑️ Discard & Start Fresh Script
            </button>
          </div>
        </div>
      )}

      {showVisualReview && visualData && (
        <div className="visual-review-modal" style={{
          position: 'fixed',
          top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(11, 15, 25, 0.98)',
          zIndex: 10000,
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column'
        }}>
          {/* Top Header Bar */}
          <div style={{
            position: 'sticky', top: 0, zIndex: 100,
            background: '#1e293b', padding: '16px 32px',
            borderBottom: '1px solid #334155',
            display: 'flex', justifyContent: 'space-between', alignItems: 'center'
          }}>
            <div>
              <h2 style={{ margin: 0, color: '#f59e0b', fontSize: '20px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                🎨 Scene Visual Storyboard & Prompt Studio
              </h2>
              <p style={{ margin: '4px 0 0', color: '#94a3b8', fontSize: '14px' }}>
                Story: <strong style={{ color: '#fff' }}>{visualData.story_title || visualData.video_id}</strong> • {visualData.segments?.length || 0} Scene Beats
              </p>
            </div>
            <button onClick={() => setShowVisualReview(false)} style={{ background: '#334155', border: 'none', color: '#fff', borderRadius: '6px', padding: '8px 16px', fontWeight: 'bold', cursor: 'pointer' }}>
              ✕ Close
            </button>
          </div>

          {/* Scrollable Content Container */}
          <div style={{ maxWidth: '1240px', width: '100%', margin: '0 auto', padding: '24px 20px 120px 20px', flex: 1, boxSizing: 'border-box' }}>
            <div style={{ background: '#1e293b', borderRadius: '8px', padding: '14px 20px', marginBottom: '24px', borderLeft: '4px solid #3b82f6' }}>
              <p style={{ margin: 0, color: '#cbd5e1', fontSize: '14px', lineHeight: 1.5 }}>
                💡 <strong>Art Director Review:</strong> Inspect each generated scene below. If any image has strange limbs, unwanted animals, or awkward poses, simply edit its <strong>Image Prompt</strong> in the box and click <strong>"🔄 Regenerate This Image"</strong>. Once satisfied with all scenes, click the green button at the bottom to render the final video.
              </p>
            </div>

            {visualData.segments.map((seg) => (
              <div key={seg.id} style={{
                background: '#181e2b',
                border: '1px solid #334155',
                borderRadius: '12px',
                marginBottom: '24px',
                overflow: 'hidden',
                display: 'grid',
                gridTemplateColumns: 'minmax(340px, 480px) 1fr',
                gap: '24px',
                padding: '20px'
              }}>
                {/* Left: 16:9 Image Preview */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <div style={{
                    width: '100%',
                    aspectRatio: '16 / 9',
                    borderRadius: '8px',
                    overflow: 'hidden',
                    background: '#0f172a',
                    border: '1px solid #334155',
                    position: 'relative'
                  }}>
                    {seg.image_url ? (
                      <img
                        key={seg.image_url}
                        src={seg.image_url}
                        alt={`Scene ${seg.id}`}
                        style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                      />
                    ) : (
                      <div style={{ display: 'flex', height: '100%', alignItems: 'center', justifyContent: 'center', color: '#64748b' }}>
                        No image generated yet
                      </div>
                    )}
                    <span style={{
                      position: 'absolute', bottom: '8px', right: '8px',
                      background: 'rgba(0,0,0,0.75)', color: '#fff', fontSize: '11px',
                      padding: '2px 8px', borderRadius: '4px', fontWeight: 600
                    }}>
                      1920 × 1080 (16:9)
                    </span>
                  </div>
                </div>

                {/* Right: Scene Details & Editable Prompt */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{
                      background: '#3b82f6', color: '#fff', fontSize: '13px',
                      fontWeight: 'bold', padding: '4px 12px', borderRadius: '12px'
                    }}>
                      Scene #{seg.id} • [{Number(seg.start).toFixed(1)}s - {Number(seg.end).toFixed(1)}s]
                    </span>
                  </div>

                  {/* Spoken Text */}
                  <div>
                    <label style={{ fontSize: '11px', fontWeight: 'bold', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                      Spoken Narration Text:
                    </label>
                    <p style={{
                      margin: '6px 0 0',
                      background: '#0f172a',
                      padding: '12px 14px',
                      borderRadius: '6px',
                      border: '1px solid #1e293b',
                      color: '#ffffff',
                      fontSize: '15px',
                      fontWeight: 500,
                      lineHeight: 1.4
                    }}>
                      "{seg.text}"
                    </p>
                  </div>

                  {/* Editable Image Prompt */}
                  <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
                    <label style={{ fontSize: '11px', fontWeight: 'bold', color: '#f59e0b', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '6px' }}>
                      Image Prompt (Editable):
                    </label>
                    <textarea
                      value={visualPrompts[seg.id] !== undefined ? visualPrompts[seg.id] : (seg.image_prompt || '')}
                      onChange={(e) => setVisualPrompts({ ...visualPrompts, [seg.id]: e.target.value })}
                      rows={5}
                      style={{
                        width: '100%',
                        boxSizing: 'border-box',
                        background: '#0b1320',
                        border: '1px solid #475569',
                        borderRadius: '6px',
                        color: '#e2e8f0',
                        fontSize: '13px',
                        padding: '10px 12px',
                        fontFamily: 'monospace',
                        lineHeight: 1.45,
                        resize: 'vertical'
                      }}
                    />
                  </div>

                  {/* Action Button */}
                  <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '4px' }}>
                    <button
                      type="button"
                      disabled={regeneratingSegId === seg.id}
                      onClick={() => handleRegenerateScene(seg.id)}
                      style={{
                        background: regeneratingSegId === seg.id ? '#475569' : '#0284c7',
                        color: '#fff',
                        border: 'none',
                        borderRadius: '6px',
                        padding: '10px 20px',
                        fontSize: '14px',
                        fontWeight: 'bold',
                        cursor: regeneratingSegId === seg.id ? 'not-allowed' : 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px',
                        boxShadow: '0 2px 6px rgba(2, 132, 199, 0.3)'
                      }}
                    >
                      {regeneratingSegId === seg.id ? '⏳ Generating 1080p Image...' : '🔄 Regenerate This Image'}
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Sticky Bottom Action Bar */}
          <div style={{
            position: 'fixed',
            bottom: 0, left: 0, right: 0,
            background: '#0f172a',
            borderTop: '2px solid #334155',
            padding: '16px 32px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            zIndex: 10001,
            boxShadow: '0 -10px 25px -5px rgba(0, 0, 0, 0.6)'
          }}>
            <div style={{ color: '#94a3b8', fontSize: '15px' }}>
              Reviewed Scenes: <strong style={{ color: '#fff' }}>{visualData.segments?.length || 0}</strong> • Ready to render?
            </div>
            <div style={{ display: 'flex', gap: '14px' }}>
              <button
                type="button"
                onClick={() => setShowVisualReview(false)}
                style={{
                  background: '#334155',
                  color: '#e2e8f0',
                  border: 'none',
                  borderRadius: '8px',
                  padding: '12px 20px',
                  fontWeight: 600,
                  cursor: 'pointer'
                }}
              >
                Close Studio
              </button>
              <button
                type="button"
                disabled={isRenderingFinal}
                onClick={handleRenderFinalVideo}
                style={{
                  background: isRenderingFinal ? '#166534' : '#16a34a',
                  color: '#ffffff',
                  border: 'none',
                  borderRadius: '8px',
                  padding: '14px 32px',
                  fontSize: '16px',
                  fontWeight: 'bold',
                  cursor: isRenderingFinal ? 'not-allowed' : 'pointer',
                  boxShadow: '0 4px 14px rgba(22, 163, 74, 0.5)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px'
                }}
              >
                {isRenderingFinal ? '⏳ Rendering 1080p Video...' : '🎬 OK, I Am Good! Create Video'}
              </button>
            </div>
          </div>
        </div>
      )}

      {evaluation && (
        <div className={`quality-badge-container ${evaluation.score >= 90 ? 'approved' : 'rejected'}`}>
          <div className="quality-header">
            <span className="quality-score-pill">
              Score: {evaluation.score}% {evaluation.score >= 90 ? '✅ APPROVED' : '❌ REJECTED (<90% threshold)'}
            </span>
            <span className="quality-verdict">{evaluation.verdict}</span>
          </div>
          <p className="quality-reason"><strong>Analysis:</strong> {evaluation.reason}</p>
          {evaluation.detected_flaws && evaluation.detected_flaws.length > 0 && (
            <div className="quality-flaws-section">
              <strong>Detected Flaws:</strong>
              <ul className="quality-flaws-list">
                {evaluation.detected_flaws.map((flaw, i) => (
                  <li key={i}>{flaw}</li>
                ))}
              </ul>
            </div>
          )}
          {evaluation.recommendation && (
            <div className="quality-recommendation">
              <strong>Recommendation:</strong> {evaluation.recommendation}
            </div>
          )}
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
