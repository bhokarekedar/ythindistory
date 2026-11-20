import { useState, useEffect } from 'react'

export default function LiveStreamClipper() {
  const [streamUrl, setStreamUrl] = useState('')
  const [spikeThreshold, setSpikeThreshold] = useState(2.0)
  const [maxClips, setMaxClips] = useState(6)
  const [clipDuration, setClipDuration] = useState(45)
  const [layoutMode, setLayoutMode] = useState('blurred_stack')

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

  const handleAnalyze = async () => {
    if (!streamUrl.trim()) {
      setErrorMsg('Please enter a livestream or VOD URL')
      return
    }
    setErrorMsg('')
    setAnalyzing(true)
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

      // Initialize clip states
      const initial = {}
      ;(data.moments || []).forEach(m => {
        initial[m.id] = {
          rendering: false,
          rendered: false,
          video_url: null,
          metadata: {
            title: m.suggested_title,
            description: `Live chat went crazy during ${data.stream_info?.uploader || 'the stream'}! \n\n#Shorts #LiveStream #Highlights`,
            tags: ['Shorts', 'StreamHighlights', ...(m.top_keywords || [])],
            privacy: 'unlisted'
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

  const handleRenderClip = async (moment) => {
    const momentId = moment.id
    setClipStates(prev => ({
      ...prev,
      [momentId]: { ...prev[momentId], rendering: true, error: null }
    }))

    try {
      const res = await fetch('http://localhost:8000/api/stream-clipper/render-clip', {
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

      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Rendering failed')
      }

      const data = await res.json()
      setClipStates(prev => ({
        ...prev,
        [momentId]: {
          ...prev[momentId],
          rendering: false,
          rendered: true,
          video_url: `http://localhost:8000${data.video_url}`,
          clip_id: data.clip_id,
          metadata: {
            ...prev[momentId]?.metadata,
            ...(data.metadata || {})
          }
        }
      }))
    } catch (err) {
      setClipStates(prev => ({
        ...prev,
        [momentId]: { ...prev[momentId], rendering: false, error: err.message }
      }))
    }
  }

  const handlePublishYouTube = async (momentId) => {
    const state = clipStates[momentId]
    if (!state || !state.rendered) return

    setClipStates(prev => ({
      ...prev,
      [momentId]: { ...prev[momentId], publishing: true, error: null }
    }))

    try {
      const res = await fetch('http://localhost:8000/api/stream-clipper/upload', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          clip_id: state.clip_id,
          title: state.metadata?.title || 'Stream Highlight #Shorts',
          description: state.metadata?.description || '',
          tags: state.metadata?.tags || ['Shorts'],
          privacy_status: state.metadata?.privacy || 'unlisted'
        })
      })

      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Publishing failed')
      }

      const data = await res.json()
      setClipStates(prev => ({
        ...prev,
        [momentId]: {
          ...prev[momentId],
          publishing: false,
          published: true,
          publish_result: data.result
        }
      }))
    } catch (err) {
      setClipStates(prev => ({
        ...prev,
        [momentId]: { ...prev[momentId], publishing: false, error: err.message }
      }))
    }
  }

  const updateMetadata = (momentId, field, val) => {
    setClipStates(prev => ({
      ...prev,
      [momentId]: {
        ...prev[momentId],
        metadata: {
          ...prev[momentId]?.metadata,
          [field]: val
        }
      }
    }))
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
                Live Stream Chat Clipper
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
                Spike Sniper
              </span>
            </div>
            <p style={{ margin: 0, color: '#a1a1aa', fontSize: '15px', maxWidth: '750px', lineHeight: '1.5' }}>
              Snipes moments when live chat exploded with messages, laughs, superchats, and hype. 
              Zero manual scrubbing: isolates peak moments, generates vertical 9:16 Shorts, and publishes directly to YouTube.
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
                YouTube Channel
              </div>
              <div style={{ fontSize: '13px', fontWeight: '700', color: ytAuth?.connected ? '#a7f3d0' : '#f43f5e' }}>
                {ytAuth?.channel_title || (ytAuth?.connected ? 'Connected' : 'Not Connected')}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Input & Configuration Card */}
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
            disabled={analyzing}
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
          <button
            type="button"
            onClick={handleAnalyze}
            disabled={analyzing || !streamUrl.trim()}
            style={{
              padding: '14px 28px',
              background: analyzing ? '#4338ca' : 'linear-gradient(135deg, #4f46e5 0%, #6366f1 100%)',
              border: 'none',
              borderRadius: '10px',
              color: '#ffffff',
              fontSize: '15px',
              fontWeight: '700',
              cursor: analyzing ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              boxShadow: '0 4px 15px rgba(79, 70, 229, 0.3)'
            }}
          >
            {analyzing ? (
              <>
                <span className="spinner" style={{ display: 'inline-block', width: '16px', height: '16px', border: '2px solid #ffffff', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
                <span>Scanning Chat Spikes...</span>
              </>
            ) : (
              <>
                <span>🔥</span>
                <span>Analyze Chat Explosions</span>
              </>
            )}
          </button>
        </div>

        {/* Sensitivity & Clip Controls */}
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
              Spike Sensitivity Threshold ({spikeThreshold}x)
            </label>
            <input
              type="range"
              min="1.5"
              max="4.0"
              step="0.1"
              value={spikeThreshold}
              onChange={(e) => setSpikeThreshold(e.target.value)}
              disabled={analyzing}
              style={{ width: '100%', accentColor: '#6366f1' }}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#71717a' }}>
              <span>More Clips (1.5x)</span>
              <span>Hype Spikes Only (4.0x)</span>
            </div>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '12px', color: '#a1a1aa', fontWeight: '600', marginBottom: '6px' }}>
              Max Highlights
            </label>
            <select
              value={maxClips}
              onChange={(e) => setMaxClips(e.target.value)}
              disabled={analyzing}
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
              <option value="3">Top 3 Moments</option>
              <option value="6">Top 6 Moments</option>
              <option value="10">Top 10 Moments</option>
            </select>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '12px', color: '#a1a1aa', fontWeight: '600', marginBottom: '6px' }}>
              Clip Duration
            </label>
            <select
              value={clipDuration}
              onChange={(e) => setClipDuration(e.target.value)}
              disabled={analyzing}
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
              <option value="30">30 Seconds (Fast Short)</option>
              <option value="45">45 Seconds (Recommended)</option>
              <option value="60">60 Seconds (Full Context)</option>
            </select>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '12px', color: '#a1a1aa', fontWeight: '600', marginBottom: '6px' }}>
              Video Layout (9:16 Shorts)
            </label>
            <select
              value={layoutMode}
              onChange={(e) => setLayoutMode(e.target.value)}
              disabled={analyzing}
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
              <option value="blurred_stack">Blurred Ambient Stack (Recommended)</option>
              <option value="center_crop">Center Crop 9:16</option>
            </select>
          </div>
        </div>

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
          {/* Metadata banner */}
          <div style={{ display: 'flex', gap: '20px', alignItems: 'center', marginBottom: '24px', flexWrap: 'wrap' }}>
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
              <div style={{ display: 'flex', gap: '16px', fontSize: '13px', color: '#a1a1aa' }}>
                <span>👤 <strong>{streamInfo.uploader}</strong></span>
                <span>⏱️ Duration: <strong>{streamInfo.duration_str}</strong></span>
                {stats && <span>💬 Total Chat: <strong>{stats.total_messages?.toLocaleString()} msgs</strong></span>}
                {stats && <span>🔥 Peak Velocity: <strong style={{ color: '#f59e0b' }}>{stats.peak_velocity_mpm} msgs/min</strong></span>}
              </div>
            </div>
          </div>

          {/* Interactive Chat Heatmap Timeline */}
          {timeline.length > 0 && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                <span style={{ fontSize: '13px', fontWeight: '700', color: '#d4d4d8', textTransform: 'uppercase' }}>
                  📊 Chat Explosion Velocity Graph (Messages / Minute)
                </span>
                <span style={{ fontSize: '12px', color: '#a1a1aa' }}>
                  Peaks marked with <strong style={{ color: '#ef4444' }}>🔴 Flame Marker</strong>
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

                  {/* Gradient Area */}
                  {timeline.length > 1 && (
                    <polygon
                      points={`0,${svgHeight} ${getPoints()} ${svgWidth},${svgHeight}`}
                      fill="url(#velocityGrad)"
                    />
                  )}

                  {/* Line Chart */}
                  {timeline.length > 1 && (
                    <polyline
                      fill="none"
                      stroke="#818cf8"
                      strokeWidth="2.5"
                      points={getPoints()}
                    />
                  )}

                  {/* Peak Marker Points */}
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

      {/* Detected Moments Grid */}
      {moments.length > 0 && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px' }}>
            <h2 style={{ margin: 0, fontSize: '20px', fontWeight: '800', color: '#ffffff' }}>
              🎯 Detected Chat Explosions ({moments.length})
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
                    border: state.rendered ? '1px solid #10b981' : '1px solid #27272a',
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
                        🔥 {moment.peak_velocity} msgs/min ({moment.spike_ratio}x spike)
                      </span>
                    </div>

                    <div style={{ fontSize: '13px', color: '#a1a1aa', marginBottom: '12px' }}>
                      Clip Window: <strong>{moment.start_time_str}</strong> to <strong>{moment.end_time_str}</strong> ({moment.duration}s)
                    </div>

                    {/* Exploding Keywords Pills */}
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

                    {/* Chat quotes preview ticker */}
                    <div style={{
                      background: '#09090b',
                      borderRadius: '8px',
                      padding: '10px 12px',
                      marginBottom: '16px',
                      border: '1px solid #27272a'
                    }}>
                      <div style={{ fontSize: '11px', color: '#71717a', textTransform: 'uppercase', marginBottom: '4px', fontWeight: '700' }}>
                        💬 Chat Reaction At This Moment:
                      </div>
                      {(moment.sample_chat || []).slice(0, 3).map((chat, idx) => (
                        <div key={idx} style={{ fontSize: '12px', color: '#d4d4d8', marginBottom: '2px', fontStyle: 'italic' }}>
                          "{chat}"
                        </div>
                      ))}
                    </div>

                    {/* Rendered Video Player Preview */}
                    {state.rendered && state.video_url && (
                      <div style={{ marginBottom: '16px', borderRadius: '10px', overflow: 'hidden', border: '1px solid #3f3f46' }}>
                        <video
                          controls
                          src={state.video_url}
                          style={{ width: '100%', maxHeight: '320px', background: '#000000', display: 'block' }}
                        />
                      </div>
                    )}

                    {/* Editable Title for YouTube Shorts */}
                    <div style={{ marginBottom: '12px' }}>
                      <label style={{ display: 'block', fontSize: '11px', color: '#a1a1aa', fontWeight: '600', marginBottom: '4px' }}>
                        YouTube Shorts Title
                      </label>
                      <input
                        type="text"
                        value={state.metadata?.title || ''}
                        onChange={(e) => updateMetadata(moment.id, 'title', e.target.value)}
                        style={{
                          width: '100%',
                          padding: '8px 12px',
                          background: '#09090b',
                          border: '1px solid #3f3f46',
                          borderRadius: '6px',
                          color: '#ffffff',
                          fontSize: '13px',
                          boxSizing: 'border-box'
                        }}
                      />
                    </div>
                  </div>

                  {/* Actions Area */}
                  <div>
                    {state.error && (
                      <div style={{ fontSize: '12px', color: '#f87171', marginBottom: '10px' }}>
                        ⚠️ {state.error}
                      </div>
                    )}

                    {!state.rendered ? (
                      <button
                        type="button"
                        onClick={() => handleRenderClip(moment)}
                        disabled={state.rendering}
                        style={{
                          width: '100%',
                          padding: '12px',
                          background: state.rendering ? '#4338ca' : 'linear-gradient(135deg, #4f46e5 0%, #6366f1 100%)',
                          border: 'none',
                          borderRadius: '8px',
                          color: '#ffffff',
                          fontWeight: '700',
                          fontSize: '14px',
                          cursor: state.rendering ? 'not-allowed' : 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          gap: '8px'
                        }}
                      >
                        {state.rendering ? (
                          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                              <span className="spinner" style={{ display: 'inline-block', width: '14px', height: '14px', border: '2px solid #ffffff', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
                              <span>Sniping & Rendering (~15-20s)...</span>
                            </div>
                            <span style={{ fontSize: '11px', color: '#c7d2fe', fontWeight: '400' }}>
                              Extracting live chunks & encoding 9:16 vertical short
                            </span>
                          </div>
                        ) : (
                          <>
                            <span>⚡</span>
                            <span>Generate 9:16 Short</span>
                          </>
                        )}
                      </button>
                    ) : (
                      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                        <select
                          value={state.metadata?.privacy || 'unlisted'}
                          onChange={(e) => updateMetadata(moment.id, 'privacy', e.target.value)}
                          disabled={state.publishing || state.published}
                          style={{
                            padding: '10px 12px',
                            background: '#09090b',
                            border: '1px solid #3f3f46',
                            borderRadius: '8px',
                            color: '#ffffff',
                            fontSize: '13px'
                          }}
                        >
                          <option value="unlisted">Unlisted</option>
                          <option value="public">Public</option>
                          <option value="private">Private</option>
                        </select>

                        <button
                          type="button"
                          onClick={() => handlePublishYouTube(moment.id)}
                          disabled={state.publishing || state.published}
                          style={{
                            flex: 1,
                            padding: '10px 16px',
                            background: state.published
                              ? '#059669'
                              : state.publishing
                              ? '#b45309'
                              : 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)',
                            border: 'none',
                            borderRadius: '8px',
                            color: '#ffffff',
                            fontWeight: '700',
                            fontSize: '13px',
                            cursor: state.publishing || state.published ? 'default' : 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            gap: '6px'
                          }}
                        >
                          {state.published ? (
                            <>
                              <span>✅</span>
                              <span>Published to YouTube</span>
                            </>
                          ) : state.publishing ? (
                            <>
                              <span className="spinner" style={{ display: 'inline-block', width: '12px', height: '12px', border: '2px solid #ffffff', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
                              <span>Uploading...</span>
                            </>
                          ) : (
                            <>
                              <span>🚀</span>
                              <span>Approve & Upload to YouTube</span>
                            </>
                          )}
                        </button>
                      </div>
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

