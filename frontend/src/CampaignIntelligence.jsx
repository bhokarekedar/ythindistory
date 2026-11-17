import { useState, useEffect } from 'react'

export default function CampaignIntelligence() {
  // Channel Profile State
  const [channelProfile, setChannelProfile] = useState(null)
  const [isEditingProfile, setIsEditingProfile] = useState(false)
  const [profileFormData, setProfileFormData] = useState({})
  const [savingProfile, setSavingProfile] = useState(false)

  // Input State
  const [title, setTitle] = useState('')
  const [sourcePlatform, setSourcePlatform] = useState('Content Rewards')
  const [campaignUrl, setCampaignUrl] = useState('')
  const [rawBrief, setRawBrief] = useState('')
  const [analyzing, setAnalyzing] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')

  // Active Analysis Result (prior to or just after saving)
  const [activeAnalysis, setActiveAnalysis] = useState(null)
  const [isDuplicate, setIsDuplicate] = useState(false)
  const [existingDuplicate, setExistingDuplicate] = useState(null)
  const [savingCampaign, setSavingCampaign] = useState(false)
  const [saveSuccessMsg, setSaveSuccessMsg] = useState('')

  // Campaign Library State
  const [campaigns, setCampaigns] = useState([])
  const [loadingCampaigns, setLoadingCampaigns] = useState(false)
  const [selectedStatusTab, setSelectedStatusTab] = useState('ALL')
  const [platformFilter, setPlatformFilter] = useState('ALL')
  const [searchQuery, setSearchQuery] = useState('')

  // Selected Campaign Detail Modal
  const [selectedCampaign, setSelectedCampaign] = useState(null)
  const [isEditingMetadata, setIsEditingMetadata] = useState(false)
  const [metadataFormData, setMetadataFormData] = useState({})
  const [updatingMetadata, setUpdatingMetadata] = useState(false)
  const [actionInProgress, setActionInProgress] = useState(false)

  // Fetch Channel Profile on mount
  useEffect(() => {
    fetchChannelProfile()
    fetchCampaigns()
  }, [])

  const fetchChannelProfile = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/campaigns/channel-profile')
      if (!res.ok) return
      const data = await res.json()
      setChannelProfile(data.profile)
      setProfileFormData(data.profile)
    } catch (err) {
      console.error('Failed to fetch channel profile:', err)
    }
  }

  const fetchCampaigns = async () => {
    setLoadingCampaigns(true)
    try {
      const res = await fetch('http://localhost:8000/api/campaigns')
      if (!res.ok) return
      const data = await res.json()
      setCampaigns(data.campaigns || [])
    } catch (err) {
      console.error('Failed to fetch campaigns:', err)
    } finally {
      setLoadingCampaigns(false)
    }
  }

  // Update Channel Profile
  const handleSaveProfile = async (e) => {
    if (e) e.preventDefault()
    setSavingProfile(true)
    try {
      const res = await fetch('http://localhost:8000/api/campaigns/channel-profile', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(profileFormData)
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Failed to update channel profile')
      setChannelProfile(data.profile)
      setIsEditingProfile(false)
    } catch (err) {
      setErrorMsg(err.message)
    } finally {
      setSavingProfile(false)
    }
  }

  // Analyze Campaign Brief
  const handleAnalyzeCampaign = async (e) => {
    if (e) e.preventDefault()
    if (!rawBrief.trim()) {
      setErrorMsg('Please paste a campaign brief to analyze.')
      return
    }

    setAnalyzing(true)
    setErrorMsg('')
    setActiveAnalysis(null)
    setSaveSuccessMsg('')
    setIsDuplicate(false)
    setExistingDuplicate(null)

    try {
      const res = await fetch('http://localhost:8000/api/campaigns/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          brief: rawBrief.trim(),
          title: title.trim() || undefined,
          source_platform: sourcePlatform,
          campaign_url: campaignUrl.trim() || undefined
        })
      })

      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Failed to analyze campaign')

      setActiveAnalysis(data.campaign)
      setIsDuplicate(data.is_duplicate)
      setExistingDuplicate(data.existing_campaign)
    } catch (err) {
      setErrorMsg(err.message || 'Error communicating with campaign intelligence engine')
    } finally {
      setAnalyzing(false)
    }
  }

  // Save Analyzed Campaign
  const handleSaveCampaign = async () => {
    if (!activeAnalysis) return
    setSavingCampaign(true)
    setErrorMsg('')

    try {
      const res = await fetch('http://localhost:8000/api/campaigns/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ campaign: activeAnalysis })
      })

      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Failed to save campaign')

      setSaveSuccessMsg(`✅ Campaign '${data.campaign.title}' saved to library with status ${data.campaign.status}!`)
      fetchCampaigns()
      // Keep result displayed but update campaign_id
      setActiveAnalysis(data.campaign)
      setIsDuplicate(false)
    } catch (err) {
      setErrorMsg(err.message)
    } finally {
      setSavingCampaign(false)
    }
  }

  // Manual Override (Approve / Reject / Reset)
  const handleVerdictOverride = async (campaignId, verdict) => {
    setActionInProgress(true)
    try {
      const res = await fetch(`http://localhost:8000/api/campaigns/${campaignId}/verdict`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          verdict,
          reason: `Manual override by channel editor to ${verdict}.`
        })
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Failed to update verdict')

      if (selectedCampaign && selectedCampaign.campaign_id === campaignId) {
        setSelectedCampaign(data.campaign)
      }
      if (activeAnalysis && activeAnalysis.campaign_id === campaignId) {
        setActiveAnalysis(data.campaign)
      }
      fetchCampaigns()
    } catch (err) {
      setErrorMsg(err.message)
    } finally {
      setActionInProgress(false)
    }
  }

  // Re-analyze existing campaign
  const handleReanalyze = async (campaignId) => {
    setActionInProgress(true)
    try {
      const res = await fetch(`http://localhost:8000/api/campaigns/${campaignId}/reanalyze`, {
        method: 'POST'
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Failed to re-analyze campaign')

      setSelectedCampaign(data.campaign)
      fetchCampaigns()
    } catch (err) {
      setErrorMsg(err.message)
    } finally {
      setActionInProgress(false)
    }
  }

  // Archive campaign
  const handleArchive = async (campaignId) => {
    if (!window.confirm('Archive this campaign? It will be hidden from the active library.')) return
    setActionInProgress(true)
    try {
      const res = await fetch(`http://localhost:8000/api/campaigns/${campaignId}/archive`, {
        method: 'POST'
      })
      if (!res.ok) throw new Error('Failed to archive campaign')

      if (selectedCampaign && selectedCampaign.campaign_id === campaignId) {
        setSelectedCampaign(null)
      }
      fetchCampaigns()
    } catch (err) {
      setErrorMsg(err.message)
    } finally {
      setActionInProgress(false)
    }
  }

  // Update Posting Metadata
  const handleSaveMetadata = async () => {
    if (!selectedCampaign) return
    setUpdatingMetadata(true)
    try {
      const res = await fetch(`http://localhost:8000/api/campaigns/${selectedCampaign.campaign_id}/metadata`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ posting_metadata: metadataFormData })
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Failed to update metadata')

      setSelectedCampaign(data.campaign)
      setIsEditingMetadata(false)
      fetchCampaigns()
    } catch (err) {
      setErrorMsg(err.message)
    } finally {
      setUpdatingMetadata(false)
    }
  }

  // Sample Brief Presets
  const applyPreset = (presetType) => {
    setErrorMsg('')
    setSaveSuccessMsg('')
    if (presetType === 'minecraft_approved') {
      setTitle('Minecraft Speedrun Highlights S4')
      setSourcePlatform('Content Rewards')
      setCampaignUrl('https://contentrewards.com/campaign/minecraft-s4')
      setRawBrief(`CAMPAIGN: Minecraft Speedrun Highlights Season 4
PLATFORM: Content Rewards
DESCRIPTION: We are paying creator clippers to create viral YouTube Shorts and TikToks from authorized Minecraft streamer VODs!
Source footage drive: https://drive.google.com/drive/folders/minecraft_authorized
ELIGIBILITY: Open to all creators, big or small! No minimum subscriber or follower count required. New channels welcome.
FORMAT: 9:16 vertical video with captions.
PAYOUT: $2.50 CPM up to $500 per video.
HASHTAGS: #Minecraft #GamingClips #Speedrun
MENTION: @MinecraftClippers`)
    } else if (presetType === 'subscribers_rejected') {
      setTitle('Top Tier Valorant Clips')
      setSourcePlatform('Whop')
      setCampaignUrl('https://whop.com/terminal/valorant-tier1')
      setRawBrief(`CAMPAIGN: Top Tier Valorant Clips
REQUIREMENTS: Channels must have at least 2,000 subscribers on YouTube to qualify for monetization.
Must submit channel analytics screenshot for verification.
Payout: $4.00 CPM.
Footage: Provided in portal.
Hashtags: #Valorant #ValorantClips`)
    } else if (presetType === 'facecam_rejected') {
      setTitle('AI Productivity App Review')
      setSourcePlatform('Vyro')
      setCampaignUrl('https://app.vyro.com/campaigns/ai-tool')
      setRawBrief(`CAMPAIGN: AI Productivity App Review
REQUIREMENTS: Creator must film themselves on camera (face cam mandatory) demonstrating the web interface and features.
No faceless voiceovers or clipping allowed. Original footage only.
PAYOUT: $150 fixed payment per video approved.`)
    } else if (presetType === 'unclear_needs_info') {
      setTitle('Internet Drama & Mystery Shorts')
      setSourcePlatform('Whop')
      setCampaignUrl('https://whop.com/invest/terminal/drama-clips')
      setRawBrief(`CAMPAIGN: Internet Drama Clips
DESCRIPTION: Create short videos about recent internet drama.
PAYMENT: $1.50 CPM.
Note: You find your own footage across Twitter and YouTube. We do not provide licenses or authorized drives.
Must tag #InternetDrama.`)
    } else if (presetType === 'challenge_approved') {
      setTitle('Extreme Stunts & Crazy Experiments')
      setSourcePlatform('Content Rewards')
      setCampaignUrl('https://contentrewards.com/campaign/extreme-stunts')
      setRawBrief(`CAMPAIGN: Extreme Stunts & Challenge Clips
DESCRIPTION: Clip the craziest challenge moments and experiments from our authorized YouTube channel footage library.
ELIGIBILITY: No follower or subscriber requirement. Open to anyone who can edit entertaining 9:16 vertical shorts.
PAYOUT: $3.00 CPM up to $1,000 budget cap.
MANDATORY HASHTAGS: #Challenge #CrazyExperiments #ViralLoop
CTA: Comment your favorite stunt below!`)
    }
  }

  // Filter campaigns
  const filteredCampaigns = campaigns.filter((c) => {
    if (selectedStatusTab !== 'ALL' && c.status !== selectedStatusTab) return false
    if (platformFilter !== 'ALL' && c.source_platform !== platformFilter) return false
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      const match = `${c.title} ${c.raw_brief} ${c.source_platform}`.toLowerCase()
      if (!match.includes(q)) return false
    }
    return true
  })

  // Format Helper
  const getDecisionBadge = (decision) => {
    if (decision === 'APPROVED') {
      return { bg: '#052e16', text: '#4ade80', border: '#15803d', label: 'APPROVED' }
    } else if (decision === 'REJECTED') {
      return { bg: '#450a0a', text: '#f87171', border: '#b91c1c', label: 'REJECTED' }
    } else if (decision === 'NEEDS_INFO') {
      return { bg: '#451a03', text: '#fbbf24', border: '#b45309', label: 'NEEDS INFO' }
    }
    return { bg: '#18181b', text: '#a1a1aa', border: '#3f3f46', label: decision || 'PENDING' }
  }

  return (
    <div style={{ maxWidth: '1000px', margin: '0 auto', textAlign: 'left' }}>
      {/* Top Banner & Channel Profile Pill */}
      <div style={{
        background: 'linear-gradient(135deg, #0c4a6e 0%, #0369a1 50%, #0284c7 100%)',
        padding: '20px 24px',
        borderRadius: '12px',
        border: '1px solid #38bdf8',
        marginBottom: '24px',
        boxShadow: '0 8px 24px rgba(2, 132, 199, 0.25)'
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '14px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '24px' }}>🎯</span>
              <h2 style={{ margin: 0, fontSize: '22px', color: '#ffffff', fontWeight: '800', letterSpacing: '-0.5px' }}>
                Campaign Intelligence & Approval System
              </h2>
              <span style={{
                background: '#38bdf8',
                color: '#082f49',
                fontSize: '11px',
                fontWeight: 'bold',
                padding: '2px 8px',
                borderRadius: '12px',
                textTransform: 'uppercase'
              }}>
                ViralLoop
              </span>
            </div>
            <p style={{ margin: '6px 0 0 0', color: '#e0f2fe', fontSize: '13px' }}>
              "The Best Moments. All in One Loop." • Pre-screen marketplace campaigns before spending processing time.
            </p>
          </div>

          {/* Active Channel Stats Widget */}
          {channelProfile && (
            <div style={{
              background: 'rgba(8, 47, 73, 0.65)',
              border: '1px solid #0284c7',
              borderRadius: '8px',
              padding: '10px 14px',
              display: 'flex',
              alignItems: 'center',
              gap: '14px',
              fontSize: '12px',
              color: '#f0f9ff'
            }}>
              <div>
                <span style={{ color: '#7dd3fc', display: 'block', fontSize: '10px' }}>CHANNEL STATUS</span>
                <strong>{channelProfile.channel_status} ({channelProfile.youtube_subscribers} subs)</strong>
              </div>
              <div style={{ borderLeft: '1px solid #0369a1', paddingLeft: '12px' }}>
                <span style={{ color: '#7dd3fc', display: 'block', fontSize: '10px' }}>PRODUCTION</span>
                <strong>Faceless 9:16 Shorts</strong>
              </div>
              <button
                type="button"
                onClick={() => {
                  setProfileFormData(channelProfile)
                  setIsEditingProfile(true)
                }}
                style={{
                  background: '#0284c7',
                  border: 'none',
                  color: 'white',
                  borderRadius: '6px',
                  padding: '6px 10px',
                  fontSize: '11px',
                  fontWeight: 'bold',
                  cursor: 'pointer'
                }}
              >
                ⚙️ Profile
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Channel Profile Edit Modal */}
      {isEditingProfile && (
        <div style={{
          position: 'fixed',
          top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.8)',
          zIndex: 9999,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '20px'
        }}>
          <div style={{
            background: '#18181b',
            border: '1px solid #3f3f46',
            borderRadius: '12px',
            padding: '24px',
            maxWidth: '520px',
            width: '100%',
            boxShadow: '0 12px 40px rgba(0,0,0,0.6)'
          }}>
            <h3 style={{ margin: '0 0 14px 0', fontSize: '18px', color: '#fff' }}>
              👤 Update ViralLoop Channel Profile
            </h3>
            <p style={{ fontSize: '12px', color: '#a1a1aa', margin: '0 0 16px 0', lineHeight: 1.4 }}>
              As our YouTube, Instagram, and TikTok accounts grow, update our verified statistics below so the eligibility engine evaluates future campaigns accurately.
            </p>

            <form onSubmit={handleSaveProfile} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                <div>
                  <label style={{ fontSize: '11px', color: '#9ca3af', display: 'block', marginBottom: '4px' }}>
                    YouTube Subscribers:
                  </label>
                  <input
                    type="number"
                    value={profileFormData.youtube_subscribers || 0}
                    onChange={(e) => setProfileFormData({ ...profileFormData, youtube_subscribers: parseInt(e.target.value) || 0 })}
                    style={{ width: '100%', background: '#09090b', border: '1px solid #3f3f46', color: '#fff', padding: '8px', borderRadius: '6px' }}
                  />
                </div>
                <div>
                  <label style={{ fontSize: '11px', color: '#9ca3af', display: 'block', marginBottom: '4px' }}>
                    Instagram Followers:
                  </label>
                  <input
                    type="number"
                    value={profileFormData.instagram_followers || 0}
                    onChange={(e) => setProfileFormData({ ...profileFormData, instagram_followers: parseInt(e.target.value) || 0 })}
                    style={{ width: '100%', background: '#09090b', border: '1px solid #3f3f46', color: '#fff', padding: '8px', borderRadius: '6px' }}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                <div>
                  <label style={{ fontSize: '11px', color: '#9ca3af', display: 'block', marginBottom: '4px' }}>
                    TikTok Followers:
                  </label>
                  <input
                    type="number"
                    value={profileFormData.tiktok_followers || 0}
                    onChange={(e) => setProfileFormData({ ...profileFormData, tiktok_followers: parseInt(e.target.value) || 0 })}
                    style={{ width: '100%', background: '#09090b', border: '1px solid #3f3f46', color: '#fff', padding: '8px', borderRadius: '6px' }}
                  />
                </div>
                <div>
                  <label style={{ fontSize: '11px', color: '#9ca3af', display: 'block', marginBottom: '4px' }}>
                    Previous Viral Video URLs:
                  </label>
                  <input
                    type="number"
                    value={profileFormData.previous_viral_videos_count || 0}
                    onChange={(e) => setProfileFormData({ ...profileFormData, previous_viral_videos_count: parseInt(e.target.value) || 0 })}
                    style={{ width: '100%', background: '#09090b', border: '1px solid #3f3f46', color: '#fff', padding: '8px', borderRadius: '6px' }}
                  />
                </div>
              </div>

              <div>
                <label style={{ fontSize: '11px', color: '#9ca3af', display: 'block', marginBottom: '4px' }}>
                  Channel Status:
                </label>
                <select
                  value={profileFormData.channel_status || 'NEW'}
                  onChange={(e) => setProfileFormData({ ...profileFormData, channel_status: e.target.value })}
                  style={{ width: '100%', background: '#09090b', border: '1px solid #3f3f46', color: '#fff', padding: '8px', borderRadius: '6px' }}
                >
                  <option value="NEW">NEW (Brand New Channel)</option>
                  <option value="GROWING">GROWING (1,000+ Subs)</option>
                  <option value="ESTABLISHED">ESTABLISHED (10,000+ Subs)</option>
                </select>
              </div>

              <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', marginTop: '12px' }}>
                <button
                  type="button"
                  onClick={() => setIsEditingProfile(false)}
                  style={{ background: '#3f3f46', color: '#fff', border: 'none', padding: '8px 16px', borderRadius: '6px', cursor: 'pointer' }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={savingProfile}
                  style={{ background: '#0284c7', color: '#fff', border: 'none', padding: '8px 18px', borderRadius: '6px', fontWeight: 'bold', cursor: 'pointer' }}
                >
                  {savingProfile ? 'Saving...' : 'Save Profile'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* SECTION 1: Campaign Brief Input & Analysis */}
      <div style={{
        background: '#18181b',
        border: '1px solid #27272a',
        borderRadius: '12px',
        padding: '24px',
        marginBottom: '24px',
        boxShadow: '0 4px 16px rgba(0,0,0,0.3)'
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px', flexWrap: 'wrap', gap: '10px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{
              background: '#0284c7',
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
            <h3 style={{ margin: 0, fontSize: '17px', color: '#f4f4f5' }}>
              Paste Campaign Brief from Marketplace
            </h3>
          </div>

          {/* Preset Buttons */}
          <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', alignItems: 'center' }}>
            <span style={{ fontSize: '11px', color: '#71717a' }}>Presets:</span>
            <button
              type="button"
              onClick={() => applyPreset('minecraft_approved')}
              style={{ background: '#1e293b', border: '1px solid #334155', color: '#38bdf8', padding: '4px 8px', borderRadius: '4px', fontSize: '11px', cursor: 'pointer' }}
            >
              🎮 Gaming (Approved)
            </button>
            <button
              type="button"
              onClick={() => applyPreset('subscribers_rejected')}
              style={{ background: '#1e293b', border: '1px solid #334155', color: '#f87171', padding: '4px 8px', borderRadius: '4px', fontSize: '11px', cursor: 'pointer' }}
            >
              ⛔ 2k Subs (Rejected)
            </button>
            <button
              type="button"
              onClick={() => applyPreset('facecam_rejected')}
              style={{ background: '#1e293b', border: '1px solid #334155', color: '#f87171', padding: '4px 8px', borderRadius: '4px', fontSize: '11px', cursor: 'pointer' }}
            >
              📹 Face-Cam (Rejected)
            </button>
            <button
              type="button"
              onClick={() => applyPreset('unclear_needs_info')}
              style={{ background: '#1e293b', border: '1px solid #334155', color: '#fbbf24', padding: '4px 8px', borderRadius: '4px', fontSize: '11px', cursor: 'pointer' }}
            >
              ❓ Unclear (Needs Info)
            </button>
            <button
              type="button"
              onClick={() => applyPreset('challenge_approved')}
              style={{ background: '#1e293b', border: '1px solid #334155', color: '#4ade80', padding: '4px 8px', borderRadius: '4px', fontSize: '11px', cursor: 'pointer' }}
            >
              ⚡ Stunts (Approved)
            </button>
          </div>
        </div>

        <form onSubmit={handleAnalyzeCampaign}>
          {/* Metadata Row */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px', marginBottom: '14px' }}>
            <div>
              <label style={{ fontSize: '11px', color: '#a1a1aa', display: 'block', marginBottom: '4px' }}>
                Source Platform:
              </label>
              <select
                value={sourcePlatform}
                onChange={(e) => setSourcePlatform(e.target.value)}
                style={{
                  width: '100%',
                  background: '#09090b',
                  border: '1px solid #3f3f46',
                  color: '#fff',
                  padding: '9px 12px',
                  borderRadius: '6px',
                  fontSize: '13px'
                }}
              >
                <option value="Content Rewards">Content Rewards</option>
                <option value="Whop">Whop Terminal</option>
                <option value="Vyro">Vyro</option>
                <option value="Other">Other Marketplace / Direct Creator</option>
              </select>
            </div>

            <div>
              <label style={{ fontSize: '11px', color: '#a1a1aa', display: 'block', marginBottom: '4px' }}>
                Campaign Title (Optional):
              </label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Auto-extracted if blank"
                style={{
                  width: '100%',
                  boxSizing: 'border-box',
                  background: '#09090b',
                  border: '1px solid #3f3f46',
                  color: '#fff',
                  padding: '9px 12px',
                  borderRadius: '6px',
                  fontSize: '13px'
                }}
              />
            </div>

            <div>
              <label style={{ fontSize: '11px', color: '#a1a1aa', display: 'block', marginBottom: '4px' }}>
                Campaign URL (Optional):
              </label>
              <input
                type="url"
                value={campaignUrl}
                onChange={(e) => setCampaignUrl(e.target.value)}
                placeholder="https://..."
                style={{
                  width: '100%',
                  boxSizing: 'border-box',
                  background: '#09090b',
                  border: '1px solid #3f3f46',
                  color: '#fff',
                  padding: '9px 12px',
                  borderRadius: '6px',
                  fontSize: '13px'
                }}
              />
            </div>
          </div>

          {/* Large Brief Textarea */}
          <div style={{ marginBottom: '16px' }}>
            <label style={{ fontSize: '11px', color: '#a1a1aa', display: 'block', marginBottom: '6px' }}>
              Complete Campaign Description & Rules (Paste everything here):
            </label>
            <textarea
              rows={7}
              value={rawBrief}
              onChange={(e) => setRawBrief(e.target.value)}
              placeholder="Paste raw text copied from Content Rewards, Whop, Vyro, or email briefs. Include rules, CPM, hashtags, follower prerequisites, and footage links..."
              style={{
                width: '100%',
                boxSizing: 'border-box',
                background: '#09090b',
                border: '1px solid #3f3f46',
                color: '#fafafa',
                padding: '12px',
                borderRadius: '8px',
                fontSize: '13px',
                lineHeight: 1.45,
                fontFamily: 'inherit'
              }}
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
            <button
              type="submit"
              disabled={analyzing || !rawBrief.trim()}
              style={{
                background: analyzing ? '#0369a1' : 'linear-gradient(135deg, #0284c7 0%, #0ea5e9 100%)',
                color: 'white',
                border: 'none',
                borderRadius: '8px',
                padding: '12px 24px',
                fontSize: '14px',
                fontWeight: 'bold',
                cursor: (analyzing || !rawBrief.trim()) ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                boxShadow: '0 4px 14px rgba(2, 132, 199, 0.35)'
              }}
            >
              {analyzing ? '🤖 Evaluating Eligibility & Feasibility...' : '⚡ Analyze Campaign with AI'}
            </button>

            {rawBrief.trim() && (
              <button
                type="button"
                onClick={() => {
                  setRawBrief('')
                  setTitle('')
                  setCampaignUrl('')
                  setActiveAnalysis(null)
                  setErrorMsg('')
                }}
                style={{
                  background: 'transparent',
                  border: '1px solid #3f3f46',
                  color: '#a1a1aa',
                  padding: '8px 14px',
                  borderRadius: '6px',
                  fontSize: '12px',
                  cursor: 'pointer'
                }}
              >
                Clear Brief
              </button>
            )}
          </div>
        </form>

        {errorMsg && (
          <div style={{
            marginTop: '14px',
            padding: '10px 14px',
            borderRadius: '6px',
            background: '#450a0a',
            border: '1px solid #7f1d1d',
            color: '#fca5a5',
            fontSize: '13px'
          }}>
            ❌ {errorMsg}
          </div>
        )}

        {saveSuccessMsg && (
          <div style={{
            marginTop: '14px',
            padding: '10px 14px',
            borderRadius: '6px',
            background: '#052e16',
            border: '1px solid #15803d',
            color: '#86efac',
            fontSize: '13px'
          }}>
            {saveSuccessMsg}
          </div>
        )}
      </div>

      {/* SECTION 2: AI Analysis Result Card */}
      {activeAnalysis && (
        <div style={{
          background: '#18181b',
          border: `1.5px solid ${getDecisionBadge(activeAnalysis.status).border}`,
          borderRadius: '12px',
          padding: '24px',
          marginBottom: '24px',
          boxShadow: '0 8px 30px rgba(0,0,0,0.45)'
        }}>
          {/* Duplicate Warning Banner */}
          {isDuplicate && existingDuplicate && (
            <div style={{
              background: '#451a03',
              border: '1px solid #b45309',
              borderRadius: '8px',
              padding: '10px 14px',
              marginBottom: '16px',
              color: '#fde68a',
              fontSize: '12px',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center'
            }}>
              <span>
                ⚠️ <strong>Duplicate Campaign Detected:</strong> You previously analyzed this campaign as "{existingDuplicate.title}" ({existingDuplicate.status}).
              </span>
              <button
                type="button"
                onClick={() => setSelectedCampaign(existingDuplicate)}
                style={{ background: '#b45309', border: 'none', color: '#fff', padding: '4px 10px', borderRadius: '4px', cursor: 'pointer', fontSize: '11px', fontWeight: 'bold' }}
              >
                View Existing Record
              </button>
            </div>
          )}

          {/* Top Decision Header */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '14px', marginBottom: '18px' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                <span style={{
                  fontSize: '12px',
                  fontWeight: 'bold',
                  padding: '4px 12px',
                  borderRadius: '6px',
                  background: getDecisionBadge(activeAnalysis.status).bg,
                  color: getDecisionBadge(activeAnalysis.status).text,
                  border: `1px solid ${getDecisionBadge(activeAnalysis.status).border}`,
                  letterSpacing: '0.5px'
                }}>
                  DECISION: {getDecisionBadge(activeAnalysis.status).label}
                </span>
                <span style={{ fontSize: '12px', color: '#9ca3af' }}>
                  Platform: <strong>{activeAnalysis.source_platform}</strong>
                </span>
                {activeAnalysis.commercial_details?.cpm_max && (
                  <span style={{ background: '#1e1b4b', color: '#a5b4fc', padding: '2px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 'bold' }}>
                    💰 ${activeAnalysis.commercial_details.cpm_max} CPM
                  </span>
                )}
              </div>

              <h3 style={{ margin: '0 0 6px 0', fontSize: '20px', color: '#ffffff' }}>
                {activeAnalysis.title}
              </h3>
              <p style={{ margin: 0, fontSize: '13px', color: '#a1a1aa', fontStyle: 'italic', lineHeight: 1.4 }}>
                "{activeAnalysis.analysis?.summary}"
              </p>
            </div>

            {/* Overall Score Circle */}
            <div style={{
              background: '#09090b',
              border: '2px solid #27272a',
              borderRadius: '12px',
              padding: '12px 18px',
              textAlign: 'center',
              minWidth: '100px'
            }}>
              <div style={{ fontSize: '11px', color: '#71717a', fontWeight: 'bold', textTransform: 'uppercase' }}>
                Compatibility
              </div>
              <div style={{
                fontSize: '28px',
                fontWeight: '900',
                color: activeAnalysis.analysis.overall_score >= 70 ? '#4ade80' : (activeAnalysis.analysis.overall_score >= 50 ? '#fbbf24' : '#f87171'),
                marginTop: '2px'
              }}>
                {activeAnalysis.analysis.overall_score}
                <span style={{ fontSize: '14px', color: '#71717a' }}>/100</span>
              </div>
            </div>
          </div>

          {/* 4 Dimension Score Bars */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: '10px', marginBottom: '20px' }}>
            <div style={{ background: '#09090b', padding: '12px', borderRadius: '8px', border: '1px solid #27272a' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#a1a1aa', marginBottom: '4px' }}>
                <span>Channel Eligibility (35%)</span>
                <strong>{activeAnalysis.analysis.eligibility_score}%</strong>
              </div>
              <div style={{ height: '6px', background: '#27272a', borderRadius: '3px', overflow: 'hidden' }}>
                <div style={{
                  width: `${activeAnalysis.analysis.eligibility_score}%`,
                  height: '100%',
                  background: activeAnalysis.analysis.eligibility_score >= 70 ? '#22c55e' : (activeAnalysis.analysis.eligibility_score >= 50 ? '#f59e0b' : '#ef4444')
                }} />
              </div>
            </div>

            <div style={{ background: '#09090b', padding: '12px', borderRadius: '8px', border: '1px solid #27272a' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#a1a1aa', marginBottom: '4px' }}>
                <span>Niche Fit (25%)</span>
                <strong>{activeAnalysis.analysis.niche_compatibility_score}%</strong>
              </div>
              <div style={{ height: '6px', background: '#27272a', borderRadius: '3px', overflow: 'hidden' }}>
                <div style={{
                  width: `${activeAnalysis.analysis.niche_compatibility_score}%`,
                  height: '100%',
                  background: activeAnalysis.analysis.niche_compatibility_score >= 70 ? '#22c55e' : (activeAnalysis.analysis.niche_compatibility_score >= 50 ? '#f59e0b' : '#ef4444')
                }} />
              </div>
            </div>

            <div style={{ background: '#09090b', padding: '12px', borderRadius: '8px', border: '1px solid #27272a' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#a1a1aa', marginBottom: '4px' }}>
                <span>Production Feasibility (25%)</span>
                <strong>{activeAnalysis.analysis.production_feasibility_score}%</strong>
              </div>
              <div style={{ height: '6px', background: '#27272a', borderRadius: '3px', overflow: 'hidden' }}>
                <div style={{
                  width: `${activeAnalysis.analysis.production_feasibility_score}%`,
                  height: '100%',
                  background: activeAnalysis.analysis.production_feasibility_score >= 70 ? '#22c55e' : (activeAnalysis.analysis.production_feasibility_score >= 50 ? '#f59e0b' : '#ef4444')
                }} />
              </div>
            </div>

            <div style={{ background: '#09090b', padding: '12px', borderRadius: '8px', border: '1px solid #27272a' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#a1a1aa', marginBottom: '4px' }}>
                <span>Commercial Value (15%)</span>
                <strong>{activeAnalysis.analysis.commercial_score}%</strong>
              </div>
              <div style={{ height: '6px', background: '#27272a', borderRadius: '3px', overflow: 'hidden' }}>
                <div style={{
                  width: `${activeAnalysis.analysis.commercial_score}%`,
                  height: '100%',
                  background: activeAnalysis.analysis.commercial_score >= 70 ? '#22c55e' : (activeAnalysis.analysis.commercial_score >= 50 ? '#f59e0b' : '#ef4444')
                }} />
              </div>
            </div>
          </div>

          {/* Rejection / Flaws Alert */}
          {activeAnalysis.analysis.rejection_reasons?.length > 0 && (
            <div style={{
              background: '#450a0a',
              border: '1px solid #dc2626',
              borderRadius: '8px',
              padding: '12px 14px',
              marginBottom: '16px',
              fontSize: '12px',
              color: '#fca5a5'
            }}>
              <strong style={{ color: '#ef4444', display: 'block', marginBottom: '4px' }}>
                ⛔ Disqualifying Reasons ({activeAnalysis.analysis.rejection_reasons.length}):
              </strong>
              <ul style={{ margin: 0, paddingLeft: '18px', lineHeight: 1.5 }}>
                {activeAnalysis.analysis.rejection_reasons.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Requirements Checklist Tabs/Cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '12px', marginBottom: '18px' }}>
            {/* Satisfied */}
            <div style={{ background: '#09090b', border: '1px solid #14532d', borderRadius: '8px', padding: '12px' }}>
              <span style={{ fontSize: '11px', color: '#86efac', fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '4px', marginBottom: '8px' }}>
                ✅ Satisfied Criteria ({activeAnalysis.analysis.satisfied_requirements?.length || 0})
              </span>
              <ul style={{ margin: 0, paddingLeft: '16px', fontSize: '11px', color: '#cbd5e1', lineHeight: 1.4 }}>
                {activeAnalysis.analysis.satisfied_requirements?.map((req, i) => (
                  <li key={i} style={{ marginBottom: '4px' }}>{req}</li>
                ))}
              </ul>
            </div>

            {/* Unverified / Missing */}
            <div style={{ background: '#09090b', border: '1px solid #78350f', borderRadius: '8px', padding: '12px' }}>
              <span style={{ fontSize: '11px', color: '#fde68a', fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '4px', marginBottom: '8px' }}>
                ❓ Unverified / Missing Info ({activeAnalysis.analysis.unverified_requirements?.length || 0})
              </span>
              {activeAnalysis.analysis.unverified_requirements?.length > 0 ? (
                <ul style={{ margin: 0, paddingLeft: '16px', fontSize: '11px', color: '#fed7aa', lineHeight: 1.4 }}>
                  {activeAnalysis.analysis.unverified_requirements.map((req, i) => (
                    <li key={i} style={{ marginBottom: '4px' }}>{req}</li>
                  ))}
                </ul>
              ) : (
                <span style={{ fontSize: '11px', color: '#71717a' }}>No unverified requirements.</span>
              )}
            </div>
          </div>

          {/* Extracted Posting Metadata Strip */}
          <div style={{
            background: '#0c0a09',
            border: '1px solid #292524',
            borderRadius: '8px',
            padding: '14px',
            marginBottom: '18px'
          }}>
            <span style={{ fontSize: '12px', fontWeight: 'bold', color: '#38bdf8', display: 'block', marginBottom: '8px' }}>
              📋 Extracted Posting Metadata (Ready for Social Uploaders)
            </span>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '10px', fontSize: '12px' }}>
              <div>
                <span style={{ color: '#71717a', fontSize: '11px' }}>Mandatory Hashtags:</span>
                <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap', marginTop: '4px' }}>
                  {activeAnalysis.posting_metadata?.hashtags?.length > 0 ? (
                    activeAnalysis.posting_metadata.hashtags.map((h, i) => (
                      <span key={i} style={{ background: '#1e293b', color: '#38bdf8', padding: '2px 6px', borderRadius: '4px', fontSize: '11px' }}>
                        {h}
                      </span>
                    ))
                  ) : (
                    <span style={{ color: '#52525b', fontSize: '11px' }}>None required</span>
                  )}
                </div>
              </div>

              <div>
                <span style={{ color: '#71717a', fontSize: '11px' }}>Mentions & Disclosures:</span>
                <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap', marginTop: '4px' }}>
                  {activeAnalysis.posting_metadata?.required_mentions?.length > 0 ? (
                    activeAnalysis.posting_metadata.required_mentions.map((m, i) => (
                      <span key={i} style={{ background: '#1e1b4b', color: '#c7d2fe', padding: '2px 6px', borderRadius: '4px', fontSize: '11px' }}>
                        {m}
                      </span>
                    ))
                  ) : (
                    <span style={{ color: '#52525b', fontSize: '11px' }}>None</span>
                  )}
                </div>
              </div>

              <div>
                <span style={{ color: '#71717a', fontSize: '11px' }}>Call to Action (CTA):</span>
                <div style={{ color: '#f5f5f4', marginTop: '4px', fontSize: '11px' }}>
                  {activeAnalysis.posting_metadata?.cta || 'None specified'}
                </div>
              </div>
            </div>
          </div>

          {/* Recommendation & Action Controls */}
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            borderTop: '1px solid #27272a',
            paddingTop: '16px',
            flexWrap: 'wrap',
            gap: '12px'
          }}>
            <div style={{ maxWidth: '600px', fontSize: '12px', color: '#d4d4d8' }}>
              <span style={{ color: '#38bdf8', fontWeight: 'bold' }}>Recommendation: </span>
              {activeAnalysis.analysis.recommendation}
            </div>

            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                type="button"
                onClick={handleSaveCampaign}
                disabled={savingCampaign}
                style={{
                  background: '#22c55e',
                  color: '#052e16',
                  border: 'none',
                  borderRadius: '6px',
                  padding: '10px 18px',
                  fontSize: '13px',
                  fontWeight: 'bold',
                  cursor: savingCampaign ? 'not-allowed' : 'pointer'
                }}
              >
                {savingCampaign ? 'Saving...' : '💾 Save to Campaign Library'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* SECTION 3: Campaign Library & Approval Center */}
      <div style={{
        background: '#18181b',
        border: '1px solid #27272a',
        borderRadius: '12px',
        padding: '24px',
        boxShadow: '0 4px 16px rgba(0,0,0,0.3)'
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px', flexWrap: 'wrap', gap: '12px' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '18px', color: '#fff' }}>
              📂 Campaign Intelligence Library ({campaigns.length})
            </h3>
            <p style={{ margin: '4px 0 0 0', fontSize: '12px', color: '#a1a1aa' }}>
              Audited marketplace briefs with eligibility reports, posting instructions, and publishing metadata.
            </p>
          </div>

          {/* Search Input */}
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search campaigns..."
              style={{
                background: '#09090b',
                border: '1px solid #3f3f46',
                color: '#fff',
                padding: '6px 12px',
                borderRadius: '6px',
                fontSize: '12px'
              }}
            />
            <button
              type="button"
              onClick={fetchCampaigns}
              style={{ background: '#27272a', border: 'none', color: '#cbd5e1', padding: '6px 10px', borderRadius: '6px', fontSize: '12px', cursor: 'pointer' }}
            >
              🔄
            </button>
          </div>
        </div>

        {/* Filter Tab Bar */}
        <div style={{ display: 'flex', gap: '8px', marginBottom: '16px', borderBottom: '1px solid #27272a', paddingBottom: '10px', flexWrap: 'wrap' }}>
          {[
            { id: 'ALL', label: `All (${campaigns.filter(c => c.status !== 'ARCHIVED').length})` },
            { id: 'APPROVED', label: `Approved (${campaigns.filter(c => c.status === 'APPROVED').length})` },
            { id: 'NEEDS_INFO', label: `Needs Info (${campaigns.filter(c => c.status === 'NEEDS_INFO').length})` },
            { id: 'REJECTED', label: `Rejected (${campaigns.filter(c => c.status === 'REJECTED').length})` },
            { id: 'ARCHIVED', label: `Archived (${campaigns.filter(c => c.status === 'ARCHIVED').length})` }
          ].map(tab => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setSelectedStatusTab(tab.id)}
              style={{
                background: selectedStatusTab === tab.id ? '#0284c7' : '#27272a',
                color: selectedStatusTab === tab.id ? '#ffffff' : '#a1a1aa',
                border: 'none',
                borderRadius: '6px',
                padding: '6px 14px',
                fontSize: '12px',
                fontWeight: selectedStatusTab === tab.id ? 'bold' : 'normal',
                cursor: 'pointer'
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Campaign Cards List */}
        {loadingCampaigns ? (
          <div style={{ textAlign: 'center', padding: '30px', color: '#a1a1aa', fontSize: '13px' }}>
            Loading campaign repository...
          </div>
        ) : filteredCampaigns.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '40px', color: '#71717a', fontSize: '13px' }}>
            No campaigns found matching filter. Paste a campaign brief above to analyze your first campaign!
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '14px' }}>
            {filteredCampaigns.map(camp => {
              const badge = getDecisionBadge(camp.status)
              return (
                <div
                  key={camp.campaign_id}
                  style={{
                    background: '#09090b',
                    border: `1.5px solid ${badge.border}`,
                    borderRadius: '10px',
                    padding: '16px',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                    boxShadow: '0 4px 12px rgba(0,0,0,0.2)'
                  }}
                >
                  <div>
                    {/* Header badge & platform */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                      <span style={{
                        background: badge.bg,
                        color: badge.text,
                        border: `1px solid ${badge.border}`,
                        fontSize: '10px',
                        fontWeight: 'bold',
                        padding: '2px 8px',
                        borderRadius: '4px'
                      }}>
                        {camp.manual_override ? `👤 MANUAL ${badge.label}` : badge.label}
                      </span>
                      <span style={{ fontSize: '11px', color: '#71717a' }}>
                        {camp.source_platform}
                      </span>
                    </div>

                    <h4 style={{ margin: '0 0 6px 0', fontSize: '15px', color: '#ffffff', lineHeight: 1.35 }}>
                      {camp.title}
                    </h4>

                    {/* Stats pill row */}
                    <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginBottom: '10px', fontSize: '11px' }}>
                      <span style={{ background: '#1e293b', color: '#93c5fd', padding: '2px 6px', borderRadius: '4px' }}>
                        🎯 Score: {camp.analysis?.overall_score || 0}/100
                      </span>
                      {camp.commercial_details?.cpm_max && (
                        <span style={{ background: '#1e1b4b', color: '#a5b4fc', padding: '2px 6px', borderRadius: '4px' }}>
                          💵 ${camp.commercial_details.cpm_max} CPM
                        </span>
                      )}
                      {camp.content_requirements?.niche?.length > 0 && (
                        <span style={{ background: '#27272a', color: '#d4d4d8', padding: '2px 6px', borderRadius: '4px' }}>
                          🎮 {camp.content_requirements.niche[0]}
                        </span>
                      )}
                    </div>

                    {/* Rejection / Note snippet */}
                    {camp.analysis?.rejection_reasons?.length > 0 && (
                      <div style={{ fontSize: '11px', color: '#f87171', marginBottom: '10px', lineHeight: 1.35 }}>
                        ⛔ {camp.analysis.rejection_reasons[0]}
                      </div>
                    )}

                    {camp.posting_metadata?.hashtags?.length > 0 && (
                      <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap', marginBottom: '10px' }}>
                        {camp.posting_metadata.hashtags.slice(0, 3).map((h, i) => (
                          <span key={i} style={{ fontSize: '10px', color: '#38bdf8' }}>{h}</span>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Card Actions */}
                  <div style={{ display: 'flex', gap: '6px', borderTop: '1px solid #1f2937', paddingTop: '10px', marginTop: '10px' }}>
                    <button
                      type="button"
                      onClick={() => setSelectedCampaign(camp)}
                      style={{
                        flex: 1,
                        background: '#0284c7',
                        color: '#fff',
                        border: 'none',
                        borderRadius: '4px',
                        padding: '6px',
                        fontSize: '11px',
                        fontWeight: 'bold',
                        cursor: 'pointer'
                      }}
                    >
                      👁 View Details
                    </button>
                    {camp.status !== 'APPROVED' ? (
                      <button
                        type="button"
                        onClick={() => handleVerdictOverride(camp.campaign_id, 'APPROVED')}
                        disabled={actionInProgress}
                        style={{ background: '#15803d', color: '#fff', border: 'none', borderRadius: '4px', padding: '6px 10px', fontSize: '11px', fontWeight: 'bold', cursor: 'pointer' }}
                        title="Override: Force Approve"
                      >
                        ✅
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => handleVerdictOverride(camp.campaign_id, 'REJECTED')}
                        disabled={actionInProgress}
                        style={{ background: '#991b1b', color: '#fff', border: 'none', borderRadius: '4px', padding: '6px 10px', fontSize: '11px', fontWeight: 'bold', cursor: 'pointer' }}
                        title="Override: Force Reject"
                      >
                        ❌
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => handleArchive(camp.campaign_id)}
                      disabled={actionInProgress}
                      style={{ background: '#27272a', color: '#a1a1aa', border: 'none', borderRadius: '4px', padding: '6px 8px', fontSize: '11px', cursor: 'pointer' }}
                      title="Archive campaign"
                    >
                      📦
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* DETAIL MODAL / DRAWER */}
      {selectedCampaign && (
        <div style={{
          position: 'fixed',
          top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.85)',
          zIndex: 9999,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '20px'
        }}>
          <div style={{
            background: '#18181b',
            border: '1px solid #3f3f46',
            borderRadius: '12px',
            padding: '24px',
            maxWidth: '800px',
            width: '100%',
            maxHeight: '90vh',
            overflowY: 'auto',
            boxShadow: '0 20px 50px rgba(0,0,0,0.8)'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                <span style={{
                  fontSize: '11px',
                  fontWeight: 'bold',
                  padding: '2px 8px',
                  borderRadius: '4px',
                  background: getDecisionBadge(selectedCampaign.status).bg,
                  color: getDecisionBadge(selectedCampaign.status).text,
                  border: `1px solid ${getDecisionBadge(selectedCampaign.status).border}`
                }}>
                  {selectedCampaign.status}
                </span>
                <span style={{ fontSize: '12px', color: '#9ca3af' }}>
                  ID: {selectedCampaign.campaign_id}
                </span>
              </div>
              <button
                type="button"
                onClick={() => {
                  setSelectedCampaign(null)
                  setIsEditingMetadata(false)
                }}
                style={{ background: '#27272a', border: 'none', color: '#fff', width: '28px', height: '28px', borderRadius: '50%', cursor: 'pointer', fontWeight: 'bold' }}
              >
                ✕
              </button>
            </div>

            <h3 style={{ margin: '0 0 8px 0', fontSize: '20px', color: '#fff' }}>
              {selectedCampaign.title}
            </h3>
            <div style={{ fontSize: '12px', color: '#a1a1aa', marginBottom: '16px' }}>
              Source Platform: <strong>{selectedCampaign.source_platform}</strong>
              {selectedCampaign.campaign_url && (
                <a href={selectedCampaign.campaign_url} target="_blank" rel="noreferrer" style={{ marginLeft: '12px', color: '#38bdf8' }}>
                  Open Link ↗
                </a>
              )}
            </div>

            {/* Dimension Breakdown Bar */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '8px', marginBottom: '16px', background: '#09090b', padding: '10px', borderRadius: '8px' }}>
              <div style={{ textAlign: 'center' }}>
                <span style={{ fontSize: '10px', color: '#71717a' }}>OVERALL</span>
                <div style={{ fontSize: '16px', fontWeight: 'bold', color: '#fff' }}>{selectedCampaign.analysis?.overall_score || 0}%</div>
              </div>
              <div style={{ textAlign: 'center' }}>
                <span style={{ fontSize: '10px', color: '#71717a' }}>ELIGIBILITY</span>
                <div style={{ fontSize: '16px', fontWeight: 'bold', color: '#38bdf8' }}>{selectedCampaign.analysis?.eligibility_score || 0}%</div>
              </div>
              <div style={{ textAlign: 'center' }}>
                <span style={{ fontSize: '10px', color: '#71717a' }}>NICHE FIT</span>
                <div style={{ fontSize: '16px', fontWeight: 'bold', color: '#4ade80' }}>{selectedCampaign.analysis?.niche_compatibility_score || 0}%</div>
              </div>
              <div style={{ textAlign: 'center' }}>
                <span style={{ fontSize: '10px', color: '#71717a' }}>FEASIBILITY</span>
                <div style={{ fontSize: '16px', fontWeight: 'bold', color: '#f59e0b' }}>{selectedCampaign.analysis?.production_feasibility_score || 0}%</div>
              </div>
            </div>

            {/* Disqualifiers or Checklists */}
            {selectedCampaign.analysis?.rejection_reasons?.length > 0 && (
              <div style={{ background: '#450a0a', border: '1px solid #dc2626', borderRadius: '6px', padding: '10px', marginBottom: '14px', fontSize: '12px', color: '#fca5a5' }}>
                <strong>⛔ Disqualifying Reasons:</strong>
                <ul style={{ margin: '4px 0 0 18px', padding: 0 }}>
                  {selectedCampaign.analysis.rejection_reasons.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Posting Metadata (Editable) */}
            <div style={{ background: '#09090b', border: '1px solid #27272a', borderRadius: '8px', padding: '14px', marginBottom: '16px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <strong style={{ fontSize: '13px', color: '#38bdf8' }}>
                  🚀 Social Posting & Publishing Metadata
                </strong>
                {!isEditingMetadata ? (
                  <button
                    type="button"
                    onClick={() => {
                      setMetadataFormData(selectedCampaign.posting_metadata || {})
                      setIsEditingMetadata(true)
                    }}
                    style={{ background: '#1e293b', border: '1px solid #334155', color: '#93c5fd', padding: '4px 10px', borderRadius: '4px', fontSize: '11px', cursor: 'pointer' }}
                  >
                    ✏️ Edit Metadata
                  </button>
                ) : (
                  <div style={{ display: 'flex', gap: '6px' }}>
                    <button
                      type="button"
                      onClick={() => setIsEditingMetadata(false)}
                      style={{ background: '#3f3f46', border: 'none', color: '#fff', padding: '4px 8px', borderRadius: '4px', fontSize: '11px', cursor: 'pointer' }}
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={handleSaveMetadata}
                      disabled={updatingMetadata}
                      style={{ background: '#22c55e', border: 'none', color: '#052e16', padding: '4px 10px', borderRadius: '4px', fontSize: '11px', fontWeight: 'bold', cursor: 'pointer' }}
                    >
                      {updatingMetadata ? 'Saving...' : 'Save'}
                    </button>
                  </div>
                )}
              </div>

              {isEditingMetadata ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '12px' }}>
                  <div>
                    <label style={{ fontSize: '11px', color: '#9ca3af' }}>Hashtags (comma separated):</label>
                    <input
                      type="text"
                      value={(metadataFormData.hashtags || []).join(', ')}
                      onChange={(e) => setMetadataFormData({
                        ...metadataFormData,
                        hashtags: e.target.value.split(',').map(s => s.trim()).filter(Boolean)
                      })}
                      style={{ width: '100%', boxSizing: 'border-box', background: '#18181b', border: '1px solid #3f3f46', color: '#fff', padding: '6px', borderRadius: '4px' }}
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: '11px', color: '#9ca3af' }}>Required Mentions (comma separated):</label>
                    <input
                      type="text"
                      value={(metadataFormData.required_mentions || []).join(', ')}
                      onChange={(e) => setMetadataFormData({
                        ...metadataFormData,
                        required_mentions: e.target.value.split(',').map(s => s.trim()).filter(Boolean)
                      })}
                      style={{ width: '100%', boxSizing: 'border-box', background: '#18181b', border: '1px solid #3f3f46', color: '#fff', padding: '6px', borderRadius: '4px' }}
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: '11px', color: '#9ca3af' }}>Call to Action (CTA):</label>
                    <input
                      type="text"
                      value={metadataFormData.cta || ''}
                      onChange={(e) => setMetadataFormData({ ...metadataFormData, cta: e.target.value })}
                      style={{ width: '100%', boxSizing: 'border-box', background: '#18181b', border: '1px solid #3f3f46', color: '#fff', padding: '6px', borderRadius: '4px' }}
                    />
                  </div>
                </div>
              ) : (
                <div style={{ fontSize: '12px', color: '#cbd5e1', lineHeight: 1.5 }}>
                  <div>
                    <span style={{ color: '#71717a' }}>Hashtags: </span>
                    {selectedCampaign.posting_metadata?.hashtags?.join(' ') || 'None'}
                  </div>
                  <div>
                    <span style={{ color: '#71717a' }}>Mentions: </span>
                    {selectedCampaign.posting_metadata?.required_mentions?.join(' ') || 'None'}
                  </div>
                  <div>
                    <span style={{ color: '#71717a' }}>CTA: </span>
                    {selectedCampaign.posting_metadata?.cta || 'None'}
                  </div>
                  <div style={{ marginTop: '8px', padding: '8px', background: '#18181b', borderRadius: '4px', borderLeft: '3px solid #0284c7', fontSize: '11px' }}>
                    <strong style={{ color: '#38bdf8' }}>Future Publishing Preview:</strong>
                    <div style={{ color: '#f5f5f4', marginTop: '4px', fontStyle: 'italic' }}>
                      "Check out this viral moment! {selectedCampaign.posting_metadata?.cta || ''} {selectedCampaign.posting_metadata?.hashtags?.join(' ')} {selectedCampaign.posting_metadata?.required_mentions?.join(' ')}"
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Original Brief Collapsible */}
            <details style={{ background: '#09090b', padding: '10px', borderRadius: '6px', border: '1px solid #27272a', marginBottom: '16px' }}>
              <summary style={{ cursor: 'pointer', fontSize: '12px', color: '#a1a1aa', fontWeight: 'bold' }}>
                📄 View Original Campaign Brief Text
              </summary>
              <pre style={{ margin: '8px 0 0 0', whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontSize: '11px', color: '#d4d4d8', background: '#121215', padding: '10px', borderRadius: '4px' }}>
                {selectedCampaign.raw_brief}
              </pre>
            </details>

            {/* Action Buttons in Modal */}
            <div style={{ display: 'flex', gap: '8px', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid #27272a', paddingTop: '14px', flexWrap: 'wrap' }}>
              <div style={{ display: 'flex', gap: '8px' }}>
                <button
                  type="button"
                  onClick={() => handleVerdictOverride(selectedCampaign.campaign_id, 'APPROVED')}
                  disabled={actionInProgress}
                  style={{ background: '#15803d', color: '#fff', border: 'none', padding: '8px 14px', borderRadius: '6px', fontSize: '12px', fontWeight: 'bold', cursor: 'pointer' }}
                >
                  ✅ Force Approve
                </button>
                <button
                  type="button"
                  onClick={() => handleVerdictOverride(selectedCampaign.campaign_id, 'REJECTED')}
                  disabled={actionInProgress}
                  style={{ background: '#991b1b', color: '#fff', border: 'none', padding: '8px 14px', borderRadius: '6px', fontSize: '12px', fontWeight: 'bold', cursor: 'pointer' }}
                >
                  ❌ Force Reject
                </button>
                {selectedCampaign.manual_override && (
                  <button
                    type="button"
                    onClick={() => handleVerdictOverride(selectedCampaign.campaign_id, 'RESET')}
                    disabled={actionInProgress}
                    style={{ background: 'transparent', border: '1px solid #4b5563', color: '#a1a1aa', padding: '8px 12px', borderRadius: '6px', fontSize: '12px', cursor: 'pointer' }}
                  >
                    ↺ Reset to AI
                  </button>
                )}
              </div>

              <div style={{ display: 'flex', gap: '8px' }}>
                <button
                  type="button"
                  onClick={() => handleReanalyze(selectedCampaign.campaign_id)}
                  disabled={actionInProgress}
                  style={{ background: '#0284c7', color: '#fff', border: 'none', padding: '8px 14px', borderRadius: '6px', fontSize: '12px', fontWeight: 'bold', cursor: 'pointer' }}
                >
                  🔄 Re-Analyze
                </button>
                <button
                  type="button"
                  onClick={() => handleArchive(selectedCampaign.campaign_id)}
                  disabled={actionInProgress}
                  style={{ background: '#27272a', color: '#f87171', border: 'none', padding: '8px 14px', borderRadius: '6px', fontSize: '12px', cursor: 'pointer' }}
                >
                  📦 Archive
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

