import React, { useState, useMemo, useEffect } from 'react';

const BACKEND_BASE = 'http://localhost:8000';

const sampleScript = {
  "title": "Job Interview English - Shadowing 01",
  "youtube": {
    "title": "Job Interview English Shadowing Practice | Speak Along",
    "title_alternatives": [
      "Answer Interview Questions in English | Shadowing Practice",
      "Speak Confidently in Job Interviews | English Shadowing",
      "Can You Answer These Interview Questions in English?"
    ],
    "description": "English shadowing practice for job interviews. Listen, repeat aloud, and build the confidence to speak clearly.\n\nThis lesson is for English learners at A2 to B2 level who want to sound natural in an interview. You will practice greetings and small talk, talking about your experience, answering common questions, discussing strengths and weaknesses, asking questions, handling difficult moments, negotiating, and writing a follow-up email.\n\nHow to use this video: listen to each sentence, repeat it out loud, copy the tone and rhythm, then watch again on another day.\n\n{{CHAPTERS}}\n\nSubscribe for a new English shadowing lesson every week. Comment this sentence to show you finished: \"I'm ready for my interview.\"\n\nThis video is for English learning practice.\n\n#EnglishShadowing #JobInterviewEnglish #SpeakEnglish",
    "tags": [
      "english shadowing practice",
      "job interview english",
      "english interview questions",
      "english sentences for job interview",
      "shadowing english",
      "speak english confidently",
      "english speaking practice",
      "learn english",
      "english conversation practice",
      "interview english phrases",
      "business english",
      "english for work",
      "english listening and speaking",
      "repeat after me english",
      "english fluency practice",
      "common interview answers english",
      "improve english speaking",
      "english pronunciation practice",
      "english beginners"
    ],
    "hashtags": ["#EnglishShadowing", "#JobInterviewEnglish", "#SpeakEnglish"],
    "thumbnail_text": "SPEAK IN INTERVIEWS",
    "pinned_comment": "If you finished the lesson, comment: \"I'm ready for my interview.\" And tell me, which topic should we practice next?",
    "playlist": "English Shadowing Practice: Work and Career",
    "category": "Education",
    "language": "en",
    "made_for_kids": false
  },
  "segments": [
    { "id": "hook_01", "type": "narration", "text": "Have you ever known the perfect answer, but forgotten it when the interviewer asked the question?" },
    { "id": "hook_02", "type": "narration", "text": "Today, you'll practice speaking clearly and calmly in a job interview, one sentence at a time." },
    { "id": "welcome_01", "type": "narration", "text": "Hello everyone, and welcome back to Shadow English Daily. Today we're practicing job interview English." },
    { "id": "howto_02", "type": "narration", "text": "Don't worry about mistakes. This is practice, not a test. Ready? Let's begin." },

    { "id": "p1_title", "type": "section_title", "chapter": true, "text": "Part 1: Greetings and Small Talk", "spoken": "Part one. Greetings and small talk." },
    { "id": "p1_intro_01", "type": "narration", "text": "The first minute of an interview matters. A warm, simple greeting helps both of you relax." },
    { "id": "p1_01", "type": "shadow", "text": "Hello, it's nice to meet you." },
    { "id": "p1_02", "type": "shadow", "text": "Thank you for inviting me today." },
    {
      "id": "p1_03",
      "type": "shadow_pair",
      "lines": [
        { "voice": "speaker_a", "text": "How was your trip here today?" },
        { "voice": "speaker_b", "text": "It was easy, thank you. I arrived a few minutes early." }
      ]
    },
    { "id": "p1_free01", "type": "free_answer", "text": "How do you usually greet someone you meet for the first time?" },

    { "id": "p2_title", "type": "section_title", "chapter": true, "text": "Part 2: Talking About Your Experience", "spoken": "Part two. Talking about your experience." },
    { "id": "p2_intro_01", "type": "narration", "text": "Excellent. Now let's practice talking about your work. Instead of saying, I did many things, you can say, I was responsible for managing the schedule." },
    { "id": "p2_01", "type": "shadow", "text": "I've worked in customer service for three years.", "spoken": "I've worked in customer service for three years." },
    { "id": "p2_02", "type": "shadow", "text": "In my last job, I managed a team of 5.", "spoken": "In my last job, I managed a team of five." },

    { "id": "outro_01", "type": "narration", "text": "Excellent work. Keep practicing, and most importantly, keep speaking English." }
  ]
};

export default function EnglishShadowingStudio() {
  const [scriptJson, setScriptJson] = useState(JSON.stringify(sampleScript, null, 2));
  const [loading, setLoading] = useState(false);
  const [exportingMeta, setExportingMeta] = useState(false);
  const [progress, setProgress] = useState(0);
  const [statusText, setStatusText] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  const [result, setResult] = useState(null);
  const [formatSuccess, setFormatSuccess] = useState(false);
  const [showMetaPreview, setShowMetaPreview] = useState(false);

  // YouTube Channel States
  const [ytChannel, setYtChannel] = useState(null);
  const [connectingChannel, setConnectingChannel] = useState(false);

  const fetchChannelStatus = async () => {
    try {
      const resp = await fetch(`${BACKEND_BASE}/api/shadowing/youtube/status`);
      if (resp.ok) {
        const data = await resp.json();
        setYtChannel(data.auth || null);
      }
    } catch (_) {}
  };

  useEffect(() => {
    fetchChannelStatus();
  }, []);

  const handleConnectChannel = async () => {
    setConnectingChannel(true);
    setErrorMsg('');
    try {
      const resp = await fetch(`${BACKEND_BASE}/api/shadowing/youtube/connect`, { method: 'POST' });
      const data = await resp.json();
      if (resp.ok && data.auth) {
        setYtChannel(data.auth);
      } else {
        setErrorMsg(data.detail || 'Channel connection failed');
      }
    } catch (e) {
      setErrorMsg('Error connecting channel: ' + e.message);
    } finally {
      setConnectingChannel(false);
      fetchChannelStatus();
    }
  };

  // Compute live validation stats from scriptJson
  const scriptStats = useMemo(() => {
    try {
      const parsed = JSON.parse(scriptJson.trim());
      const segments = Array.isArray(parsed.segments) ? parsed.segments : (Array.isArray(parsed) ? parsed : []);
      const shadowCount = segments.filter(s => s.type === 'shadow' || s.type === 'shadow_pair').length;
      
      // Estimated duration: ~7-9s per shadow repeat + 4s per narration
      let estSec = 0;
      segments.forEach(s => {
        if (s.type === 'narration') estSec += 5;
        else if (s.type === 'section_title') estSec += 4;
        else if (s.type === 'shadow') estSec += ((s.repeat || 2) * 8);
        else if (s.type === 'shadow_pair') estSec += ((s.lines ? s.lines.length : 2) * (s.repeat || 2) * 7);
        else if (s.type === 'free_answer') estSec += 12;
      });

      const yt = (parsed.youtube && typeof parsed.youtube === 'object') ? parsed.youtube : null;
      const ytTitle = yt && yt.title ? yt.title : '';
      const ytTags = yt && Array.isArray(yt.tags) ? yt.tags : [];
      const ytTagsLength = ytTags.join(',').length;

      // Extract chapters
      const chapters = [{ time: "00:00", title: "Intro" }];
      let chapSec = 0;
      segments.forEach(s => {
        if (s.type === 'section_title' && s.chapter) {
          const m = Math.floor(chapSec / 60);
          const sec = Math.floor(chapSec % 60);
          chapters.push({
            time: `${m < 10 ? '0' : ''}${m}:${sec < 10 ? '0' : ''}${sec}`,
            title: s.text
          });
        }
        if (s.type === 'narration') chapSec += 5;
        else if (s.type === 'section_title') chapSec += 4;
        else if (s.type === 'shadow') chapSec += ((s.repeat || 2) * 8);
        else if (s.type === 'shadow_pair') chapSec += ((s.lines ? s.lines.length : 2) * (s.repeat || 2) * 7);
        else if (s.type === 'free_answer') chapSec += 12;
      });

      const chaptersTxt = chapters.map(c => `${c.time} ${c.title}`).join('\n');
      const descPreview = yt && yt.description ? yt.description.replace('{{CHAPTERS}}', chaptersTxt) : '';

      return {
        valid: true,
        segmentsCount: segments.length,
        shadowCount,
        estimatedDurationMinutes: (estSec / 60).toFixed(1),
        yt,
        ytTitle,
        ytTitleLen: ytTitle.length,
        ytTagsCount: ytTags.length,
        ytTagsLen: ytTagsLength,
        chapters,
        chaptersTxt,
        descPreview,
        descLen: descPreview.length,
        titleWarn: ytTitle.length > 70,
        titleCapsWarn: ytTitle.length > 0 && ytTitle === ytTitle.toUpperCase() && /[A-Z]/.test(ytTitle),
        tagsWarn: ytTagsLength > 450,
        descWarn: descPreview.length > 5000,
      };
    } catch (e) {
      return { valid: false, error: e.message };
    }
  }, [scriptJson]);

  const tryRepairJson = (raw) => {
    // 1. Direct parse
    try {
      return { parsed: JSON.parse(raw), repaired: false };
    } catch (_) {}

    // 2. Intelligent regex fixes for common LLM copy/paste errors
    let fixed = raw
      // Normalize smart quotes
      .replace(/[\u201C\u201D]/g, '"')
      .replace(/[\u2018\u2019]/g, "'")
      // Python booleans / None
      .replace(/:\s*True\b/g, ': true')
      .replace(/:\s*False\b/g, ': false')
      .replace(/:\s*None\b/g, ': null')
      // Remove JS/JSON single-line comments
      .replace(/\/\/[^\n\r]*/g, '')
      // Fix missing comma between consecutive objects: } {
      .replace(/\}\s*[\r\n]+\s*\{/g, '},\n{')
      // Fix stray duplicate closing brace lines: e.g. '}\n  },' -> '},'
      .replace(/\}\s*,\s*[\r\n]+\s*\},/g, '},')
      .replace(/\}\s*[\r\n]+\s*\},/g, '},')
      // Fix trailing comma before } or ]
      .replace(/,\s*([\}\]])/g, '$1');

    try {
      return { parsed: JSON.parse(fixed), repaired: true };
    } catch (err) {
      // Find line number of failure
      let lineHint = '';
      const match = err.message.match(/position\s+(\d+)/i);
      if (match) {
        const charPos = parseInt(match[1], 10);
        const upToChar = fixed.substring(0, charPos);
        const line = upToChar.split('\n').length;
        lineHint = ` around line ${line}`;
      }
      throw new Error(`${err.message}${lineHint}`);
    }
  };

  const handleFormatJson = () => {
    try {
      const { parsed, repaired } = tryRepairJson(scriptJson.trim());
      setScriptJson(JSON.stringify(parsed, null, 2));
      setErrorMsg('');
      setFormatSuccess(repaired ? 'repaired' : 'formatted');
      setTimeout(() => setFormatSuccess(null), 2500);
    } catch (e) {
      setErrorMsg('Cannot format JSON: ' + e.message);
    }
  };

  const handleValidateJson = () => {
    try {
      const parsed = JSON.parse(scriptJson.trim());
      if (!parsed.youtube) {
        throw new Error("Missing required top-level key 'youtube'.");
      }
      setErrorMsg('');
      setShowMetaPreview(true);
      alert(`✅ Valid Script & YouTube Metadata!\n- Title: "${parsed.title}"\n- YouTube Title: "${parsed.youtube.title}"\n- Segments: ${parsed.segments ? parsed.segments.length : 0}\n- Chapters: ${scriptStats.chapters ? scriptStats.chapters.length : 0}`);
    } catch (e) {
      setErrorMsg('Validation Error: ' + e.message);
    }
  };

  const handleKeyDown = (e) => {
    // Tab key inserts 2 spaces
    if (e.key === 'Tab') {
      e.preventDefault();
      const start = e.target.selectionStart;
      const end = e.target.selectionEnd;
      const val = e.target.value;
      setScriptJson(val.substring(0, start) + '  ' + val.substring(end));
      setTimeout(() => {
        e.target.selectionStart = e.target.selectionEnd = start + 2;
      }, 0);
    }
    // Alt + Shift + F formats JSON
    if (e.altKey && e.shiftKey && (e.key === 'f' || e.key === 'F')) {
      e.preventDefault();
      handleFormatJson();
    }
  };

  const handleLoadSample = () => {
    setScriptJson(JSON.stringify(sampleScript, null, 2));
    setErrorMsg('');
  };

  const setKokoroVoice = (teacherVoice) => {
    try {
      const parsed = JSON.parse(scriptJson);
      parsed.settings = parsed.settings || {};
      parsed.settings.voice_teacher = teacherVoice;
      setScriptJson(JSON.stringify(parsed, null, 2));
    } catch (e) {}
  };

  const setKokoroSpeed = (spd) => {
    try {
      const parsed = JSON.parse(scriptJson);
      parsed.settings = parsed.settings || {};
      parsed.settings.speed = spd;
      setScriptJson(JSON.stringify(parsed, null, 2));
    } catch (e) {}
  };

  const handleExportMetadata = async () => {
    setErrorMsg('');
    let parsed;
    try {
      parsed = JSON.parse(scriptJson.trim());
    } catch (e) {
      setErrorMsg('JSON Parse Error: Please verify valid JSON syntax. ' + e.message);
      return;
    }

    if (!parsed.youtube) {
      setErrorMsg("Validation Error: Missing required top-level key 'youtube'.");
      return;
    }

    setExportingMeta(true);
    setStatusText('Exporting YouTube metadata and chapters...');
    try {
      const resp = await fetch(`${BACKEND_BASE}/api/shadowing/export-metadata`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ script: parsed })
      });

      if (!resp.ok) {
        let errDetail = 'Failed to export metadata';
        try {
          const errData = await resp.json();
          errDetail = errData.detail || errDetail;
        } catch (_) {
          errDetail = `HTTP ${resp.status}: ${resp.statusText}`;
        }
        throw new Error(errDetail);
      }

      const data = await resp.json();
      setResult({
        video_url: null,
        metadata_url: `${BACKEND_BASE}${data.metadata_url}`,
        description_url: `${BACKEND_BASE}${data.description_url}`,
        tags_url: `${BACKEND_BASE}${data.tags_url}`,
        chapters_url: `${BACKEND_BASE}${data.chapters_url}`,
        timeline_url: `${BACKEND_BASE}/output/${data.title ? data.title.replace(/[^a-zA-Z0-9_-]/g, '_') : 'timeline'}_timeline.json`,
        duration: data.duration_seconds,
        is_metadata_only: true,
      });
      setShowMetaPreview(true);
      setStatusText('YouTube metadata exported successfully!');
    } catch (err) {
      setErrorMsg('Export Error: ' + err.message);
    } finally {
      setExportingMeta(false);
    }
  };

  const handleStartGeneration = async (preview = false) => {
    setErrorMsg('');
    let parsed;
    try {
      parsed = JSON.parse(scriptJson.trim());
    } catch (e) {
      setErrorMsg('JSON Parse Error: Please verify valid JSON syntax. ' + e.message);
      return;
    }

    // Auto-normalize if user pasted just a single segment or an array of segments
    if (Array.isArray(parsed)) {
      parsed = {
        title: "English Shadowing Practice",
        segments: parsed
      };
    } else if (typeof parsed === 'object' && parsed !== null) {
      if (parsed.type && !parsed.segments) {
        parsed = {
          title: "English Shadowing Practice",
          segments: [parsed]
        };
      }
    }

    setLoading(true);
    setProgress(0);
    setStatusText('Submitting script to shadowing renderer...');
    setResult(null);

    try {
      const resp = await fetch(`${BACKEND_BASE}/api/shadowing/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ script: parsed, preview })
      });

      if (!resp.ok) {
        let errDetail = 'Server generation error';
        try {
          const errData = await resp.json();
          errDetail = errData.detail || errDetail;
        } catch (_) {
          errDetail = `HTTP ${resp.status}: ${resp.statusText}`;
        }
        throw new Error(errDetail);
      }

      const data = await resp.json();
      const jobId = data.job_id;

      // Start polling
      let consecutive404Count = 0;
      const pollTimer = setInterval(async () => {
        try {
          const sResp = await fetch(`${BACKEND_BASE}/api/shadowing/jobs/${jobId}`);
          if (sResp.status === 404) {
            consecutive404Count++;
            if (consecutive404Count >= 3) {
              clearInterval(pollTimer);
              setLoading(false);
              setErrorMsg('Backend server reloaded during rendering. Please click "Render" again to start.');
            }
            return;
          }
          consecutive404Count = 0;
          if (!sResp.ok) return;

          const job = await sResp.json();

          if (job.status === 'processing') {
            setProgress(job.progress || 0);
            setStatusText(job.status_text || 'Rendering video frames...');
          } else if (job.status === 'completed') {
            clearInterval(pollTimer);
            setProgress(100);
            setStatusText('Rendering complete!');
            setResult({
              video_url: `${BACKEND_BASE}${job.result.video_url}`,
              srt_url: `${BACKEND_BASE}${job.result.srt_url}`,
              timeline_url: `${BACKEND_BASE}${job.result.timeline_url}`,
              metadata_url: `${BACKEND_BASE}${job.result.metadata_url || '/output/video_metadata.json'}`,
              description_url: `${BACKEND_BASE}${job.result.description_url || '/output/description.txt'}`,
              tags_url: `${BACKEND_BASE}${job.result.tags_url || '/output/tags.txt'}`,
              chapters_url: `${BACKEND_BASE}${job.result.chapters_url || '/output/chapters.txt'}`,
              duration: job.result.duration,
              youtube_url: job.result.youtube_url,
              youtube_upload: job.result.youtube_upload,
              youtube_upload_error: job.result.youtube_upload_error
            });
            setLoading(false);
          } else if (job.status === 'failed') {
            clearInterval(pollTimer);
            setErrorMsg('Rendering failed: ' + job.error);
            setLoading(false);
          }
        } catch (err) {
          console.error('Job polling error:', err);
        }
      }, 700);

    } catch (err) {
      setErrorMsg(`Connection Error: ${err.message}. (Ensure backend server is running on port 8000).`);
      setLoading(false);
    }
  };

  return (
    <div style={{ marginTop: '20px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Banner */}
      <div style={{
        background: 'linear-gradient(135deg, #431407 0%, #9a3412 50%, #c2410c 100%)',
        borderRadius: '14px',
        padding: '24px',
        border: '1px solid rgba(249, 115, 22, 0.3)',
        boxShadow: '0 8px 30px rgba(0,0,0,0.35)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: '16px'
      }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{ fontSize: '26px' }}>🎙️</span>
            <h2 style={{ margin: 0, fontSize: '24px', fontWeight: '800', color: '#fff' }}>
              English Shadowing Video Studio
            </h2>
            <span style={{
              background: '#22c55e',
              color: '#052e16',
              fontSize: '11px',
              fontWeight: 'bold',
              padding: '3px 9px',
              borderRadius: '12px'
            }}>
              ACTIVE
            </span>
          </div>
          <p style={{ margin: '6px 0 0 0', color: '#fed7aa', fontSize: '14px' }}>
            Transform JSON scripts into 1080p English shadowing practice videos with word-level pill highlighting, waveforms, and repetition pauses.
          </p>
        </div>

        <button
          type="button"
          onClick={handleLoadSample}
          style={{
            background: 'rgba(255, 255, 255, 0.15)',
            border: '1px solid rgba(255, 255, 255, 0.3)',
            color: '#fff',
            padding: '8px 16px',
            borderRadius: '8px',
            fontSize: '13px',
            fontWeight: '600',
            cursor: 'pointer',
            transition: 'all 0.2s'
          }}
        >
          Load Sample Script
        </button>
      </div>

      {/* YouTube Channel Integration Bar */}
      <div style={{
        background: '#18181b',
        borderRadius: '12px',
        border: ytChannel && ytChannel.is_target_channel
          ? '1px solid #16a34a'
          : ytChannel && ytChannel.connected
          ? '1px solid #f59e0b'
          : '1px solid #3f3f46',
        padding: '14px 20px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: '12px'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div style={{
            width: '40px',
            height: '40px',
            borderRadius: '50%',
            overflow: 'hidden',
            background: '#27272a',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            border: '2px solid #ef4444'
          }}>
            {ytChannel && ytChannel.thumbnail ? (
              <img src={ytChannel.thumbnail} alt="Channel" style={{ width: '100%', height: '100%' }} />
            ) : (
              <span style={{ fontSize: '20px' }}>📺</span>
            )}
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '13px', fontWeight: '700', color: '#fff' }}>
                Target YouTube Channel:
              </span>
              <a
                href="https://www.youtube.com/@ShadowEnglishDaily-d4z"
                target="_blank"
                rel="noreferrer"
                style={{ color: '#38bdf8', textDecoration: 'none', fontSize: '13px', fontWeight: '600' }}
              >
                @ShadowEnglishDaily-d4z ↗
              </a>
            </div>

            <div style={{ fontSize: '12px', marginTop: '2px', color: '#a1a1aa' }}>
              {ytChannel && ytChannel.connected ? (
                ytChannel.is_target_channel ? (
                  <span style={{ color: '#4ade80', fontWeight: '600' }}>
                    🟢 Connected: {ytChannel.channel_title} ({ytChannel.custom_url})
                  </span>
                ) : (
                  <span style={{ color: '#fbbf24', fontWeight: '600' }}>
                    ⚠️ Currently authorized as: <strong>{ytChannel.channel_title}</strong> ({ytChannel.custom_url}) — Connect @ShadowEnglishDaily-d4z below!
                  </span>
                )
              ) : (
                <span style={{ color: '#f87171' }}>
                  🔴 No YouTube account connected for English Shadowing.
                </span>
              )}
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <button
            type="button"
            disabled={connectingChannel}
            onClick={handleConnectChannel}
            style={{
              background: ytChannel && ytChannel.is_target_channel
                ? '#27272a'
                : 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)',
              color: '#fff',
              border: '1px solid rgba(255,255,255,0.15)',
              borderRadius: '8px',
              padding: '8px 16px',
              fontSize: '12px',
              fontWeight: '600',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px'
            }}
          >
            <span>{connectingChannel ? '⏳ Authorizing...' : ytChannel && ytChannel.is_target_channel ? '🔄 Reconnect Account' : '🔗 Connect @ShadowEnglishDaily-d4z'}</span>
          </button>
        </div>
      </div>

      {/* Main Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))', gap: '20px' }}>
        {/* Editor Box */}
        <div style={{
          background: '#18181b',
          border: '1px solid #27272a',
          borderRadius: '14px',
          padding: '20px',
          display: 'flex',
          flexDirection: 'column',
          gap: '14px'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <label style={{ color: '#e4e4e7', fontWeight: '700', fontSize: '15px' }}>
                Script JSON
              </label>
              <button
                type="button"
                onClick={handleFormatJson}
                title="Format / Prettify JSON (or press Alt+Shift+F)"
                style={{
                  background: formatSuccess ? '#166534' : 'rgba(56, 189, 248, 0.12)',
                  color: formatSuccess ? '#86efac' : '#38bdf8',
                  border: formatSuccess ? '1px solid #22c55e' : '1px solid rgba(56, 189, 248, 0.35)',
                  borderRadius: '6px',
                  padding: '4px 10px',
                  fontSize: '12px',
                  fontWeight: '600',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '5px',
                  transition: 'all 0.2s ease'
                }}
              >
                <span>{formatSuccess ? '✅ Formatted!' : '✨ Format JSON'}</span>
              </button>
            </div>
            <span style={{ color: '#a1a1aa', fontSize: '12px' }}>
              narration • section_title • shadow • dialogue • free_answer
            </span>
          </div>

          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center', background: '#27272a', padding: '8px 12px', borderRadius: '8px' }}>
            <span style={{ fontSize: '12px', color: '#fb923c', fontWeight: 'bold' }}>Kokoro Teacher:</span>
            {['af_heart', 'af_bella', 'af_nicole', 'af_sarah', 'bf_emma'].map(v => (
              <button
                key={v}
                type="button"
                onClick={() => setKokoroVoice(v)}
                style={{
                  background: scriptJson.includes(`"voice_teacher": "${v}"`) ? '#ea580c' : '#3f3f46',
                  color: '#fff',
                  border: 'none',
                  borderRadius: '6px',
                  padding: '3px 8px',
                  fontSize: '11px',
                  fontWeight: '600',
                  cursor: 'pointer'
                }}
              >
                {v}
              </button>
            ))}
            <span style={{ fontSize: '12px', color: '#94a3b8', fontWeight: 'bold', marginLeft: '6px' }}>Speed:</span>
            {[0.80, 0.85, 0.90, 0.95, 1.0].map(s => (
              <button
                key={s}
                type="button"
                onClick={() => setKokoroSpeed(s)}
                style={{
                  background: scriptJson.includes(`"speed": ${s}`) || (s === 0.85 && !scriptJson.includes('"speed":')) ? '#0284c7' : '#3f3f46',
                  color: '#fff',
                  border: 'none',
                  borderRadius: '6px',
                  padding: '3px 8px',
                  fontSize: '11px',
                  fontWeight: '600',
                  cursor: 'pointer'
                }}
              >
                {s === 0.85 ? '0.85x (ESL)' : `${s}x`}
              </button>
            ))}
          </div>

          <textarea
            value={scriptJson}
            onChange={(e) => setScriptJson(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={18}
            placeholder="Paste or write your shadowing script JSON here..."
            style={{
              width: '100%',
              background: '#09090b',
              color: '#f4f4f5',
              fontFamily: 'monospace',
              fontSize: '13px',
              lineHeight: '1.5',
              border: '1px solid #3f3f46',
              borderRadius: '10px',
              padding: '14px',
              resize: 'vertical',
              outline: 'none',
              boxSizing: 'border-box'
            }}
          />

          {/* Bottom Toolbar right below editor */}
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginTop: '-4px',
            flexWrap: 'wrap',
            gap: '10px'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <button
                type="button"
                onClick={handleFormatJson}
                title="Format, prettify & auto-repair JSON (Alt+Shift+F)"
                style={{
                  background: formatSuccess ? '#166534' : 'rgba(56, 189, 248, 0.15)',
                  color: formatSuccess ? '#86efac' : '#38bdf8',
                  border: formatSuccess ? '1px solid #22c55e' : '1px solid #0284c7',
                  borderRadius: '6px',
                  padding: '6px 14px',
                  fontSize: '12px',
                  fontWeight: '600',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  transition: 'all 0.15s ease'
                }}
              >
                <span>
                  {formatSuccess === 'repaired'
                    ? '🛠️ Repaired & Formatted!'
                    : formatSuccess === 'formatted'
                    ? '✅ Formatted!'
                    : '✨ Format / Fix JSON'}
                </span>
              </button>

              <button
                type="button"
                onClick={handleValidateJson}
                title="Verify JSON syntax and segment count"
                style={{
                  background: '#27272a',
                  color: '#d4d4d8',
                  border: '1px solid #3f3f46',
                  borderRadius: '6px',
                  padding: '6px 12px',
                  fontSize: '12px',
                  fontWeight: '500',
                  cursor: 'pointer'
                }}
              >
                🔍 Check Syntax
              </button>
            </div>

            <span style={{ fontSize: '11px', color: '#71717a' }}>
              Pro tip: press <kbd style={{ background: '#27272a', border: '1px solid #3f3f46', padding: '1px 5px', borderRadius: '4px', color: '#e4e4e7' }}>Alt+Shift+F</kbd> or <kbd style={{ background: '#27272a', border: '1px solid #3f3f46', padding: '1px 5px', borderRadius: '4px', color: '#e4e4e7' }}>Tab</kbd> in editor
            </span>
          </div>

          {/* Live Validation & YouTube Metadata Stats */}
          {scriptStats.valid && (
            <div style={{
              background: '#27272a',
              borderRadius: '10px',
              padding: '14px',
              display: 'flex',
              flexDirection: 'column',
              gap: '10px',
              border: '1px solid #3f3f46'
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
                <span style={{ fontSize: '13px', fontWeight: '700', color: '#38bdf8' }}>
                  📊 Script & YouTube Metadata Summary
                </span>
                <span style={{ fontSize: '12px', color: '#a1a1aa' }}>
                  {scriptStats.segmentsCount} segments • {scriptStats.shadowCount} shadow sentences • ~{scriptStats.estimatedDurationMinutes} mins
                </span>
              </div>

              {scriptStats.yt ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '12px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: '#d4d4d8' }}>
                      <strong>Title:</strong> {scriptStats.ytTitle}
                    </span>
                    <span style={{
                      color: scriptStats.titleWarn ? '#f59e0b' : '#10b981',
                      fontWeight: '600'
                    }}>
                      {scriptStats.ytTitleLen}/100 chars {scriptStats.titleWarn ? '(>70 warn)' : ''}
                    </span>
                  </div>

                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: '#d4d4d8' }}>
                      <strong>Tags:</strong> {scriptStats.ytTagsCount} tags
                    </span>
                    <span style={{
                      color: scriptStats.tagsWarn ? '#f59e0b' : '#10b981',
                      fontWeight: '600'
                    }}>
                      {scriptStats.ytTagsLen}/500 chars {scriptStats.tagsWarn ? '(>450 warn)' : ''}
                    </span>
                  </div>

                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: '#d4d4d8' }}>
                      <strong>Chapters:</strong> {scriptStats.chapters.length} chapters (starts with 00:00 Intro)
                    </span>
                    <button
                      type="button"
                      onClick={() => setShowMetaPreview(!showMetaPreview)}
                      style={{
                        background: 'transparent',
                        border: 'none',
                        color: '#38bdf8',
                        cursor: 'pointer',
                        padding: 0,
                        textDecoration: 'underline',
                        fontSize: '12px'
                      }}
                    >
                      {showMetaPreview ? 'Hide Description Preview' : 'Show Description Preview'}
                    </button>
                  </div>

                  {showMetaPreview && (
                    <div style={{
                      marginTop: '6px',
                      background: '#18181b',
                      borderRadius: '8px',
                      padding: '12px',
                      border: '1px solid #3f3f46',
                      maxHeight: '180px',
                      overflowY: 'auto',
                      whiteSpace: 'pre-wrap',
                      color: '#cbd5e1',
                      fontSize: '11px',
                      fontFamily: 'monospace'
                    }}>
                      <div style={{ color: '#fb923c', fontWeight: 'bold', marginBottom: '4px' }}>
                        Description Preview with {'{{CHAPTERS}}'} Replaced ({scriptStats.descLen}/5000 chars):
                      </div>
                      {scriptStats.descPreview}
                    </div>
                  )}
                </div>
              ) : (
                <div style={{ color: '#f87171', fontSize: '12px' }}>
                  ⚠️ Missing 'youtube' metadata block in script JSON.
                </div>
              )}
            </div>
          )}

          {errorMsg && (
            <div style={{
              background: '#450a0a',
              border: '1px solid #991b1b',
              color: '#fca5a5',
              padding: '12px 14px',
              borderRadius: '8px',
              fontSize: '13px',
              whiteSpace: 'pre-wrap'
            }}>
              {errorMsg}
            </div>
          )}

          <div style={{ display: 'flex', gap: '10px', marginTop: '6px', flexWrap: 'wrap' }}>
            <button
              type="button"
              disabled={loading || exportingMeta}
              onClick={() => handleStartGeneration(false)}
              style={{
                flex: '2 1 200px',
                background: 'linear-gradient(135deg, #ea580c 0%, #f97316 100%)',
                color: '#fff',
                border: 'none',
                padding: '14px',
                borderRadius: '10px',
                fontWeight: '700',
                fontSize: '15px',
                cursor: (loading || exportingMeta) ? 'not-allowed' : 'pointer',
                opacity: (loading || exportingMeta) ? 0.6 : 1,
                boxShadow: '0 4px 14px rgba(234, 88, 12, 0.4)'
              }}
            >
              Generate Video & Auto-Upload (Private)
            </button>

            <button
              type="button"
              disabled={loading || exportingMeta}
              onClick={handleExportMetadata}
              style={{
                flex: '1 1 150px',
                background: 'linear-gradient(135deg, #0284c7 0%, #0369a1 100%)',
                color: '#fff',
                border: 'none',
                padding: '14px 16px',
                borderRadius: '10px',
                fontWeight: '700',
                fontSize: '14px',
                cursor: (loading || exportingMeta) ? 'not-allowed' : 'pointer',
                opacity: (loading || exportingMeta) ? 0.6 : 1,
                boxShadow: '0 4px 14px rgba(2, 132, 199, 0.3)'
              }}
            >
              {exportingMeta ? 'Exporting...' : '📄 Export Metadata'}
            </button>

            <button
              type="button"
              disabled={loading || exportingMeta}
              onClick={() => handleStartGeneration(true)}
              style={{
                background: '#27272a',
                color: '#e4e4e7',
                border: '1px solid #3f3f46',
                padding: '14px 16px',
                borderRadius: '10px',
                fontWeight: '600',
                fontSize: '13px',
                cursor: (loading || exportingMeta) ? 'not-allowed' : 'pointer',
                opacity: (loading || exportingMeta) ? 0.6 : 1
              }}
            >
              Fast Preview (5 Segments)
            </button>
          </div>
        </div>

        {/* Status & Preview Output */}
        <div style={{
          background: '#18181b',
          border: '1px solid #27272a',
          borderRadius: '14px',
          padding: '20px',
          display: 'flex',
          flexDirection: 'column',
          gap: '16px'
        }}>
          <h3 style={{ margin: 0, fontSize: '17px', color: '#e4e4e7', fontWeight: '700' }}>
            Output & Deliverables
          </h3>

          {(loading || exportingMeta) && (
            <div style={{ background: '#27272a', padding: '16px', borderRadius: '10px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px', color: '#fb923c', fontWeight: '600', marginBottom: '8px' }}>
                <span>{statusText}</span>
                <span>{progress.toFixed(0)}%</span>
              </div>
              <div style={{ width: '100%', height: '10px', background: '#3f3f46', borderRadius: '5px', overflow: 'hidden' }}>
                <div style={{
                  width: `${progress}%`,
                  height: '100%',
                  background: 'linear-gradient(90deg, #ea580c, #fb923c)',
                  transition: 'width 0.3s ease'
                }} />
              </div>
            </div>
          )}

          {!loading && !exportingMeta && !result && (
            <div style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '60px 20px',
              border: '2px dashed #27272a',
              borderRadius: '12px',
              color: '#71717a'
            }}>
              <span style={{ fontSize: '40px', marginBottom: '12px' }}>🎬</span>
              <p style={{ margin: 0, fontWeight: '600', fontSize: '15px', color: '#a1a1aa' }}>Ready to Generate</p>
              <p style={{ margin: '4px 0 0 0', fontSize: '13px' }}>Click "Generate Video" to render MP4 or "Export Metadata" for YouTube files.</p>
            </div>
          )}

          {result && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              {result.video_url && (
                <video
                  controls
                  src={result.video_url}
                  style={{
                    width: '100%',
                    borderRadius: '10px',
                    background: '#000',
                    boxShadow: '0 4px 20px rgba(0,0,0,0.5)'
                  }}
                />
              )}

              {result.is_metadata_only && (
                <div style={{
                  background: '#064e3b',
                  border: '1px solid #059669',
                  borderRadius: '10px',
                  padding: '16px',
                  color: '#a7f3d0'
                }}>
                  <div style={{ fontWeight: '700', fontSize: '15px', marginBottom: '4px' }}>
                    ✅ YouTube Metadata Exported Successfully
                  </div>
                  <div style={{ fontSize: '13px' }}>
                    All YouTube files with computed chapters and duration are ready for copy-paste or upload.
                  </div>
                </div>
              )}

              <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                {result.video_url && (
                  <a
                    href={result.video_url}
                    download
                    style={{
                      flex: '1 1 180px',
                      textAlign: 'center',
                      background: '#16a34a',
                      color: '#fff',
                      padding: '12px',
                      borderRadius: '8px',
                      textDecoration: 'none',
                      fontWeight: '700',
                      fontSize: '14px'
                    }}
                  >
                    Download MP4 Video
                  </a>
                )}
                {result.metadata_url && (
                  <a
                    href={result.metadata_url}
                    download
                    style={{
                      background: '#0369a1',
                      color: '#fff',
                      padding: '12px 16px',
                      borderRadius: '8px',
                      textDecoration: 'none',
                      fontWeight: '600',
                      fontSize: '13px'
                    }}
                  >
                    video_metadata.json
                  </a>
                )}
                {result.description_url && (
                  <a
                    href={result.description_url}
                    download
                    style={{
                      background: '#27272a',
                      color: '#e4e4e7',
                      padding: '12px 16px',
                      borderRadius: '8px',
                      textDecoration: 'none',
                      fontWeight: '600',
                      fontSize: '13px'
                    }}
                  >
                    description.txt
                  </a>
                )}
                {result.tags_url && (
                  <a
                    href={result.tags_url}
                    download
                    style={{
                      background: '#27272a',
                      color: '#e4e4e7',
                      padding: '12px 16px',
                      borderRadius: '8px',
                      textDecoration: 'none',
                      fontWeight: '600',
                      fontSize: '13px'
                    }}
                  >
                    tags.txt
                  </a>
                )}
                {result.chapters_url && (
                  <a
                    href={result.chapters_url}
                    download
                    style={{
                      background: '#27272a',
                      color: '#e4e4e7',
                      padding: '12px 16px',
                      borderRadius: '8px',
                      textDecoration: 'none',
                      fontWeight: '600',
                      fontSize: '13px'
                    }}
                  >
                    chapters.txt
                  </a>
                )}
                {result.srt_url && (
                  <a
                    href={result.srt_url}
                    download
                    style={{
                      background: '#27272a',
                      color: '#e4e4e7',
                      padding: '12px 16px',
                      borderRadius: '8px',
                      textDecoration: 'none',
                      fontWeight: '600',
                      fontSize: '13px'
                    }}
                  >
                    SRT Subtitles
                  </a>
                )}
              </div>

              {/* YouTube Auto-Upload Success Banner */}
              {result.youtube_url && (
                <div style={{
                  marginTop: '16px',
                  background: '#052e16',
                  border: '1px solid #16a34a',
                  borderRadius: '10px',
                  padding: '16px',
                  color: '#86efac',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '6px'
                }}>
                  <div style={{ fontWeight: '700', fontSize: '15px', color: '#4ade80', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span>🎉</span>
                    <span>Auto-Uploaded to YouTube as Private Video!</span>
                  </div>
                  <div style={{ fontSize: '13px' }}>
                    <strong>Channel:</strong> {ytChannel ? `${ytChannel.channel_title} (${ytChannel.custom_url})` : '@ShadowEnglishDaily-d4z'}
                  </div>
                  <div style={{ fontSize: '13px' }}>
                    <strong>YouTube Link:</strong>{' '}
                    <a
                      href={result.youtube_url}
                      target="_blank"
                      rel="noreferrer"
                      style={{ color: '#38bdf8', textDecoration: 'underline', fontWeight: 'bold' }}
                    >
                      {result.youtube_url} ↗
                    </a>
                  </div>
                  <div style={{ color: '#fef08a', fontSize: '12px', marginTop: '4px' }}>
                    🔒 Video uploaded as <strong>Private</strong>. Review it anytime in YouTube Studio!
                  </div>
                </div>
              )}

              {/* YouTube Auto-Upload Error / Notice if any */}
              {result.youtube_upload_error && (
                <div style={{
                  marginTop: '16px',
                  background: '#450a0a',
                  border: '1px solid #991b1b',
                  borderRadius: '10px',
                  padding: '14px',
                  color: '#fca5a5',
                  fontSize: '13px'
                }}>
                  <strong>⚠️ YouTube Auto-Upload Notice:</strong> {result.youtube_upload_error}
                  <div style={{ color: '#cbd5e1', fontSize: '12px', marginTop: '4px' }}>
                    (The MP4 video, subtitles, chapters, and metadata were all generated successfully above).
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
