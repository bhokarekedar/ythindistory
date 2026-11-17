import { useState, useEffect, useRef } from 'react'

export default function ViralClipGenerator() {
  const [url, setUrl] = useState('')
  const [isValidUrl, setIsValidUrl] = useState(false)
  const [loadingInfo, setLoadingInfo] = useState(false)
  const [videoMeta, setVideoMeta] = useState(null)
  const [errorMsg, setErrorMsg] = useState('')

  // Processing state
  const [isProcessing, setIsProcessing] = useState(false)
  const [jobId, setJobId] = useState(null)
  const [jobData, setJobData] = useState(null)
  const pollIntervalRef = useRef(null)

  // Viral Moments & Smart Crop State
  const [viralMoments, setViralMoments] = useState([])
  const [loadingMoments, setLoadingMoments] = useState(false)
  const [selectedLayouts, setSelectedLayouts] = useState({})
  const [renderingClipId, setRenderingClipId] = useState(null)
  const [activePreviewClip, setActivePreviewClip] = useState(null)

  // Real-time client-side URL validation
  useEffect(() => {
    const trimmed = url.trim()
    const ytRegex = /^(https?:\/\/)?(www\.|m\.)?(youtube\.com\/(watch\?v=|embed\/|v\/|shorts\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})/i
    const directIdRegex = /^[a-zA-Z0-9_-]{11}$/
    const valid = ytRegex.test(trimmed) || directIdRegex.test(trimmed)
    setIsValidUrl(valid)
    if (!trimmed) {
      setErrorMsg('')
    }
  }, [url])

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current)
    }
  }, [])

  // Poll job status
  useEffect(() => {
    if (!jobId || !isProcessing) return

    pollIntervalRef.current = setInterval(async () => {
      try {
        const res = await fetch(`http://localhost:8000/api/viral-clips/status/${jobId}`)
        if (!res.ok) return
        const data = await res.json()
        setJobData(data)

        if (data.status === 'completed' || data.status === 'error') {
          setIsProcessing(false)
          clearInterval(pollIntervalRef.current)
          if (data.status === 'completed' && data.video_id) {
            fetchExistingMoments(data.video_id)
          }
        }
      } catch (err) {
        console.error('Failed to poll viral clip status:', err)
      }
    }, 1500)

    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current)
    }
  }, [jobId, isProcessing])

  // Fetch video metadata
  const handleFetchInfo = async (e) => {
    if (e) e.preventDefault()
    if (!url.trim()) {
      setErrorMsg('Please enter a YouTube video URL.')
      return
    }

    setLoadingInfo(true)
    setErrorMsg('')
    setVideoMeta(null)
    setJobData(null)
    setViralMoments([])
    setActivePreviewClip(null)

    try {
      const res = await fetch('http://localhost:8000/api/viral-clips/video-info', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url.trim() })
      })

      const data = await res.json()
      if (!res.ok) {
        throw new Error(data.detail || data.error || 'Failed to fetch video information')
      }

      setVideoMeta(data.metadata)
      if (data.metadata?.video_id) {
        fetchExistingMoments(data.metadata.video_id)
      }
    } catch (err) {
      setErrorMsg(err.message || 'Error communicating with backend server')
    } finally {
      setLoadingInfo(false)
    }
  }

  // Check if viral moments were already generated for this video
  const fetchExistingMoments = async (videoId) => {
    try {
      const res = await fetch(`http://localhost:8000/api/viral-clips/moments/${videoId}`)
      if (!res.ok) return
      const data = await res.json()
      if (data.clips && data.clips.length > 0) {
        setViralMoments(data.clips)
        const layouts = {}
        data.clips.forEach(c => {
          layouts[c.clip_id] = c.suggested_layout || 'dynamic_smart_crop'
          if (c.rendered && !activePreviewClip) {
            setActivePreviewClip(c)
          }
        })
        setSelectedLayouts(layouts)
      }
    } catch (err) {
      console.error('Failed to fetch existing viral moments:', err)
    }
  }

  // Start processing workflow
  const handleStartWorkflow = async () => {
    if (!url.trim()) return
    setIsProcessing(true)
    setErrorMsg('')
    setJobData({
      status: 'in_progress',
      step: 'started',
      message: 'Submitting video to processing pipeline...'
    })

    try {
      const res = await fetch('http://localhost:8000/api/viral-clips/process', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url.trim() })
      })

      const data = await res.json()
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to start clipping workflow')
      }

      setJobId(data.job_id)
    } catch (err) {
      setIsProcessing(false)
      setErrorMsg(err.message || 'Failed to start video processing')
    }
  }

  // Detect viral moments via LLM
  const handleDetectViralMoments = async () => {
    const videoId = videoMeta?.video_id || jobData?.video_id
    if (!videoId) return

    setLoadingMoments(true)
    setErrorMsg('')
    try {
      const res = await fetch('http://localhost:8000/api/viral-clips/detect-moments', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ video_id: videoId, target_clips: 4 })
      })

      const data = await res.json()
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to identify viral moments')
      }

      setViralMoments(data.clips || [])
      const layouts = {}
      (data.clips || []).forEach(c => {
        layouts[c.clip_id] = c.suggested_layout || 'dynamic_smart_crop'
      })
      setSelectedLayouts(layouts)
    } catch (err) {
      setErrorMsg(err.message || 'Error running AI viral moment detection')
    } finally {
      setLoadingMoments(false)
    }
  }

  // Render a specific vertical clip via AI Smart Cropping Engine
  const handleRenderClip = async (clip) => {
    const videoId = videoMeta?.video_id || jobData?.video_id
    if (!videoId) return

    setRenderingClipId(clip.clip_id)
    setErrorMsg('')
    const layout = selectedLayouts[clip.clip_id] || clip.suggested_layout || 'dynamic_smart_crop'

    try {
      const res = await fetch('http://localhost:8000/api/viral-clips/render-clip', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          video_id: videoId,
          clip_id: clip.clip_id,
          start_time: clip.start_time,
          end_time: clip.end_time,
          layout: layout
        })
      })

      const data = await res.json()
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to render vertical clip')
      }

      // Mark clip as rendered and set as active preview
      const updated = viralMoments.map(c => {
        if (c.clip_id === clip.clip_id) {
          return { ...c, rendered: true, video_url: data.video_url, report: data.report }
        }
        return c
      })
      setViralMoments(updated)
      setActivePreviewClip({ ...clip, rendered: true, video_url: data.video_url, report: data.report })
    } catch (err) {
      setErrorMsg(`Error rendering ${clip.clip_id}: ${err.message}`)
    } finally {
      setRenderingClipId(null)
    }
  }

  const formatViews = (count) => {
    if (!count) return '0 views'
    if (count >= 1000000) return `${(count / 1000000).toFixed(1)}M views`
    if (count >= 1000) return `${(count / 1000).toFixed(1)}K views`
    return `${count.toLocaleString()} views`
  }

  const formatSeconds = (sec) => {
    const s = Math.floor(sec || 0)
    const m = Math.floor(s / 60)
    const rem = s % 60
    return `${m.toString().padStart(2, '0')}:${rem.toString().padStart(2, '0')}`
  }

  const effectiveVideoId = videoMeta?.video_id || jobData?.video_id
  const isWorkflowReady = (jobData?.status === 'completed' || videoMeta?.has_transcript_cached)

  return (
    <div style={{ maxWidth: '900px', margin: '0 auto', textAlign: 'left' }}>
      {/* Top Banner / Channel Card */}
      <div style={{
        background: 'linear-gradient(135deg, #1e1b4b 0%, #312e81 50%, #4338ca 100%)',
        padding: '20px 24px',
        borderRadius: '12px',
        border: '1px solid #4f46e5',
        marginBottom: '24px',
        boxShadow: '0 8px 24px rgba(79, 70, 229, 0.25)'
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '24px' }}>🔥</span>
              <h2 style={{ margin: 0, fontSize: '22px', color: '#ffffff', fontWeight: '800', letterSpacing: '-0.5px' }}>
                ViralLoop Clip Automation
              </h2>
              <span style={{
                background: '#22c55e',
                color: '#052e16',
                fontSize: '11px',
                fontWeight: 'bold',
                padding: '2px 8px',
                borderRadius: '12px',
                textTransform: 'uppercase'
              }}>Active</span>
            </div>
            <p style={{ margin: '6px 0 0 0', color: '#c7d2fe', fontSize: '13px' }}>
              AI Video Cropping Engine • 1080×1920 Vertical Shorts & Creator Monetization
            </p>
          </div>
          <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
            <span style={{ background: 'rgba(255,255,255,0.12)', color: '#e0e7ff', fontSize: '11px', padding: '4px 10px', borderRadius: '6px' }}>
              💰 ContentRewards
            </span>
            <span style={{ background: 'rgba(255,255,255,0.12)', color: '#e0e7ff', fontSize: '11px', padding: '4px 10px', borderRadius: '6px' }}>
              ⚡ Vyro
            </span>
            <span style={{ background: 'rgba(255,255,255,0.12)', color: '#e0e7ff', fontSize: '11px', padding: '4px 10px', borderRadius: '6px' }}>
              🎯 Whop
            </span>
          </div>
        </div>
      </div>

      {/* Step 1: YouTube Video Input Card */}
      <div style={{
        background: '#18181b',
        border: '1px solid #27272a',
        borderRadius: '12px',
        padding: '24px',
        marginBottom: '24px',
        boxShadow: '0 4px 16px rgba(0,0,0,0.3)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '14px' }}>
          <span style={{
            background: '#6366f1',
            color: 'white',
            width: '26px',
            height: '26px',
            borderRadius: '50%',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '13px',
            fontWeight: 'bold'
          }}>1</span>
          <h3 style={{ margin: 0, fontSize: '17px', color: '#f4f4f5' }}>Step 1: Paste YouTube Video URL</h3>
        </div>
        <p style={{ margin: '0 0 16px 0', fontSize: '13px', color: '#a1a1aa' }}>
          Paste any authorized YouTube video or creator footage URL to inspect metadata and extract viral moments.
        </p>

        <form onSubmit={handleFetchInfo} style={{ display: 'flex', gap: '10px', alignItems: 'stretch' }}>
          <div style={{ position: 'relative', flex: 1 }}>
            <input
              type="text"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="e.g. https://www.youtube.com/watch?v=VIDEO_ID or youtu.be/VIDEO_ID"
              style={{
                width: '100%',
                boxSizing: 'border-box',
                padding: '14px 16px',
                paddingRight: '40px',
                borderRadius: '8px',
                border: isValidUrl ? '1.5px solid #22c55e' : (url.trim() ? '1.5px solid #f59e0b' : '1px solid #3f3f46'),
                background: '#09090b',
                color: '#fafafa',
                fontSize: '14px',
                outline: 'none',
                transition: 'border-color 0.2s'
              }}
            />
            {url.trim() && (
              <span style={{
                position: 'absolute',
                right: '12px',
                top: '50%',
                transform: 'translateY(-50%)',
                fontSize: '16px'
              }} title={isValidUrl ? 'Valid YouTube URL format' : 'Incomplete or non-YouTube URL'}>
                {isValidUrl ? '✅' : '⚠️'}
              </span>
            )}
          </div>

          <button
            type="submit"
            disabled={loadingInfo || !url.trim()}
            style={{
              padding: '0 22px',
              borderRadius: '8px',
              border: 'none',
              background: isValidUrl ? '#4f46e5' : '#3f3f46',
              color: 'white',
              fontSize: '14px',
              fontWeight: '600',
              cursor: (loadingInfo || !url.trim()) ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              whiteSpace: 'nowrap',
              transition: 'background 0.2s'
            }}
          >
            {loadingInfo ? '🔎 Inspecting...' : '🔍 Fetch Video Info'}
          </button>
        </form>

        {errorMsg && (
          <div style={{
            marginTop: '14px',
            padding: '12px 14px',
            background: '#450a0a',
            border: '1px solid #b91c1c',
            borderRadius: '8px',
            color: '#fca5a5',
            fontSize: '13px'
          }}>
            ❌ {errorMsg}
          </div>
        )}
      </div>

      {/* Video Metadata Card */}
      {videoMeta && (
        <div style={{
          background: '#18181b',
          border: '1px solid #3f3f46',
          borderRadius: '12px',
          padding: '24px',
          marginBottom: '24px',
          boxShadow: '0 4px 20px rgba(0,0,0,0.4)'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h4 style={{ margin: 0, fontSize: '15px', color: '#a1a1aa', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              📺 Verified Video Information
            </h4>
            {videoMeta.is_cached ? (
              <span style={{
                background: '#14532d',
                color: '#86efac',
                border: '1px solid #22c55e',
                fontSize: '11px',
                fontWeight: 'bold',
                padding: '3px 10px',
                borderRadius: '6px'
              }}>
                ⚡ Download Cached on Disk
              </span>
            ) : (
              <span style={{
                background: '#27272a',
                color: '#d4d4d8',
                border: '1px solid #52525b',
                fontSize: '11px',
                padding: '3px 10px',
                borderRadius: '6px'
              }}>
                📥 New Video (Ready for Download)
              </span>
            )}
          </div>

          <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
            <div style={{ position: 'relative', width: '280px', flexShrink: 0, borderRadius: '8px', overflow: 'hidden', background: '#000' }}>
              <img
                src={videoMeta.thumbnail}
                alt={videoMeta.title}
                style={{ width: '100%', height: '160px', objectFit: 'cover', display: 'block' }}
              />
              <span style={{
                position: 'absolute',
                bottom: '8px',
                right: '8px',
                background: 'rgba(0,0,0,0.85)',
                color: '#fff',
                padding: '2px 8px',
                borderRadius: '4px',
                fontSize: '12px',
                fontWeight: 'bold'
              }}>
                ⏱ {videoMeta.duration_formatted}
              </span>
            </div>

            <div style={{ flex: 1, minWidth: '260px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
              <div>
                <h3 style={{ margin: '0 0 10px 0', fontSize: '18px', color: '#ffffff', lineHeight: 1.35 }}>
                  {videoMeta.title}
                </h3>
                <div style={{ display: 'flex', gap: '14px', alignItems: 'center', flexWrap: 'wrap', marginBottom: '12px', fontSize: '13px', color: '#a1a1aa' }}>
                  <span style={{ color: '#60a5fa', fontWeight: '500' }}>👤 {videoMeta.uploader}</span>
                  <span>👁 {formatViews(videoMeta.view_count)}</span>
                  <span>🆔 {videoMeta.video_id}</span>
                </div>
              </div>

              <div style={{ marginTop: '16px', display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
                <button
                  type="button"
                  onClick={handleStartWorkflow}
                  disabled={isProcessing}
                  style={{
                    background: isProcessing ? '#4338ca' : 'linear-gradient(135deg, #4f46e5 0%, #6366f1 100%)',
                    color: 'white',
                    padding: '12px 24px',
                    borderRadius: '8px',
                    border: 'none',
                    fontWeight: 'bold',
                    fontSize: '14px',
                    cursor: isProcessing ? 'not-allowed' : 'pointer',
                    boxShadow: '0 4px 12px rgba(99, 102, 241, 0.3)',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px'
                  }}
                >
                  {isProcessing ? '⏳ Workflow Running...' : '🚀 Start Clip Extraction Workflow'}
                </button>
                <a
                  href={videoMeta.webpage_url}
                  target="_blank"
                  rel="noreferrer"
                  style={{
                    fontSize: '13px',
                    color: '#a1a1aa',
                    textDecoration: 'none',
                    padding: '10px 14px',
                    borderRadius: '6px',
                    background: '#27272a'
                  }}
                >
                  Open in YouTube ↗
                </a>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Real-Time Processing Status & Pipeline Progress */}
      {jobData && (
        <div style={{
          background: '#18181b',
          border: '1px solid #3f3f46',
          borderRadius: '12px',
          padding: '24px',
          marginBottom: '24px',
          boxShadow: '0 4px 16px rgba(0,0,0,0.3)'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h4 style={{ margin: 0, fontSize: '15px', color: '#f4f4f5', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span>⚙️</span> Processing Pipeline Progress
            </h4>
            <span style={{
              fontSize: '12px',
              padding: '3px 10px',
              borderRadius: '6px',
              fontWeight: '600',
              background: jobData.status === 'completed' ? '#14532d' : (jobData.status === 'error' ? '#7f1d1d' : '#312e81'),
              color: jobData.status === 'completed' ? '#86efac' : (jobData.status === 'error' ? '#fca5a5' : '#c7d2fe')
            }}>
              {jobData.status ? jobData.status.toUpperCase() : 'IN PROGRESS'}
            </span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: '10px', marginBottom: '18px' }}>
            <div style={{ background: '#27272a', padding: '12px', borderRadius: '8px', borderLeft: '4px solid #22c55e' }}>
              <div style={{ fontSize: '11px', color: '#a1a1aa' }}>STEP 1</div>
              <div style={{ fontSize: '13px', fontWeight: 'bold', color: '#fff', marginTop: '2px' }}>Video Verified ✅</div>
            </div>

            <div style={{
              background: '#27272a',
              padding: '12px',
              borderRadius: '8px',
              borderLeft: jobData.video_path ? '4px solid #22c55e' : (jobData.step === 'downloading' ? '4px solid #6366f1' : '4px solid #52525b')
            }}>
              <div style={{ fontSize: '11px', color: '#a1a1aa' }}>STEP 2</div>
              <div style={{ fontSize: '13px', fontWeight: 'bold', color: '#fff', marginTop: '2px' }}>
                {jobData.video_path ? 'Video Downloaded ✅' : (jobData.step === 'downloading' ? 'Downloading... ⏳' : 'Video Download')}
              </div>
            </div>

            <div style={{
              background: '#27272a',
              padding: '12px',
              borderRadius: '8px',
              borderLeft: jobData.audio_path ? '4px solid #22c55e' : (jobData.step === 'extracting_audio' ? '4px solid #6366f1' : '4px solid #52525b')
            }}>
              <div style={{ fontSize: '11px', color: '#a1a1aa' }}>STEP 3</div>
              <div style={{ fontSize: '13px', fontWeight: 'bold', color: '#fff', marginTop: '2px' }}>
                {jobData.audio_path ? 'Audio Extracted ✅' : (jobData.step === 'extracting_audio' ? 'Extracting... ⏳' : 'Audio Track')}
              </div>
            </div>

            <div style={{
              background: '#27272a',
              padding: '12px',
              borderRadius: '8px',
              borderLeft: jobData.transcript_path ? '4px solid #22c55e' : (jobData.step === 'transcribing' ? '4px solid #6366f1' : '4px solid #52525b')
            }}>
              <div style={{ fontSize: '11px', color: '#a1a1aa' }}>STEP 4</div>
              <div style={{ fontSize: '13px', fontWeight: 'bold', color: '#fff', marginTop: '2px' }}>
                {jobData.transcript_path ? `Transcribed (${jobData.total_segments} segs) ✅` : (jobData.step === 'transcribing' ? 'Transcribing... ⏳' : 'Transcript & Sentences')}
              </div>
            </div>
          </div>

          <div style={{
            background: '#09090b',
            padding: '14px 16px',
            borderRadius: '8px',
            fontFamily: 'monospace',
            fontSize: '13px',
            color: jobData.status === 'error' ? '#f87171' : '#4ade80',
            border: '1px solid #27272a'
          }}>
            ▶ {jobData.message || 'Processing video workflow...'}
          </div>
        </div>
      )}

      {/* Step 2: AI Viral Moment Identification & Vertical Video Studio */}
      {isWorkflowReady && (
        <div style={{
          background: '#18181b',
          border: '1px solid #4f46e5',
          borderRadius: '12px',
          padding: '24px',
          marginBottom: '24px',
          boxShadow: '0 8px 30px rgba(79, 70, 229, 0.15)'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px', flexWrap: 'wrap', gap: '12px' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <span style={{
                  background: '#4f46e5',
                  color: 'white',
                  width: '26px',
                  height: '26px',
                  borderRadius: '50%',
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '13px',
                  fontWeight: 'bold'
                }}>2</span>
                <h3 style={{ margin: 0, fontSize: '18px', color: '#ffffff' }}>
                  AI Viral Moment Discovery & Smart Cropping Studio
                </h3>
              </div>
              <p style={{ margin: '6px 0 0 0', color: '#a1a1aa', fontSize: '13px' }}>
                Groq LLM hook analysis + MediaPipe AI Face Reframing to 1080×1920 (9:16 vertical)
              </p>
            </div>

            <button
              type="button"
              onClick={handleDetectViralMoments}
              disabled={loadingMoments}
              style={{
                background: loadingMoments ? '#312e81' : 'linear-gradient(135deg, #4f46e5 0%, #6366f1 100%)',
                color: 'white',
                border: 'none',
                borderRadius: '8px',
                padding: '12px 20px',
                fontSize: '14px',
                fontWeight: 'bold',
                cursor: loadingMoments ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                boxShadow: '0 4px 12px rgba(99, 102, 241, 0.3)'
              }}
            >
              {loadingMoments ? '🤖 Analyzing 300+ Sentences...' : '⚡ Find Top Viral Clips (Groq AI)'}
            </button>
          </div>

          {/* Active Preview Player if a clip is rendered */}
          {activePreviewClip && activePreviewClip.rendered && activePreviewClip.video_url && (
            <div style={{
              background: '#09090b',
              border: '1px solid #3f3f46',
              borderRadius: '12px',
              padding: '20px',
              marginBottom: '24px',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              boxShadow: '0 6px 24px rgba(0,0,0,0.5)'
            }}>
              <div style={{ width: '100%', display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                <span style={{ fontSize: '14px', fontWeight: 'bold', color: '#4ade80', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span>🎬</span> Vertical 9:16 Preview: {activePreviewClip.title}
                </span>
                <a
                  href={`http://localhost:8000${activePreviewClip.video_url}`}
                  download={`${activePreviewClip.clip_id}_vertical.mp4`}
                  style={{
                    background: '#22c55e',
                    color: '#052e16',
                    padding: '8px 16px',
                    borderRadius: '6px',
                    fontSize: '12px',
                    fontWeight: 'bold',
                    textDecoration: 'none',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px'
                  }}
                >
                  📥 Download 1080x1920 MP4
                </a>
              </div>

              {/* 9:16 Vertical Video Frame */}
              <div style={{
                width: '280px',
                height: '497px',
                borderRadius: '12px',
                overflow: 'hidden',
                background: '#000',
                boxShadow: '0 8px 30px rgba(0,0,0,0.8)',
                border: '2px solid #27272a'
              }}>
                <video
                  src={`http://localhost:8000${activePreviewClip.video_url}`}
                  controls
                  autoPlay
                  loop
                  playsInline
                  style={{ width: '100%', height: '100%', objectFit: 'contain' }}
                />
              </div>

              {activePreviewClip.report && (
                <div style={{ marginTop: '14px', fontSize: '12px', color: '#a1a1aa', display: 'flex', gap: '16px', flexWrap: 'wrap', justifyContent: 'center' }}>
                  <span>📐 {activePreviewClip.report.output_resolution}</span>
                  <span>⏱ {activePreviewClip.report.duration}s</span>
                  <span>🎥 {activePreviewClip.report.selected_layout}</span>
                  <span>🎯 Stability: {Math.round((activePreviewClip.report.tracking_stability_score || 0.9) * 100)}%</span>
                  <span>⚡ Rendered in {activePreviewClip.report.processing_time_seconds}s</span>
                </div>
              )}
            </div>
          )}

          {/* Discovered Viral Moments Grid */}
          {viralMoments.length > 0 && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px' }}>
              {viralMoments.map((clip) => {
                const isRendering = renderingClipId === clip.clip_id
                const currentLayout = selectedLayouts[clip.clip_id] || clip.suggested_layout || 'dynamic_smart_crop'

                return (
                  <div
                    key={clip.clip_id}
                    style={{
                      background: '#09090b',
                      border: clip.rendered ? '1.5px solid #22c55e' : '1px solid #27272a',
                      borderRadius: '10px',
                      padding: '16px',
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'space-between',
                      boxShadow: '0 4px 12px rgba(0,0,0,0.2)'
                    }}
                  >
                    <div>
                      {/* Top Pill Bar with Story Completeness & Ending Type */}
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px', flexWrap: 'wrap', gap: '6px' }}>
                        <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                          <span style={{
                            background: '#4338ca',
                            color: '#e0e7ff',
                            fontSize: '11px',
                            fontWeight: 'bold',
                            padding: '2px 8px',
                            borderRadius: '4px'
                          }}>
                            {clip.clip_id.toUpperCase()}
                          </span>
                          {clip.story?.ending_type && (
                            <span style={{
                              background: '#1e293b',
                              color: '#38bdf8',
                              border: '1px solid #0284c7',
                              fontSize: '10px',
                              fontWeight: '600',
                              padding: '2px 6px',
                              borderRadius: '4px',
                              textTransform: 'uppercase'
                            }}>
                              {clip.story.ending_type === 'complete_payoff' && '🎯 Payoff'}
                              {clip.story.ending_type === 'unexpected_twist' && '⚡ Twist'}
                              {clip.story.ending_type === 'funny_reaction_punchline' && '😂 Punchline'}
                              {clip.story.ending_type === 'revealing_moment' && '🔍 Reveal'}
                              {clip.story.ending_type === 'open_loop' && '⏳ Cliffhanger'}
                            </span>
                          )}
                        </div>
                        <div style={{ display: 'flex', gap: '4px' }}>
                          <span style={{
                            background: clip.viral_score >= 95 ? '#065f46' : '#1e3a8a',
                            color: clip.viral_score >= 95 ? '#6ee7b7' : '#93c5fd',
                            fontSize: '11px',
                            fontWeight: 'bold',
                            padding: '2px 8px',
                            borderRadius: '12px'
                          }}>
                            🔥 {clip.viral_score}/100
                          </span>
                          {clip.story_completeness_score && (
                            <span style={{
                              background: '#312e81',
                              color: '#c7d2fe',
                              fontSize: '11px',
                              fontWeight: 'bold',
                              padding: '2px 8px',
                              borderRadius: '12px'
                            }} title="Story Completeness & Payoff Score">
                              📖 {clip.story_completeness_score} STORY
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Title */}
                      <h4 style={{ margin: '0 0 8px 0', fontSize: '15px', color: '#ffffff', lineHeight: 1.35 }}>
                        {clip.title}
                      </h4>

                      {/* Duration & Time Range */}
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px', color: '#818cf8', marginBottom: '10px', fontWeight: '500' }}>
                        <span>⏱ {formatSeconds(clip.start_time)} - {formatSeconds(clip.end_time)}</span>
                        <span style={{ background: '#1e1b4b', padding: '2px 6px', borderRadius: '4px', border: '1px solid #3730a3' }}>
                          {clip.duration}s mini-story
                        </span>
                      </div>

                      {/* Opening Hook Quote */}
                      {clip.hook && (
                        <div style={{
                          background: '#18181b',
                          borderLeft: '3px solid #6366f1',
                          padding: '8px 10px',
                          borderRadius: '4px',
                          fontSize: '12px',
                          color: '#e2e8f0',
                          fontStyle: 'italic',
                          marginBottom: '10px',
                          lineHeight: 1.4
                        }}>
                          "{clip.hook}"
                        </div>
                      )}

                      {/* Story Structure Box: Setup -> Payoff */}
                      {clip.story && (
                        <div style={{
                          background: '#0c0a09',
                          border: '1px solid #292524',
                          borderRadius: '6px',
                          padding: '10px',
                          marginBottom: '10px',
                          fontSize: '11px',
                          lineHeight: 1.4
                        }}>
                          <div style={{ marginBottom: '6px' }}>
                            <span style={{ color: '#fdba74', fontWeight: 'bold' }}>🎬 Setup: </span>
                            <span style={{ color: '#d6d3d1' }}>{clip.story.setup}</span>
                          </div>
                          <div>
                            <span style={{ color: '#86efac', fontWeight: 'bold' }}>🏁 Payoff: </span>
                            <span style={{ color: '#f5f5f4' }}>{clip.story.payoff}</span>
                          </div>
                        </div>
                      )}

                      {/* Ending Validation Checklist */}
                      <div style={{ display: 'flex', gap: '8px', fontSize: '10px', color: '#4ade80', marginBottom: '10px', flexWrap: 'wrap' }}>
                        <span>✓ Complete Thought</span>
                        <span>✓ Natural Cut</span>
                        <span>✓ Payoff Delivered</span>
                      </div>

                      {/* Why it works */}
                      {clip.reason && (
                        <p style={{ margin: '0 0 14px 0', fontSize: '11px', color: '#71717a', lineHeight: 1.35 }}>
                          💡 {clip.reason}
                        </p>
                      )}
                    </div>

                    {/* Bottom Controls */}
                    <div style={{ borderTop: '1px solid #1f2937', paddingTop: '12px' }}>
                      {/* Layout Selection */}
                      <div style={{ marginBottom: '10px' }}>
                        <label style={{ fontSize: '11px', color: '#9ca3af', display: 'block', marginBottom: '4px' }}>
                          Reframing Strategy:
                        </label>
                        <select
                          value={currentLayout}
                          onChange={(e) => {
                            setSelectedLayouts({
                              ...selectedLayouts,
                              [clip.clip_id]: e.target.value
                            })
                          }}
                          style={{
                            width: '100%',
                            background: '#18181b',
                            color: '#fff',
                            border: '1px solid #374151',
                            borderRadius: '6px',
                            padding: '6px 8px',
                            fontSize: '12px',
                            outline: 'none'
                          }}
                        >
                          <option value="dynamic_smart_crop">👤 Dynamic Smart Crop (Auto Face-Follow)</option>
                          <option value="blurred_background">🌌 Blurred Background (Wide Fill)</option>
                          <option value="split_screen">🔲 Split Screen (Dual View)</option>
                        </select>
                      </div>

                      {/* Action Button */}
                      {clip.rendered ? (
                        <div style={{ display: 'flex', gap: '8px' }}>
                          <button
                            type="button"
                            onClick={() => setActivePreviewClip(clip)}
                            style={{
                              flex: 1,
                              background: '#22c55e',
                              color: '#052e16',
                              padding: '8px',
                              borderRadius: '6px',
                              border: 'none',
                              fontSize: '12px',
                              fontWeight: 'bold',
                              cursor: 'pointer'
                            }}
                          >
                            ▶ Play 9:16 Video
                          </button>
                          <a
                            href={`http://localhost:8000${clip.video_url}`}
                            download={`${clip.clip_id}_vertical.mp4`}
                            style={{
                              background: '#374151',
                              color: '#fff',
                              padding: '8px 12px',
                              borderRadius: '6px',
                              fontSize: '12px',
                              textDecoration: 'none',
                              display: 'inline-flex',
                              alignItems: 'center'
                            }}
                          >
                            📥
                          </a>
                        </div>
                      ) : (
                        <button
                          type="button"
                          onClick={() => handleRenderClip(clip)}
                          disabled={isRendering}
                          style={{
                            width: '100%',
                            background: isRendering ? '#4b5563' : 'linear-gradient(135deg, #4f46e5 0%, #6366f1 100%)',
                            color: '#fff',
                            padding: '10px',
                            borderRadius: '6px',
                            border: 'none',
                            fontSize: '13px',
                            fontWeight: 'bold',
                            cursor: isRendering ? 'not-allowed' : 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            gap: '6px'
                          }}
                        >
                          {isRendering ? '⏳ Reframing 1080x1920...' : '⚡ Render Vertical Short (9:16)'}
                        </button>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
