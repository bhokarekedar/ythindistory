import React, { useState } from 'react';

const BACKEND_BASE = 'http://localhost:8000';

const sampleScript = {
  "title": "English Fluency Shadowing Practice: Mindset & Daily Life",
  "settings": {
    "buffer_seconds": 1.5,
    "default_repeat": 2,
    "voice_teacher": "Samantha",
    "voice_speaker_b": "Alex"
  },
  "segments": [
    {
      "type": "narration",
      "text": "Hello everyone, and welcome back to English Fluency Teacher. Today we are going to do an English shadowing practice."
    },
    {
      "type": "section_title",
      "text": "Section 1: English Learning Mindset"
    },
    {
      "type": "shadow",
      "text": "I don't need perfect English to have a meaningful conversation.",
      "repeat": 2
    },
    {
      "type": "shadow",
      "text": "Every time I speak aloud, I'm making English easier to access next time.",
      "repeat": 2
    },
    {
      "type": "shadow",
      "text": "Shadowing trains my ears and mouth to work together.",
      "repeat": 2
    },
    {
      "type": "section_title",
      "text": "Section 2: Morning Routine"
    },
    {
      "type": "dialogue",
      "speaker": "Speaker A",
      "text": "What time did you wake up this morning?"
    },
    {
      "type": "dialogue",
      "speaker": "Speaker B",
      "text": "I woke up around 7:00, but I stayed in bed for another 10 minutes."
    },
    {
      "type": "free_answer",
      "text": "What helps you start the day in a good mood?",
      "pause_seconds": 5.0
    },
    {
      "type": "narration",
      "text": "Excellent work! Keep listening, keep practicing, and most importantly, keep speaking English."
    }
  ]
};

export default function EnglishShadowingStudio() {
  const [scriptJson, setScriptJson] = useState(JSON.stringify(sampleScript, null, 2));
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [statusText, setStatusText] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  const [result, setResult] = useState(null);

  const handleLoadSample = () => {
    setScriptJson(JSON.stringify(sampleScript, null, 2));
    setErrorMsg('');
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
      const pollTimer = setInterval(async () => {
        try {
          const sResp = await fetch(`${BACKEND_BASE}/api/shadowing/jobs/${jobId}`);
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
              duration: job.result.duration
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
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <label style={{ color: '#e4e4e7', fontWeight: '700', fontSize: '15px' }}>
              Script JSON
            </label>
            <span style={{ color: '#a1a1aa', fontSize: '12px' }}>
              narration • section_title • shadow • dialogue • free_answer
            </span>
          </div>

          <textarea
            value={scriptJson}
            onChange={(e) => setScriptJson(e.target.value)}
            rows={18}
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

          <div style={{ display: 'flex', gap: '12px', marginTop: '6px' }}>
            <button
              type="button"
              disabled={loading}
              onClick={() => handleStartGeneration(false)}
              style={{
                flex: 1,
                background: 'linear-gradient(135deg, #ea580c 0%, #f97316 100%)',
                color: '#fff',
                border: 'none',
                padding: '14px',
                borderRadius: '10px',
                fontWeight: '700',
                fontSize: '15px',
                cursor: loading ? 'not-allowed' : 'pointer',
                opacity: loading ? 0.6 : 1,
                boxShadow: '0 4px 14px rgba(234, 88, 12, 0.4)'
              }}
            >
              Render Full Video (1080p)
            </button>

            <button
              type="button"
              disabled={loading}
              onClick={() => handleStartGeneration(true)}
              style={{
                background: '#27272a',
                color: '#e4e4e7',
                border: '1px solid #3f3f46',
                padding: '14px 20px',
                borderRadius: '10px',
                fontWeight: '600',
                fontSize: '14px',
                cursor: loading ? 'not-allowed' : 'pointer',
                opacity: loading ? 0.6 : 1
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
            Output & Live Progress
          </h3>

          {loading && (
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

          {!loading && !result && (
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
              <span style={{ fontSize: '40px', marginBottom: '12px' }}>🎧</span>
              <p style={{ margin: 0, fontWeight: '600', fontSize: '15px', color: '#a1a1aa' }}>Ready to Render</p>
              <p style={{ margin: '4px 0 0 0', fontSize: '13px' }}>Click "Render Full Video" or "Fast Preview" to generate your MP4.</p>
            </div>
          )}

          {result && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
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

              <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                <a
                  href={result.video_url}
                  download
                  style={{
                    flex: 1,
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
                <a
                  href={result.srt_url}
                  download
                  style={{
                    background: '#27272a',
                    color: '#e4e4e7',
                    padding: '12px 18px',
                    borderRadius: '8px',
                    textDecoration: 'none',
                    fontWeight: '600',
                    fontSize: '13px'
                  }}
                >
                  Download SRT Subtitles
                </a>
                <a
                  href={result.timeline_url}
                  download
                  style={{
                    background: '#27272a',
                    color: '#e4e4e7',
                    padding: '12px 18px',
                    borderRadius: '8px',
                    textDecoration: 'none',
                    fontWeight: '600',
                    fontSize: '13px'
                  }}
                >
                  Timeline JSON
                </a>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
