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
    } catch (err) {
      setErrorMsg(err.message || 'Error communicating with backend server')
    } finally {
      setLoadingInfo(false)
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

  const formatViews = (count) => {
    if (!count) return '0 views'
    if (count >= 1000000) return `${(count / 1000000).toFixed(1)}M views`
    if (count >= 1000) return `${(count / 1000).toFixed(1)}K views`
    return `${count.toLocaleString()} views`
  }

  return (
    <div style={{ maxWidth: '850px', margin: '0 auto', textAlign: 'left' }}>
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
              Automated high-engagement short-form video extraction for YouTube Shorts & Creator Monetization
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
          boxShadow: '0 4px 20px rgba(0,0,0,0.4)',
          animation: 'fadeIn 0.3s ease'
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
            {/* Thumbnail Preview */}
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
                fontWeight: 'bold',
                letterSpacing: '0.5px'
              }}>
                ⏱ {videoMeta.duration_formatted}
              </span>
            </div>

            {/* Video Details */}
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
                {videoMeta.description && (
                  <p style={{
                    margin: '0',
                    fontSize: '12px',
                    color: '#71717a',
                    lineHeight: '1.4',
                    maxHeight: '48px',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis'
                  }}>
                    {videoMeta.description}
                  </p>
                )}
              </div>

              {/* Action Button */}
              <div style={{ marginTop: '16px', display: 'flex', gap: '10px', alignItems: 'center' }}>
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
                    transition: 'all 0.2s',
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

          {/* Stepper Display */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: '10px', marginBottom: '18px' }}>
            <div style={{
              background: '#27272a',
              padding: '12px',
              borderRadius: '8px',
              borderLeft: '4px solid #22c55e'
            }}>
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

          {/* Status Message Box */}
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

          {jobData.status === 'completed' && (
            <div style={{
              marginTop: '16px',
              padding: '14px 16px',
              background: '#052e16',
              border: '1px solid #16a34a',
              borderRadius: '8px',
              color: '#bbf7d0',
              fontSize: '13px'
            }}>
              ✨ <strong>Step 1 & Foundation Complete!</strong> Video is cached and dialogue is parsed into {jobData.total_segments} timestamped sentence units. Ready for viral moment identification!
            </div>
          )}
        </div>
      )}
    </div>
  )
}

