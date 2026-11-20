import { useState, useEffect } from 'react'

export default function LiveStreamClipper() {
  const [streamUrl, setStreamUrl] = useState('')
  const [spikeThreshold, setSpikeThreshold] = useState(2.0)
  const [maxClips, setMaxClips] = useState(3)
  const [clipDuration, setClipDuration] = useState(45)
  const [layoutMode, setLayoutMode] = useState('blurred_stack')

  // Auto-Pilot state (Auto Clip & Direct YouTube Upload)
  const [autoPilotCount, setAutoPilotCount] = useState(3)
  const [autoPilotPrivacy, setAutoPilotPrivacy] = useState('public')
  const [autoPilotRunning, setAutoPilotRunning] = useState(false)
  const [autoPilotProgress, setAutoPilotProgress] = useState('')
  const [autoPilotCompleted, setAutoPilotCompleted] = useState(false)

  // Analysis state
  const [analyzing, setAnalyzing] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')
  const [streamInfo, setStreamInfo] = useState(null)
  const [moments, setMoments] = useState([])
  const [timeline, setTimeline] = useState([])
  const [stats, setStats] = useState(null)

  // Clip state: moment_id -> { rendering, rendered, video_url, metadata, publishing, published, publish_result, error }
  const [clipStates, setClipStates] = useState({})

  // YouTube auth state
  const [ytAuth, setYtAuth] = useState(null)

  useEffect(() => {
    fetchYouTubeStatus()
  }, [])

  const fetchYouTubeStatus = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/stream-clipper/youtube-status')
      if (res.ok) {
        const data = await res.json()
        setYtAuth(data.auth)
      }
    } catch (err) {
      console.warn('Could not fetch YouTube auth:', err)
    }
  }

  // Auto-Pilot: 1-Click Clip & Direct Upload Top Moments (No manual approval needed)
  const handleAutoPilotUpload = async () => {
    if (!streamUrl.trim()) {
      setErrorMsg('Please enter a livestream or VOD URL')
      return
    }
    setErrorMsg('')
    setAutoPilotRunning(true)
    setAutoPilotCompleted(false)
    setAutoPilotProgress('1/3: Analyzing stream chat velocity & detecting peak explosion moments...')
    setStreamInfo(null)
    setMoments([])
    setTimeline([])
    setClipStates({})

    try {
      const res = await fetch('http://localhost:8000/api/stream-clipper/auto-upload-top-moments', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: streamUrl.trim(),
          top_n: parseInt(autoPilotCount),
          spike_threshold: parseFloat(spikeThreshold),
          clip_duration: parseInt(clipDuration),
          layout: layoutMode,
          privacy_status: autoPilotPrivacy
        })
      })

      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Auto-upload failed')
      }

      const data = await res.json()
      setStreamInfo(data.stream_info)

      const newClipStates = {}
      const newMoments = (data.results || []).map((r, idx) => {
        newClipStates[r.moment_id] = {
          rendering: false,
          rendered: true,
          video_url: `http://localhost:8000${r.video_url}`,
          clip_id: r.clip_id,
          metadata: {
            title: r.title,
            privacy: autoPilotPrivacy
          },
          publishing: false,
          published: true,
          publish_result: r.upload_result,
          error: null
        }
        return {
          id: r.moment_id,
          rank: idx + 1,
          peak_time_str: r.peak_time_str,
          peak_velocity: r.peak_velocity,
          suggested_title: r.title,
          duration: clipDuration
        }
      })

      setMoments(newMoments)
      setClipStates(newClipStates)
      setAutoPilotCompleted(true)
      setAutoPilotProgress(`🎉 All ${data.uploaded_count} top moments clipped & published directly to YouTube!`)
    } catch (err) {
      setErrorMsg(err.message || 'Auto-upload failed. Please verify YouTube connection and URL.')
    } finally {
      setAutoPilotRunning(false)
    }
  }

  // Analyze First (Inspect Moments)
  const handleAnalyze = async () => {
    if (!streamUrl.trim()) {
      setErrorMsg('Please enter a livestream or VOD URL')
      return
    }
    setErrorMsg('')
    setAnalyzing(true)
    setAutoPilotCompleted(false)
    setStreamInfo(null)
    setMoments([])
    setTimeline([])
    setClipStates({})

    try {
      const res = await fetch('http://localhost:8000/api/stream-clipper/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: streamUrl.trim(),
          spike_threshold: parseFloat(spikeThreshold),
          max_clips: parseInt(maxClips),
          clip_duration: parseInt(clipDuration)
        })
      })

      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Failed to analyze stream chat')
      }

      const data = await res.json()
      setStreamInfo(data.stream_info)
      setMoments(data.moments || [])
      setTimeline(data.timeline || [])
      setStats(data.stats || {})

      const initial = {}
        ; (data.moments || []).forEach(m => {
          initial[m.id] = {
            rendering: false,
            rendered: false,
            video_url: null,
            metadata: {
              title: m.suggested_title,
              description: `Live chat exploded during ${data.stream_info?.uploader || 'the stream'}! \n\n#Shorts #LiveStream #Highlights`,
              tags: ['Shorts', 'StreamHighlights', ...(m.top_keywords || [])],
              privacy: autoPilotPrivacy
            },
            publishing: false,
            published: false,
            publish_result: null,
            error: null
          }
        })
      setClipStates(initial)
    } catch (err) {
      setErrorMsg(err.message || 'Stream analysis failed. Please check the URL.')
    } finally {
      setAnalyzing(false)
    }
  }

  // 1-Click Direct Clip & Upload for an individual moment
  const handleDirectClipAndUpload = async (moment) => {
    const momentId = moment.id
    setClipStates(prev => ({
      ...prev,
      [momentId]: { ...prev[momentId], rendering: true, error: null }
    }))

    try {
      // 1. Render clip
      const renderRes = await fetch('http://localhost:8000/api/stream-clipper/render-clip', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: streamUrl.trim(),
          moment_id: momentId,
          start_time: moment.start_time,
          duration: moment.duration,
          layout: layoutMode,
          stream_title: streamInfo?.title || '',
          streamer: streamInfo?.uploader || '',
          top_keywords: moment.top_keywords || [],
          sample_chat: moment.sample_chat || []
        })
      })

      if (!renderRes.ok) {
        const err = await renderRes.json()
        throw new Error(err.detail || 'Rendering failed')
      }

      const renderData = await renderRes.json()
      const clipId = renderData.clip_id
      const meta = renderData.metadata || {}

      // 2. Immediately Upload to YouTube without stopping for approval
      setClipStates(prev => ({
        ...prev,
        [momentId]: {
          ...prev[momentId],
          rendering: false,
          rendered: true,
          publishing: true,
          video_url: `http://localhost:8000${renderData.video_url}`,
          clip_id: clipId,
          metadata: meta
        }
      }))

      const uploadRes = await fetch('http://localhost:8000/api/stream-clipper/upload', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          clip_id: clipId,
          title: meta.title || moment.suggested_title || 'Live Stream Highlight #Shorts',
          description: meta.description || '',
          tags: meta.tags || ['Shorts'],
          privacy_status: autoPilotPrivacy
        })
      })

      if (!uploadRes.ok) {
        const err = await uploadRes.json()
        throw new Error(err.detail || 'Upload failed')
      }

      const uploadData = await uploadRes.json()
      setClipStates(prev => ({
        ...prev,
        [momentId]: {
          ...prev[momentId],
          publishing: false,
          published: true,
          publish_result: uploadData.result
        }
      }))
    } catch (err) {
      setClipStates(prev => ({
        ...prev,
        [momentId]: { ...prev[momentId], rendering: false, publishing: false, error: err.message }
      }))
    }
  }

  // 1-Click Batch Upload All Top Moments
  const handleBatchUploadAll = async () => {
    for (const moment of moments) {
      const state = clipStates[moment.id]
      if (!state?.published) {
        await handleDirectClipAndUpload(moment)
      }
    }
  }

  // Calculate SVG timeline points
  const maxVelocity = Math.max(...(timeline.map(t => t.velocity) || [10]), 10)
  const svgWidth = 800
  const svgHeight = 120

  const getPoints = () => {
    if (!timeline.length) return ''
    return timeline
      .map((pt, i) => {
        const x = (i / (timeline.length - 1)) * svgWidth
        const y = svgHeight - (pt.velocity / maxVelocity) * (svgHeight - 20) - 10
        return `${x},${y}`
      })
      .join(' ')
  }

  return (
    <div style={{ maxWidth: '1280px', margin: '0 auto', color: '#e4e4e7', padding: '10px 0 60px 0' }}>

      {/* Header Banner */}
      <div style={{
        background: 'linear-gradient(135deg, #18181b 0%, #1e1b4b 50%, #0f172a 100%)',
        padding: '28px 32px',
        borderRadius: '16px',
        border: '1px solid #312e81',
        marginBottom: '24px',
        boxShadow: '0 10px 30px -10px rgba(79, 70, 229, 0.2)'
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '16px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
              <span style={{ fontSize: '32px' }}>⚡</span>
              <h1 style={{ margin: 0, fontSize: '26px', fontWeight: '800', letterSpacing: '-0.5px', color: '#ffffff' }}>
                Live Stream Chat Clipper & Direct Auto-Publisher
              </h1>
              <span style={{
                fontSize: '11px',
                background: '#4f46e5',
                color: '#ffffff',
                padding: '4px 10px',
                borderRadius: '12px',
                fontWeight: '700',
                textTransform: 'uppercase',
                letterSpacing: '0.5px'
              }}>
                Auto-Pilot
              </span>
            </div>
            <p style={{ margin: 0, color: '#a1a1aa', fontSize: '15px', maxWidth: '750px', lineHeight: '1.5' }}>
              Detects where chat went crazy, clips the 9:16 vertical Short, and publishes directly to YouTube.
              <strong> Zero approval bottlenecks: paste the live stream URL and let it automatically upload the top viral moments.</strong>
            </p>
          </div>

          {/* YouTube Connection Status Pill */}
          <div style={{
            background: ytAuth?.connected ? '#064e3b' : '#27272a',
            border: ytAuth?.connected ? '1px solid #059669' : '1px solid #3f3f46',
            borderRadius: '10px',
            padding: '10px 16px',
            display: 'flex',
            alignItems: 'center',
            gap: '10px'
          }}>
            <span style={{ fontSize: '18px' }}>{ytAuth?.connected ? '✅' : '⚠️'}</span>
            <div>
              <div style={{ fontSize: '11px', color: '#a1a1aa', textTransform: 'uppercase', fontWeight: '600' }}>
                Target YouTube Channel
              </div>
              <div style={{ fontSize: '13px', fontWeight: '700', color: ytAuth?.connected ? '#a7f3d0' : '#f43f5e' }}>
                {ytAuth?.channel_title || (ytAuth?.connected ? 'Connected' : 'Not Connected')}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Input & 1-Click Auto-Upload Action */}
      <div style={{
        background: '#18181b',
        border: '1px solid #27272a',
        borderRadius: '14px',
        padding: '24px',
        marginBottom: '24px'
      }}>
        <label style={{ display: 'block', fontSize: '13px', fontWeight: '700', color: '#d4d4d8', marginBottom: '8px', textTransform: 'uppercase' }}>
          Live Stream or VOD Replay URL
        </label>

        <div style={{ display: 'flex', gap: '12px', marginBottom: '20px', flexWrap: 'wrap' }}>
          <input
            type="text"
            placeholder="Paste YouTube Live stream URL (e.g. https://www.youtube.com/watch?v=...)"
            value={streamUrl}
            onChange={(e) => setStreamUrl(e.target.value)}
            disabled={autoPilotRunning || analyzing}
            style={{
              flex: '1',
              minWidth: '320px',
              padding: '14px 18px',
              background: '#09090b',
              border: '1.5px solid #3f3f46',
              borderRadius: '10px',
              color: '#ffffff',
              fontSize: '15px',
              outline: 'none',
              transition: 'border 0.2s'
            }}
          />

          {/* PRIMARY AUTO-PILOT ACTION */}
          <button
            type="button"
            onClick={handleAutoPilotUpload}
            disabled={autoPilotRunning || analyzing || !streamUrl.trim()}
            style={{
              padding: '14px 28px',
              background: autoPilotRunning ? '#b91c1c' : 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)',
              border: 'none',
              borderRadius: '10px',
              color: '#ffffff',
              fontSize: '15px',
              fontWeight: '800',
              cursor: autoPilotRunning || analyzing ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              boxShadow: '0 4px 20px rgba(239, 68, 68, 0.4)'
            }}
          >
            {autoPilotRunning ? (
              <>
                <span className="spinner" style={{ display: 'inline-block', width: '16px', height: '16px', border: '2px solid #ffffff', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
                <span>Auto-Uploading to YouTube...</span>
              </>
            ) : (
              <>
                <span>🚀</span>
                <span>Auto-Clip & Upload Top Moments</span>
              </>
            )}
          </button>

          {/* SECONDARY: ANALYZE FIRST */}
          <button
            type="button"
            onClick={handleAnalyze}
            disabled={autoPilotRunning || analyzing || !streamUrl.trim()}
            style={{
              padding: '14px 20px',
              background: '#27272a',
              border: '1px solid #3f3f46',
              borderRadius: '10px',
              color: '#d4d4d8',
              fontSize: '14px',
              fontWeight: '600',
              cursor: autoPilotRunning || analyzing ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '8px'
            }}
          >
            <span>🔍</span>
            <span>Analyze First</span>
          </button>
        </div>

        {/* Auto-Pilot Controls */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: '16px',
          background: '#09090b',
          padding: '16px 20px',
          borderRadius: '10px',
          border: '1px solid #27272a'
        }}>
          <div>
            <label style={{ display: 'block', fontSize: '12px', color: '#a1a1aa', fontWeight: '600', marginBottom: '6px' }}>
              Auto-Upload Moments Count
            </label>
            <select
              value={autoPilotCount}
              onChange={(e) => setAutoPilotCount(e.target.value)}
              disabled={autoPilotRunning || analyzing}
              style={{
                width: '100%',
                padding: '8px 12px',
                background: '#18181b',
                color: '#ffffff',
                border: '1px solid #3f3f46',
                borderRadius: '8px',
                fontSize: '13px'
              }}
            >
              <option value="1">Top 1 Biggest Spike</option>
              <option value="3">Top 3 Viral Moments (Recommended)</option>
              <option value="5">Top 5 Moments</option>
            </select>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '12px', color: '#a1a1aa', fontWeight: '600', marginBottom: '6px' }}>
              YouTube Privacy Setting
            </label>
            <select
              value={autoPilotPrivacy}
              onChange={(e) => setAutoPilotPrivacy(e.target.value)}
              disabled={autoPilotRunning || analyzing}
              style={{
                width: '100%',
                padding: '8px 12px',
                background: '#18181b',
                color: '#ffffff',
                border: '1px solid #3f3f46',
                borderRadius: '8px',
                fontSize: '13px'
              }}
            >
              <option value="public">Public (Immediate Live Post)</option>
              <option value="unlisted">Unlisted (Shareable Link)</option>
              <option value="private">Private (Only You)</option>
            </select>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '12px', color: '#a1a1aa', fontWeight: '600', marginBottom: '6px' }}>
              Clip Duration (Shorts)
            </label>
            <select
              value={clipDuration}
              onChange={(e) => setClipDuration(e.target.value)}
              disabled={autoPilotRunning || analyzing}
              style={{
                width: '100%',
                padding: '8px 12px',
                background: '#18181b',
                color: '#ffffff',
                border: '1px solid #3f3f46',
                borderRadius: '8px',
                fontSize: '13px'
              }}
            >
              <option value="30">30 Seconds (Fast)</option>
              <option value="45">45 Seconds (Standard)</option>
              <option value="60">60 Seconds (Full Highlight)</option>
            </select>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '12px', color: '#a1a1aa', fontWeight: '600', marginBottom: '6px' }}>
              Spike Sensitivity ({spikeThreshold}x)
            </label>
            <input
              type="range"
              min="1.5"
              max="4.0"
              step="0.1"
              value={spikeThreshold}
              onChange={(e) => setSpikeThreshold(e.target.value)}
              disabled={autoPilotRunning || analyzing}
              style={{ width: '100%', accentColor: '#ef4444' }}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#71717a' }}>
              <span>More Clips (1.5x)</span>
              <span>Ultra Hype (4.0x)</span>
            </div>
          </div>
        </div>

        {/* Live Auto-Pilot Progress Banner */}
        {autoPilotProgress && (
          <div style={{
            marginTop: '16px',
            padding: '14px 18px',
            background: autoPilotCompleted ? 'rgba(16, 185, 129, 0.15)' : 'rgba(239, 68, 68, 0.15)',
            border: autoPilotCompleted ? '1px solid #10b981' : '1px solid #ef4444',
            borderRadius: '10px',
            color: autoPilotCompleted ? '#6ee7b7' : '#fca5a5',
            fontSize: '14px',
            fontWeight: '600',
            display: 'flex',
            alignItems: 'center',
            gap: '12px'
          }}>
            {autoPilotRunning && <span className="spinner" style={{ display: 'inline-block', width: '16px', height: '16px', border: '2px solid #ef4444', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />}
            <span>{autoPilotProgress}</span>
          </div>
        )}

        {errorMsg && (
          <div style={{
            marginTop: '16px',
            padding: '12px 16px',
            background: 'rgba(239, 68, 68, 0.15)',
            border: '1px solid #ef4444',
            borderRadius: '8px',
            color: '#fca5a5',
            fontSize: '14px',
            display: 'flex',
            alignItems: 'center',
            gap: '8px'
          }}>
            <span>⚠️</span>
            <span>{errorMsg}</span>
          </div>
        )}
      </div>

      {/* Stream Overview & Chat Timeline Chart */}
      {streamInfo && (
        <div style={{
          background: '#18181b',
          border: '1px solid #27272a',
          borderRadius: '14px',
          padding: '24px',
          marginBottom: '24px'
        }}>
          <div style={{ display: 'flex', gap: '20px', alignItems: 'center', marginBottom: '20px', flexWrap: 'wrap' }}>
            {streamInfo.thumbnail && (
              <img
                src={streamInfo.thumbnail}
                alt="thumbnail"
                style={{ width: '140px', height: '80px', objectFit: 'cover', borderRadius: '8px', border: '1px solid #3f3f46' }}
              />
            )}
            <div style={{ flex: 1, minWidth: '240px' }}>
              <h2 style={{ margin: '0 0 6px 0', fontSize: '18px', fontWeight: '700', color: '#ffffff' }}>
                {streamInfo.title}
              </h2>
              <div style={{ display: 'flex', gap: '16px', fontSize: '13px', color: '#a1a1aa', flexWrap: 'wrap' }}>
                <span>👤 <strong>{streamInfo.uploader}</strong></span>
                <span>⏱️ Duration: <strong>{streamInfo.duration_str}</strong></span>
                {stats && <span>💬 Total Chat: <strong>{stats.total_messages?.toLocaleString()} msgs</strong></span>}
                {stats && <span>🔥 Peak Velocity: <strong style={{ color: '#f59e0b' }}>{stats.peak_velocity_mpm} msgs/min</strong></span>}
              </div>
            </div>

            {/* Quick Batch Upload Button if not all published */}
            {moments.some(m => !clipStates[m.id]?.published) && (
              <button
                type="button"
                onClick={handleBatchUploadAll}
                style={{
                  padding: '12px 20px',
                  background: 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)',
                  border: 'none',
                  borderRadius: '8px',
                  color: '#ffffff',
                  fontWeight: '700',
                  fontSize: '13px',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px'
                }}
              >
                <span>🚀</span>
                <span>Upload All Top Moments to YouTube</span>
              </button>
            )}
          </div>

          {/* Interactive Chat Heatmap Timeline */}
          {timeline.length > 0 && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                <span style={{ fontSize: '13px', fontWeight: '700', color: '#d4d4d8', textTransform: 'uppercase' }}>
                  📊 Chat Explosion Velocity Heatmap
                </span>
                <span style={{ fontSize: '12px', color: '#a1a1aa' }}>
                  Spikes marked with <strong style={{ color: '#ef4444' }}>🔴 Flame Marker</strong>
                </span>
              </div>

              <div style={{
                background: '#09090b',
                padding: '16px',
                borderRadius: '10px',
                border: '1px solid #27272a',
                overflowX: 'auto'
              }}>
                <svg viewBox={`0 0 ${svgWidth} ${svgHeight}`} style={{ width: '100%', height: '140px', overflow: 'visible' }}>
                  <defs>
                    <linearGradient id="velocityGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                      <stop offset="0%" stopColor="#ef4444" stopOpacity="0.4" />
                      <stop offset="100%" stopColor="#4f46e5" stopOpacity="0.0" />
                    </linearGradient>
                  </defs>

                  {timeline.length > 1 && (
                    <polygon
                      points={`0,${svgHeight} ${getPoints()} ${svgWidth},${svgHeight}`}
                      fill="url(#velocityGrad)"
                    />
                  )}

                  {timeline.length > 1 && (
                    <polyline
                      fill="none"
                      stroke="#818cf8"
                      strokeWidth="2.5"
                      points={getPoints()}
                    />
                  )}

                  {timeline.map((pt, i) => {
                    if (!pt.is_peak) return null
                    const x = (i / (timeline.length - 1)) * svgWidth
                    const y = svgHeight - (pt.velocity / maxVelocity) * (svgHeight - 20) - 10
                    return (
                      <g key={i}>
                        <line x1={x} y1={y} x2={x} y2={svgHeight} stroke="#ef4444" strokeWidth="1.5" strokeDasharray="3,3" />
                        <circle cx={x} cy={y} r="5" fill="#ef4444" stroke="#ffffff" strokeWidth="2" />
                        <text x={x} y={y - 10} fill="#fca5a5" fontSize="10" fontWeight="bold" textAnchor="middle">
                          🔥 {pt.time_str}
                        </text>
                      </g>
                    )
                  })}
                </svg>

                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#71717a', marginTop: '6px' }}>
                  <span>00:00:00</span>
                  <span>Stream Progression</span>
                  <span>{streamInfo.duration_str}</span>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Top Moments Cards Gallery */}
      {moments.length > 0 && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px' }}>
            <h2 style={{ margin: 0, fontSize: '20px', fontWeight: '800', color: '#ffffff' }}>
              🎯 Top Explosion Moments ({moments.length})
            </h2>
            <span style={{ fontSize: '13px', color: '#a1a1aa' }}>
              Ranked by chat velocity spike intensity
            </span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '20px' }}>
            {moments.map((moment) => {
              const state = clipStates[moment.id] || {}
              return (
                <div
                  key={moment.id}
                  style={{
                    background: '#18181b',
                    border: state.published ? '1.5px solid #059669' : state.rendered ? '1px solid #3b82f6' : '1px solid #27272a',
                    borderRadius: '14px',
                    padding: '20px',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                    boxShadow: '0 4px 20px rgba(0,0,0,0.2)'
                  }}
                >
                  <div>
                    {/* Header badge row */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                      <span style={{
                        background: '#312e81',
                        color: '#c7d2fe',
                        padding: '4px 10px',
                        borderRadius: '6px',
                        fontSize: '12px',
                        fontWeight: '700'
                      }}>
                        #{moment.rank} MOMENT • {moment.peak_time_str}
                      </span>
                      <span style={{
                        background: 'rgba(239, 68, 68, 0.2)',
                        color: '#f87171',
                        padding: '4px 10px',
                        borderRadius: '6px',
                        fontSize: '12px',
                        fontWeight: '700'
                      }}>
                        🔥 {moment.peak_velocity} msgs/min
                      </span>
                    </div>

                    {/* Published Success Banner */}
                    {state.published && (
                      <div style={{
                        background: 'linear-gradient(135deg, rgba(5, 150, 105, 0.2) 0%, rgba(6, 78, 59, 0.3) 100%)',
                        border: '1px solid #059669',
                        borderRadius: '10px',
                        padding: '12px 14px',
                        marginBottom: '16px',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '8px'
                      }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#a7f3d0', fontWeight: '800', fontSize: '13px' }}>
                          <span>✅</span>
                          <span>LIVE ON YOUTUBE</span>
                        </div>
                        {state.publish_result?.shorts_url && (
                          <a
                            href={state.publish_result.shorts_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{
                              color: '#38bdf8',
                              fontSize: '13px',
                              fontWeight: '600',
                              textDecoration: 'none',
                              display: 'flex',
                              alignItems: 'center',
                              gap: '6px'
                            }}
                          >
                            <span>🔗 Watch Short on YouTube</span>
                            <span>↗</span>
                          </a>
                        )}
                      </div>
                    )}

                    {/* Rendered Video Player Preview */}
                    {state.rendered && state.video_url && (
                      <div style={{ marginBottom: '16px', borderRadius: '10px', overflow: 'hidden', border: '1px solid #3f3f46' }}>
                        <video
                          controls
                          src={state.video_url}
                          style={{ width: '100%', maxHeight: '300px', background: '#000000', display: 'block' }}
                        />
                      </div>
                    )}

                    {/* Title Banner */}
                    <div style={{ fontSize: '14px', fontWeight: '700', color: '#ffffff', marginBottom: '8px', lineHeight: '1.4' }}>
                      {state.metadata?.title || moment.suggested_title}
                    </div>

                    {/* Exploding Keywords Pills */}
                    {moment.top_keywords && (
                      <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginBottom: '14px' }}>
                        {(moment.top_keywords || []).map((kw, i) => (
                          <span key={i} style={{
                            background: '#27272a',
                            color: '#fcd34d',
                            padding: '3px 8px',
                            borderRadius: '6px',
                            fontSize: '11px',
                            fontWeight: '700'
                          }}>
                            {kw}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Actions Area */}
                  <div>
                    {state.error && (
                      <div style={{ fontSize: '12px', color: '#f87171', marginBottom: '10px' }}>
                        ⚠️ {state.error}
                      </div>
                    )}

                    {!state.published ? (
                      <button
                        type="button"
                        onClick={() => handleDirectClipAndUpload(moment)}
                        disabled={state.rendering || state.publishing}
                        style={{
                          width: '100%',
                          padding: '12px',
                          background: state.rendering || state.publishing
                            ? '#b45309'
                            : 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)',
                          border: 'none',
                          borderRadius: '8px',
                          color: '#ffffff',
                          fontWeight: '800',
                          fontSize: '14px',
                          cursor: state.rendering || state.publishing ? 'not-allowed' : 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          gap: '8px',
                          boxShadow: '0 4px 15px rgba(239, 68, 68, 0.3)'
                        }}
                      >
                        {state.rendering ? (
                          <>
                            <span className="spinner" style={{ display: 'inline-block', width: '14px', height: '14px', border: '2px solid #ffffff', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
                            <span>Sniping & Rendering 9:16...</span>
                          </>
                        ) : state.publishing ? (
                          <>
                            <span className="spinner" style={{ display: 'inline-block', width: '14px', height: '14px', border: '2px solid #ffffff', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
                            <span>Publishing to YouTube...</span>
                          </>
                        ) : (
                          <>
                            <span>🚀</span>
                            <span>Direct Clip & Upload to YouTube</span>
                          </>
                        )}
                      </button>
                    ) : (
                      <a
                        href={state.publish_result?.shorts_url || '#'}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{
                          display: 'block',
                          textAlign: 'center',
                          padding: '12px',
                          background: '#059669',
                          borderRadius: '8px',
                          color: '#ffffff',
                          fontWeight: '800',
                          fontSize: '14px',
                          textDecoration: 'none'
                        }}
                      >
                        ▶️ Open Short on YouTube
                      </a>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      <style>{`
        @keyframes spin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  )
}
