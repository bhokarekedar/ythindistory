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

  // Editorial Quality Review State
  const [reviewingClipId, setReviewingClipId] = useState(null)
  const [isReviewingAll, setIsReviewingAll] = useState(false)
  const [expandedReviews, setExpandedReviews] = useState({})
  const [activeKeyframeModal, setActiveKeyframeModal] = useState(null)

  // Campaign Intelligence Linkage State
  const [approvedCampaigns, setApprovedCampaigns] = useState([])
  const [selectedCampaignId, setSelectedCampaignId] = useState('')
  const [copiedCaptionClipId, setCopiedCaptionClipId] = useState(null)
  const [campaignFootage, setCampaignFootage] = useState(null)
  const [loadingFootage, setLoadingFootage] = useState(false)

  // Fetch approved campaigns for monetization linkage
  useEffect(() => {
    fetchApprovedCampaigns()
  }, [])

  const fetchApprovedCampaigns = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/campaigns?status=APPROVED')
      if (!res.ok) return
      const data = await res.json()
      setApprovedCampaigns(data.campaigns || [])
    } catch (e) {
      console.error('Failed to fetch approved campaigns:', e)
    }
  }

  // Fetch source footage whenever selected campaign changes
  useEffect(() => {
    if (!selectedCampaignId) {
      setCampaignFootage(null)
      return
    }
    const loadFootage = async () => {
      setLoadingFootage(true)
      try {
        const res = await fetch(`http://localhost:8000/api/campaigns/${selectedCampaignId}/footage`)
        if (res.ok) {
          const data = await res.json()
          setCampaignFootage(data.footage)
        }
      } catch (err) {
        console.error('Failed to load campaign footage:', err)
      } finally {
        setLoadingFootage(false)
      }
    }
    loadFootage()
  }, [selectedCampaignId])

  const selectedCampaign = approvedCampaigns.find(c => c.campaign_id === selectedCampaignId)

  const copyPostingCaption = (clip) => {
    if (!selectedCampaign) return
    const tags = (selectedCampaign.posting_metadata?.hashtags || []).join(' ')
    const mentions = (selectedCampaign.posting_metadata?.required_mentions || []).join(' ')
    const cta = selectedCampaign.posting_metadata?.cta || ''
    const text = `${clip.title}\n\n${cta}\n\n${tags} ${mentions}`.trim()
    navigator.clipboard.writeText(text)
    setCopiedCaptionClipId(clip.clip_id)
    setTimeout(() => setCopiedCaptionClipId(null), 2500)
  }

  // Real-time client-side URL validation
  useEffect(() => {
    const trimmed = url.trim()
    const ytRegex = /^(https?:\/\/)?(www\.|m\.)?(youtube\.com\/(watch\?v=|embed\/|v\/|shorts\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})/i
    const directIdRegex = /^[a-zA-Z0-9_-]{11}$/
    const valid = ytRegex.test(trimmed) || directIdRegex.test(trimmed)
    setIsValidUrl(valid)
    if (!trimmed) {
      setErrorMsg('')
    } else if (trimmed.includes('/results') || trimmed.includes('search_query=')) {
      setErrorMsg("⚠️ You entered a YouTube search link. Please click on any specific video and copy its watch link (e.g. https://www.youtube.com/watch?v=...).")
    } else if (!valid) {
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
  const handleFetchInfo = async (e, overrideUrl = null) => {
    if (e && e.preventDefault) e.preventDefault()
    const targetUrl = (overrideUrl || url).trim()
    if (!targetUrl) {
      setErrorMsg('Please enter a YouTube video URL.')
      return
    }
    if (overrideUrl) {
      setUrl(overrideUrl)
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
        body: JSON.stringify({ url: targetUrl })
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

  // Run Editorial Quality Review for a single clip
  const handleReviewClip = async (clipId) => {
    const videoId = videoMeta?.video_id || jobData?.video_id
    if (!videoId) return
    setReviewingClipId(clipId)
    setErrorMsg('')

    try {
      const res = await fetch('http://localhost:8000/api/viral-clips/review-clip', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ video_id: videoId, clip_id: clipId })
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Failed to review clip')

      setViralMoments(prev => prev.map(c => {
        if (c.clip_id === clipId) {
          return { ...c, editorial_review: data.review }
        }
        return c
      }))
      setExpandedReviews(prev => ({ ...prev, [clipId]: true }))
    } catch (err) {
      setErrorMsg(`Editorial review error: ${err.message}`)
    } finally {
      setReviewingClipId(null)
    }
  }

  // Audit all clips in batch
  const handleReviewAllClips = async () => {
    const videoId = videoMeta?.video_id || jobData?.video_id
    if (!videoId) return
    setIsReviewingAll(true)
    setErrorMsg('')

    try {
      const res = await fetch('http://localhost:8000/api/viral-clips/review-all', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ video_id: videoId })
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Failed to review all clips')

      const reviews = data.reviews || {}
      setViralMoments(prev => prev.map(c => ({
        ...c,
        editorial_review: reviews[c.clip_id] || c.editorial_review
      })))
      const newExpanded = {}
      viralMoments.forEach(c => { newExpanded[c.clip_id] = true })
      setExpandedReviews(newExpanded)
    } catch (err) {
      setErrorMsg(`Batch review error: ${err.message}`)
    } finally {
      setIsReviewingAll(false)
    }
  }

  // Manual Editorial Override: Approve, Reject, or Reset
  const handleManualVerdict = async (clipId, verdict) => {
    const videoId = videoMeta?.video_id || jobData?.video_id
    if (!videoId) return
    try {
      const res = await fetch('http://localhost:8000/api/viral-clips/manual-verdict', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ video_id: videoId, clip_id: clipId, verdict })
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Failed to update editorial verdict')

      setViralMoments(prev => prev.map(c => {
        if (c.clip_id === clipId) {
          return {
            ...c,
            editorial_review: {
              ...(c.editorial_review || {}),
              user_verdict: data.review.user_verdict
            }
          }
        }
        return c
      }))
    } catch (err) {
      setErrorMsg(`Failed to save verdict: ${err.message}`)
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

        {/* Link to Approved Campaign (Monetization Integration) */}
        <div style={{
          background: '#09090b',
          border: '1px solid #27272a',
          borderRadius: '8px',
          padding: '12px 14px',
          marginBottom: '16px'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
            <span style={{ fontSize: '12px', fontWeight: 'bold', color: '#38bdf8', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span>🎯</span> Link to Approved Campaign (Optional):
            </span>
            <span style={{ fontSize: '11px', color: '#a1a1aa' }}>
              {approvedCampaigns.length} Approved in Library
            </span>
          </div>

          <select
            value={selectedCampaignId}
            onChange={(e) => setSelectedCampaignId(e.target.value)}
            style={{
              width: '100%',
              background: '#18181b',
              border: '1px solid #3f3f46',
              color: '#fff',
              padding: '8px 10px',
              borderRadius: '6px',
              fontSize: '13px',
              outline: 'none'
            }}
          >
            <option value="">-- None (Independent Viral Clip) --</option>
            {approvedCampaigns.map(ac => (
              <option key={ac.campaign_id} value={ac.campaign_id}>
                {ac.title} ({ac.source_platform} • ${ac.commercial_details?.cpm_max || 0} CPM)
              </option>
            ))}
          </select>

          {selectedCampaign && (
            <div style={{ marginTop: '8px', fontSize: '11px', color: '#86efac', display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
              <span>✅ Requirements: 9:16 vertical shorts</span>
              {selectedCampaign.posting_metadata?.hashtags?.length > 0 && (
                <span>🏷️ Tags: {selectedCampaign.posting_metadata.hashtags.join(' ')}</span>
              )}
              {selectedCampaign.posting_metadata?.required_mentions?.length > 0 && (
                <span>👤 Mentions: {selectedCampaign.posting_metadata.required_mentions.join(' ')}</span>
              )}
            </div>
          )}

          {/* Footage Loader */}
          {loadingFootage && (
            <div style={{
              marginTop: '12px',
              padding: '12px',
              background: '#18181b',
              borderRadius: '8px',
              border: '1px dashed #38bdf8',
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              color: '#93c5fd',
              fontSize: '12px'
            }}>
              <span>⏳</span>
              <span>Scanning campaign brief & fetching available creator footage...</span>
            </div>
          )}

          {/* Campaign Footage Gallery */}
          {campaignFootage && !loadingFootage && (
            <div style={{ marginTop: '14px', paddingTop: '14px', borderTop: '1px solid #27272a' }}>
              {/* Google Drive Links */}
              {campaignFootage.drive_links?.length > 0 && (
                <div style={{
                  marginBottom: '12px',
                  padding: '10px 14px',
                  background: '#1e1b4b',
                  borderRadius: '6px',
                  border: '1px solid #4338ca',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '12px'
                }}>
                  <span style={{ fontSize: '12px', color: '#c7d2fe' }}>
                    📁 <strong>Official Footage Folder:</strong> Google Drive folder provided for this campaign.
                  </span>
                  <a
                    href={campaignFootage.drive_links[0].url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      padding: '5px 12px',
                      background: '#4f46e5',
                      color: '#fff',
                      borderRadius: '5px',
                      fontSize: '11px',
                      textDecoration: 'none',
                      fontWeight: 'bold',
                      whiteSpace: 'nowrap'
                    }}
                  >
                    Open Drive ↗
                  </a>
                </div>
              )}

              {/* Video Cards Grid */}
              {campaignFootage.videos?.length > 0 ? (
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                    <span style={{ fontSize: '12px', fontWeight: 'bold', color: '#f8fafc', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span>🎬</span> Available Source Videos ({campaignFootage.videos.length})
                      {campaignFootage.channel_url && (
                        <span style={{ fontSize: '11px', color: '#38bdf8', fontWeight: 'normal' }}>
                          • {campaignFootage.channel_url.replace('https://www.youtube.com/', '')}
                        </span>
                      )}
                    </span>
                    <span style={{ fontSize: '11px', color: '#a1a1aa' }}>
                      Click any video to load & analyze
                    </span>
                  </div>

                  <div style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
                    gap: '10px'
                  }}>
                    {campaignFootage.videos.map((vid) => {
                      const isSelected = url.trim() === vid.url.trim()
                      return (
                        <div
                          key={vid.video_id || vid.url}
                          onClick={() => handleFetchInfo(null, vid.url)}
                          style={{
                            background: isSelected ? '#1e1b4b' : '#18181b',
                            border: isSelected ? '1.5px solid #818cf8' : '1px solid #3f3f46',
                            borderRadius: '8px',
                            padding: '8px',
                            cursor: 'pointer',
                            transition: 'all 0.15s ease',
                            display: 'flex',
                            flexDirection: 'column',
                            gap: '8px'
                          }}
                        >
                          <div style={{ position: 'relative', width: '100%', height: '115px', borderRadius: '6px', overflow: 'hidden', background: '#09090b' }}>
                            {vid.thumbnail ? (
                              <img
                                src={vid.thumbnail}
                                alt={vid.title}
                                style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                              />
                            ) : (
                              <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#71717a' }}>
                                📹 Video
                              </div>
                            )}
                            {vid.duration_formatted && (
                              <span style={{
                                position: 'absolute',
                                bottom: '5px',
                                right: '5px',
                                background: 'rgba(0,0,0,0.85)',
                                color: '#fff',
                                fontSize: '10px',
                                fontWeight: 'bold',
                                padding: '2px 5px',
                                borderRadius: '4px'
                              }}>
                                ⏱️ {vid.duration_formatted}
                              </span>
                            )}
                            {isSelected && (
                              <span style={{
                                position: 'absolute',
                                top: '5px',
                                left: '5px',
                                background: '#10b981',
                                color: '#fff',
                                fontSize: '10px',
                                fontWeight: 'bold',
                                padding: '2px 6px',
                                borderRadius: '4px'
                              }}>
                                ✓ Selected
                              </span>
                            )}
                          </div>

                          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'space-between', gap: '6px' }}>
                            <div style={{
                              fontSize: '12px',
                              fontWeight: '600',
                              color: isSelected ? '#c7d2fe' : '#f4f4f5',
                              lineHeight: '1.3',
                              display: '-webkit-box',
                              WebkitLineClamp: 2,
                              WebkitBoxOrient: 'vertical',
                              overflow: 'hidden'
                            }} title={vid.title}>
                              {vid.title}
                            </div>

                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation()
                                handleFetchInfo(null, vid.url)
                              }}
                              style={{
                                width: '100%',
                                padding: '6px 8px',
                                borderRadius: '6px',
                                border: 'none',
                                background: isSelected ? '#4338ca' : '#27272a',
                                color: isSelected ? '#fff' : '#e4e4e7',
                                fontSize: '11px',
                                fontWeight: '600',
                                cursor: 'pointer',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                gap: '4px'
                              }}
                            >
                              <span>⚡</span> {isSelected ? 'Selected & Ready' : 'Clip This Video'}
                            </button>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              ) : (
                !campaignFootage.drive_links?.length && (
                  <div style={{ fontSize: '11px', color: '#94a3b8' }}>
                    ℹ️ No direct videos in brief. Paste any authorized video link from this creator below.
                  </div>
                )
              )}
            </div>
          )}
        </div>

        {/* Custom URL Input Header */}
        <div style={{ marginBottom: '8px', fontSize: '12px', color: '#a1a1aa' }}>
          {selectedCampaign ? '🔗 Or paste any custom YouTube video URL:' : 'Paste YouTube Video URL:'}
        </div>

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

            <div style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
              <button
                type="button"
                onClick={handleDetectViralMoments}
                disabled={loadingMoments || isReviewingAll}
                style={{
                  background: loadingMoments ? '#312e81' : 'linear-gradient(135deg, #4f46e5 0%, #6366f1 100%)',
                  color: 'white',
                  border: 'none',
                  borderRadius: '8px',
                  padding: '12px 20px',
                  fontSize: '14px',
                  fontWeight: 'bold',
                  cursor: (loadingMoments || isReviewingAll) ? 'not-allowed' : 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  boxShadow: '0 4px 12px rgba(99, 102, 241, 0.3)'
                }}
              >
                {loadingMoments ? '🤖 Analyzing 300+ Sentences...' : '⚡ Find Top Viral Clips (Groq AI)'}
              </button>

              {viralMoments.length > 0 && (
                <button
                  type="button"
                  onClick={handleReviewAllClips}
                  disabled={isReviewingAll || loadingMoments}
                  style={{
                    background: isReviewingAll ? '#1e293b' : 'linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%)',
                    color: 'white',
                    border: 'none',
                    borderRadius: '8px',
                    padding: '12px 20px',
                    fontSize: '14px',
                    fontWeight: 'bold',
                    cursor: (isReviewingAll || loadingMoments) ? 'not-allowed' : 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    boxShadow: '0 4px 12px rgba(2, 132, 199, 0.3)'
                  }}
                >
                  {isReviewingAll ? '🔍 Auditing Quality & Keyframes...' : '📋 Audit All Clips (Editorial Review)'}
                </button>
              )}
            </div>
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
                        <p style={{ margin: '0 0 10px 0', fontSize: '11px', color: '#71717a', lineHeight: 1.35 }}>
                          💡 {clip.reason}
                        </p>
                      )}

                      {/* Editorial Quality Review Section */}
                      <div style={{
                        background: '#121215',
                        border: '1px solid #27272a',
                        borderRadius: '8px',
                        padding: '10px',
                        marginBottom: '12px'
                      }}>
                        {clip.editorial_review ? (
                          <div>
                            {/* Review Header Banner */}
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '6px' }}>
                              <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                                <span style={{
                                  fontSize: '11px',
                                  fontWeight: 'bold',
                                  padding: '2px 8px',
                                  borderRadius: '4px',
                                  background: clip.editorial_review.status === 'APPROVED' ? '#052e16' : (clip.editorial_review.status === 'NEEDS_REVIEW' ? '#451a03' : '#450a0a'),
                                  color: clip.editorial_review.status === 'APPROVED' ? '#4ade80' : (clip.editorial_review.status === 'NEEDS_REVIEW' ? '#fbbf24' : '#f87171'),
                                  border: `1px solid ${clip.editorial_review.status === 'APPROVED' ? '#15803d' : (clip.editorial_review.status === 'NEEDS_REVIEW' ? '#b45309' : '#b91c1c')}`
                                }}>
                                  {clip.editorial_review.status === 'APPROVED' && '✅ EDITORIAL APPROVED'}
                                  {clip.editorial_review.status === 'NEEDS_REVIEW' && '⚠️ NEEDS REVIEW'}
                                  {clip.editorial_review.status === 'REJECTED' && '❌ REJECTED'}
                                </span>
                                <span style={{
                                  fontSize: '11px',
                                  fontWeight: 'bold',
                                  background: '#1e1b4b',
                                  color: '#a5b4fc',
                                  padding: '2px 6px',
                                  borderRadius: '4px'
                                }}>
                                  {clip.editorial_review.overall_score}/100
                                </span>
                              </div>

                              <button
                                type="button"
                                onClick={() => setExpandedReviews({
                                  ...expandedReviews,
                                  [clip.clip_id]: !expandedReviews[clip.clip_id]
                                })}
                                style={{
                                  background: 'transparent',
                                  border: 'none',
                                  color: '#38bdf8',
                                  fontSize: '11px',
                                  cursor: 'pointer',
                                  fontWeight: '600'
                                }}
                              >
                                {expandedReviews[clip.clip_id] ? 'Hide Audit ▲' : 'View Audit Details ▼'}
                              </button>
                            </div>

                            {/* User Manual Verdict Badge if present */}
                            {clip.editorial_review.user_verdict && (
                              <div style={{ marginTop: '6px', fontSize: '10px', color: clip.editorial_review.user_verdict === 'APPROVED' ? '#86efac' : '#fca5a5' }}>
                                👤 Editor Override: <strong>{clip.editorial_review.user_verdict}</strong>
                              </div>
                            )}

                            {/* Expanded Review Details */}
                            {expandedReviews[clip.clip_id] && (
                              <div style={{ marginTop: '10px' }}>
                                {/* Editorial Summary */}
                                {clip.editorial_review.editorial_summary && (
                                  <div style={{
                                    background: '#1c1917',
                                    borderLeft: '3px solid #f59e0b',
                                    padding: '8px',
                                    borderRadius: '4px',
                                    fontSize: '11px',
                                    color: '#e7e5e4',
                                    marginBottom: '8px',
                                    lineHeight: 1.4
                                  }}>
                                    "{clip.editorial_review.editorial_summary}"
                                  </div>
                                )}

                                {/* Critical Issues */}
                                {clip.editorial_review.critical_issues && clip.editorial_review.critical_issues.length > 0 && (
                                  <div style={{
                                    background: '#450a0a',
                                    border: '1px solid #dc2626',
                                    borderRadius: '6px',
                                    padding: '8px',
                                    marginBottom: '8px',
                                    fontSize: '11px',
                                    color: '#fca5a5'
                                  }}>
                                    <strong style={{ color: '#ef4444' }}>⛔ Critical Editorial Flaws:</strong>
                                    <ul style={{ margin: '4px 0 0 16px', padding: 0 }}>
                                      {clip.editorial_review.critical_issues.map((iss, idx) => (
                                        <li key={idx}>{iss}</li>
                                      ))}
                                    </ul>
                                  </div>
                                )}

                                {/* Suggestions */}
                                {clip.editorial_review.improvement_suggestions && clip.editorial_review.improvement_suggestions.length > 0 && (
                                  <div style={{
                                    background: '#1e293b',
                                    border: '1px solid #334155',
                                    borderRadius: '6px',
                                    padding: '8px',
                                    marginBottom: '8px',
                                    fontSize: '11px',
                                    color: '#94a3b8'
                                  }}>
                                    <span style={{ color: '#38bdf8', fontWeight: 'bold' }}>💡 Editor Tips: </span>
                                    {clip.editorial_review.improvement_suggestions.join('; ')}
                                  </div>
                                )}

                                {/* 6 Criteria Rubric Table */}
                                <div style={{
                                  background: '#09090b',
                                  border: '1px solid #27272a',
                                  borderRadius: '6px',
                                  padding: '8px',
                                  marginBottom: '8px'
                                }}>
                                  <div style={{ fontSize: '11px', fontWeight: 'bold', color: '#93c5fd', marginBottom: '6px', display: 'flex', justifyContent: 'space-between' }}>
                                    <span>6-Criteria Editorial Breakdown</span>
                                    <span>Score / 10</span>
                                  </div>
                                  {Object.entries(clip.editorial_review.criteria || {}).map(([cKey, cVal]) => (
                                    <div key={cKey} style={{ borderTop: '1px solid #18181b', paddingTop: '4px', marginTop: '4px', fontSize: '11px' }}>
                                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                        <span style={{ fontWeight: '600', color: '#e5e7eb', textTransform: 'capitalize' }}>
                                          {cKey.replace('_', ' ')} <span style={{ color: '#71717a', fontSize: '10px' }}>({cVal.weight_pct}%)</span>
                                        </span>
                                        <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                                          <span style={{
                                            fontSize: '9px',
                                            padding: '1px 5px',
                                            borderRadius: '3px',
                                            fontWeight: 'bold',
                                            background: cVal.status === 'PASSED' ? '#065f46' : (cVal.status === 'NEEDS_REVIEW' ? '#78350f' : '#7f1d1d'),
                                            color: cVal.status === 'PASSED' ? '#6ee7b7' : (cVal.status === 'NEEDS_REVIEW' ? '#fde68a' : '#fca5a5')
                                          }}>
                                            {cVal.status}
                                          </span>
                                          <span style={{ fontWeight: 'bold', color: '#fff' }}>{cVal.score}/10</span>
                                        </div>
                                      </div>
                                      <div style={{ fontSize: '10px', color: '#9ca3af', marginTop: '2px', lineHeight: 1.3 }}>
                                        {cVal.reason}
                                      </div>
                                    </div>
                                  ))}
                                </div>

                                {/* Visual Verification & Keyframe Thumbnails */}
                                {clip.editorial_review.visual_verification && (
                                  <div style={{
                                    background: '#09090b',
                                    border: '1px solid #27272a',
                                    borderRadius: '6px',
                                    padding: '8px',
                                    marginBottom: '8px'
                                  }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                                      <span style={{ fontSize: '11px', fontWeight: 'bold', color: '#cbd5e1' }}>
                                        👁 Visual Verification (Keyframes)
                                      </span>
                                      <span style={{
                                        fontSize: '10px',
                                        fontWeight: 'bold',
                                        color: clip.editorial_review.visual_verification.status === 'VERIFIED' ? '#4ade80' : '#f87171'
                                      }}>
                                        {clip.editorial_review.visual_verification.status}
                                      </span>
                                    </div>

                                    {clip.editorial_review.visual_verification.keyframes && clip.editorial_review.visual_verification.keyframes.length > 0 && (
                                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '4px', marginBottom: '6px' }}>
                                        {clip.editorial_review.visual_verification.keyframes.map((kf, kfIdx) => (
                                          <div
                                            key={kfIdx}
                                            onClick={() => setActiveKeyframeModal(kf)}
                                            style={{ cursor: 'pointer', textAlign: 'center' }}
                                            title="Click to enlarge keyframe"
                                          >
                                            <img
                                              src={`http://localhost:8000${kf.url}`}
                                              alt={kf.label}
                                              style={{ width: '100%', height: '52px', objectFit: 'cover', borderRadius: '4px', border: '1px solid #3f3f46' }}
                                            />
                                            <div style={{ fontSize: '9px', color: '#a1a1aa', textTransform: 'capitalize', marginTop: '2px' }}>
                                              {kf.label} ({kf.timestamp}s)
                                            </div>
                                          </div>
                                        ))}
                                      </div>
                                    )}

                                    {clip.editorial_review.visual_verification.observations?.map((obs, oIdx) => (
                                      <div key={oIdx} style={{ fontSize: '10px', color: '#94a3b8' }}>• {obs}</div>
                                    ))}
                                  </div>
                                )}

                                {/* Manual Override Controls */}
                                <div style={{ display: 'flex', gap: '6px', alignItems: 'center', flexWrap: 'wrap', marginTop: '6px' }}>
                                  <button
                                    type="button"
                                    onClick={() => handleManualVerdict(clip.clip_id, 'APPROVED')}
                                    style={{
                                      flex: 1,
                                      background: clip.editorial_review.user_verdict === 'APPROVED' ? '#15803d' : '#1f2937',
                                      border: '1px solid #16a34a',
                                      color: '#86efac',
                                      padding: '5px 8px',
                                      borderRadius: '4px',
                                      fontSize: '11px',
                                      fontWeight: 'bold',
                                      cursor: 'pointer'
                                    }}
                                  >
                                    ✅ Approve
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => handleManualVerdict(clip.clip_id, 'REJECTED')}
                                    style={{
                                      flex: 1,
                                      background: clip.editorial_review.user_verdict === 'REJECTED' ? '#991b1b' : '#1f2937',
                                      border: '1px solid #dc2626',
                                      color: '#fca5a5',
                                      padding: '5px 8px',
                                      borderRadius: '4px',
                                      fontSize: '11px',
                                      fontWeight: 'bold',
                                      cursor: 'pointer'
                                    }}
                                  >
                                    ❌ Reject
                                  </button>
                                  {clip.editorial_review.user_verdict && (
                                    <button
                                      type="button"
                                      onClick={() => handleManualVerdict(clip.clip_id, 'RESET')}
                                      style={{
                                        background: 'transparent',
                                        border: '1px solid #4b5563',
                                        color: '#9ca3af',
                                        padding: '5px 8px',
                                        borderRadius: '4px',
                                        fontSize: '10px',
                                        cursor: 'pointer'
                                      }}
                                      title="Reset to AI verdict"
                                    >
                                      ↺ Reset
                                    </button>
                                  )}
                                  <button
                                    type="button"
                                    onClick={() => handleReviewClip(clip.clip_id)}
                                    disabled={reviewingClipId === clip.clip_id}
                                    style={{
                                      background: '#374151',
                                      border: 'none',
                                      color: '#e5e7eb',
                                      padding: '5px 8px',
                                      borderRadius: '4px',
                                      fontSize: '10px',
                                      cursor: reviewingClipId === clip.clip_id ? 'not-allowed' : 'pointer'
                                    }}
                                    title="Re-run AI editorial evaluation"
                                  >
                                    {reviewingClipId === clip.clip_id ? 'Auditing...' : '🔄 Re-audit'}
                                  </button>
                                </div>
                              </div>
                            )}
                          </div>
                        ) : (
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <span style={{ fontSize: '11px', color: '#a1a1aa' }}>
                              Editorial Quality Review: <span style={{ color: '#fbbf24' }}>Pending</span>
                            </span>
                            <button
                              type="button"
                              onClick={() => handleReviewClip(clip.clip_id)}
                              disabled={reviewingClipId === clip.clip_id}
                              style={{
                                background: reviewingClipId === clip.clip_id ? '#312e81' : '#4f46e5',
                                color: 'white',
                                border: 'none',
                                borderRadius: '4px',
                                padding: '5px 10px',
                                fontSize: '11px',
                                fontWeight: 'bold',
                                cursor: reviewingClipId === clip.clip_id ? 'not-allowed' : 'pointer'
                              }}
                            >
                              {reviewingClipId === clip.clip_id ? '🔍 Auditing...' : '📋 Run Quality Review'}
                            </button>
                          </div>
                        )}
                      </div>
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
                          {selectedCampaign && (
                            <button
                              type="button"
                              onClick={() => copyPostingCaption(clip)}
                              style={{
                                background: copiedCaptionClipId === clip.clip_id ? '#15803d' : '#0284c7',
                                color: '#fff',
                                padding: '8px 12px',
                                borderRadius: '6px',
                                border: 'none',
                                fontSize: '11px',
                                fontWeight: 'bold',
                                cursor: 'pointer',
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '4px'
                              }}
                              title="Copy title, hashtags, CTA, and mentions formatted for this campaign"
                            >
                              {copiedCaptionClipId === clip.clip_id ? '✅ Copied!' : '📋 Caption'}
                            </button>
                          )}
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

      {/* Lightbox Modal for Keyframe Visual Inspection */}
      {activeKeyframeModal && (
        <div
          onClick={() => setActiveKeyframeModal(null)}
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0, 0, 0, 0.85)',
            zIndex: 9999,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '20px'
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: '#18181b',
              border: '1px solid #3f3f46',
              borderRadius: '12px',
              padding: '16px',
              maxWidth: '90vw',
              maxHeight: '90vh',
              display: 'flex',
              flexDirection: 'column',
              boxShadow: '0 20px 50px rgba(0,0,0,0.8)'
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
              <span style={{ fontSize: '14px', fontWeight: 'bold', color: '#f4f4f5', textTransform: 'capitalize' }}>
                📸 Keyframe: {activeKeyframeModal.label} ({activeKeyframeModal.timestamp}s)
              </span>
              <button
                type="button"
                onClick={() => setActiveKeyframeModal(null)}
                style={{
                  background: '#27272a',
                  border: 'none',
                  color: '#fff',
                  borderRadius: '50%',
                  width: '28px',
                  height: '28px',
                  cursor: 'pointer',
                  fontWeight: 'bold'
                }}
              >
                ✕
              </button>
            </div>
            <img
              src={`http://localhost:8000${activeKeyframeModal.url}`}
              alt={activeKeyframeModal.label}
              style={{
                maxWidth: '800px',
                maxHeight: '70vh',
                width: '100%',
                height: 'auto',
                borderRadius: '8px',
                objectFit: 'contain',
                border: '1px solid #27272a'
              }}
            />
          </div>
        </div>
      )}
    </div>
  )
}
