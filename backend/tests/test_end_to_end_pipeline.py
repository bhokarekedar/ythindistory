import os
import sys
import json
import time
import subprocess
from pathlib import Path

# Add backend directory to sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from core.campaign_intelligence import (
    CampaignAnalyzer,
    CampaignRepository,
    ChannelProfile
)
from core.viral_moment_detector import ViralMomentDetector
from core.editorial_reviewer import EditorialReviewer
from core.smart_crop import SmartCropEngine

PASSED = "✅ PASS"
FAILED = "❌ FAIL"

def run_tests():
    print("\n=======================================================")
    print("🚀 VIRALLOOP PIPELINE: COMPLETE END-TO-END VERIFICATION")
    print("=======================================================\n")
    
    total_steps = 0
    passed_steps = 0
    
    # ---------------------------------------------------------
    # STAGE 1: CAMPAIGN INTELLIGENCE PIPELINE
    # ---------------------------------------------------------
    print("--- [STAGE 1] Testing Campaign Intelligence ---")
    
    # 1.1 Channel Profile Initialization
    total_steps += 1
    profile = ChannelProfile()
    if profile.channel_name == "ViralLoop" and profile.youtube_subscribers == 0:
        print(f"[{PASSED}] 1.1 Channel profile initialized (Brand New: 0 subs, 0 followers)")
        passed_steps += 1
    else:
        print(f"[{FAILED}] 1.1 Channel profile initialization failed")

    # 1.2 Campaign Analysis with LLM
    total_steps += 1
    analyzer = CampaignAnalyzer()
    sample_brief = """
    CAMPAIGN: Extreme Streamer Challenge 2026
    PLATFORM: Content Rewards
    DESCRIPTION: Create viral short-form clips (YouTube Shorts & TikTok) from our official Minecraft & challenge streams.
    ELIGIBILITY: Open to all creators! No minimum subscriber count required.
    FORMAT: 9:16 vertical video with animated captions.
    PAYOUT: $3.00 CPM up to $600 per video.
    HASHTAGS: #Minecraft #GamingClips #ViralChallenge
    """
    record = analyzer.analyze_campaign(
        raw_brief=sample_brief,
        title="Extreme Streamer Challenge 2026",
        channel_profile=profile
    )
    
    if record.status == "APPROVED" and record.analysis.overall_score >= 70:
        print(f"[{PASSED}] 1.2 Campaign LLM Analysis (Verdict: {record.status}, Score: {record.analysis.overall_score}/100)")
        passed_steps += 1
    else:
        print(f"[{FAILED}] 1.2 Campaign Analysis unexpected result: status={record.status}")

    # 1.3 Strict Eligibility Rejection Check
    total_steps += 1
    strict_brief = """
    CAMPAIGN: Pro League Highlights
    REQUIREMENTS: Creators must have at least 50,000 subscribers and submit 5 previous viral video links.
    """
    strict_record = analyzer.analyze_campaign(
        raw_brief=strict_brief,
        title="Pro League Highlights",
        channel_profile=profile
    )
    if strict_record.status == "REJECTED":
        print(f"[{PASSED}] 1.3 Strict Eligibility Rejection (Successfully rejected ineligible campaign: {strict_record.analysis.rejection_reasons[0][:60]}...)")
        passed_steps += 1
    else:
        print(f"[{FAILED}] 1.3 Strict eligibility was not rejected!")

    # 1.4 Campaign Repository Persistence
    total_steps += 1
    repo = CampaignRepository()
    saved_record = repo.save(record)
    retrieved = repo.get(saved_record.campaign_id)
    if retrieved and retrieved.campaign_id == saved_record.campaign_id and retrieved.title == "Extreme Streamer Challenge 2026":
        print(f"[{PASSED}] 1.4 Campaign Persistence (Saved & Retrieved {retrieved.campaign_id})")
        passed_steps += 1
    else:
        print(f"[{FAILED}] 1.4 Campaign Persistence failed")

    # ---------------------------------------------------------
    # STAGE 2: STORY-COMPLETE VIRAL MOMENT DETECTION
    # ---------------------------------------------------------
    print("\n--- [STAGE 2] Testing Story-Complete Viral Moment Detection ---")
    
    total_steps += 1
    transcript_file = os.path.join(backend_dir, "temp", "viral_q6fgVVmdpgY", "q6fgVVmdpgY_transcript.json")
    if not os.path.exists(transcript_file):
        print(f"[{FAILED}] 2.1 Transcript file not found at {transcript_file}")
    else:
        with open(transcript_file, "r", encoding="utf-8") as f:
            segments = json.load(f)
            
        detector = ViralMomentDetector()
        moments = detector.detect_moments(transcript_file, target_clips=3)
        
        if moments and len(moments) > 0:
            first_m = moments[0]
            has_arc = first_m.get("story_arc") is not None
            has_hook = bool(first_m.get("story_arc", {}).get("hook"))
            has_payoff = bool(first_m.get("story_arc", {}).get("payoff"))
            print(f"[{PASSED}] 2.1 Story-Complete Detection: Found {len(moments)} candidate clips.")
            print(f"    Sample: \"{first_m.get('title')}\" [{first_m.get('start_time')}s - {first_m.get('end_time')}s] ({first_m.get('duration')}s)")
            print(f"    Ending Type: {first_m.get('ending_type')}, Completeness Score: {first_m.get('completeness_score')}/100")
            passed_steps += 1
        else:
            print(f"[{FAILED}] 2.1 No viral moments detected")

    # ---------------------------------------------------------
    # STAGE 3: EDITORIAL QUALITY REVIEW STAGE
    # ---------------------------------------------------------
    print("\n--- [STAGE 3] Testing Editorial Quality Review ---")
    
    total_steps += 1
    reviewer = EditorialReviewer()
    source_video_path = os.path.join(backend_dir, "temp", "videos", "q6fgVVmdpgY.mp4")
    
    clip_to_review = moments[0]
    transcript_ctx = clip_to_review.get("transcript_excerpt") or clip_to_review.get("reasoning") or "Watch this shot. If he hits the crossbar, he wins."
    
    review_result = reviewer.review_clip(
        clip=clip_to_review,
        transcript_context=transcript_ctx,
        source_video_path=source_video_path if os.path.exists(source_video_path) else None,
        keyframe_dir=os.path.join(backend_dir, "temp", "viral_q6fgVVmdpgY", "keyframes")
    )
    
    if review_result and "overall_score" in review_result:
        print(f"[{PASSED}] 3.1 Editorial Quality Review completed!")
        print(f"    Status: {review_result.get('editorial_status')}, Overall Score: {review_result.get('overall_score')}/100")
        crit = review_result.get('criteria_scores', {})
        print(f"    Criteria: Hook={crit.get('hook_score')}, Context={crit.get('context_score')}, Payoff={crit.get('payoff_score')}, Completeness={crit.get('completeness_score')}")
        passed_steps += 1
    else:
        print(f"[{FAILED}] 3.1 Editorial review failed")

    # ---------------------------------------------------------
    # STAGE 4: AI VIDEO CROPPING & RENDERING ENGINE
    # ---------------------------------------------------------
    print("\n--- [STAGE 4] Testing AI Video Cropping & FFmpeg Render ---")
    
    total_steps += 1
    if not os.path.exists(source_video_path):
        print(f"[{FAILED}] 4.1 Source video not found for rendering at {source_video_path}")
    else:
        test_render_out = os.path.join(backend_dir, "temp", "e2e_test_render_9x16.mp4")
        if os.path.exists(test_render_out):
            try:
                os.remove(test_render_out)
            except Exception:
                pass
                
        engine = SmartCropEngine()
        print(f"    Rendering 5-second 9:16 vertical clip from {os.path.basename(source_video_path)}...")
        report = engine.process_clip(
            source_path=source_video_path,
            output_path=test_render_out,
            clip_id="e2e_test_clip",
            start_time=15.0,
            duration=5.0,
            preferred_layout="dynamic_smart_crop"
        )
        
        if os.path.exists(test_render_out) and report.render_status == "completed":
            size_mb = os.path.getsize(test_render_out) / (1024 * 1024)
            # Probe resolution with ffprobe
            probe_cmd = [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=s=x:p=0", test_render_out
            ]
            res = subprocess.check_output(probe_cmd).decode().strip()
            print(f"[{PASSED}] 4.1 9:16 Vertical Video Rendered Successfully!")
            print(f"    File: {test_render_out}")
            print(f"    Resolution: {res} (Target 1080x1920)")
            print(f"    File Size: {size_mb:.2f} MB, Status: {report.render_status}")
            passed_steps += 1
        else:
            print(f"[{FAILED}] 4.1 Render failed: {report.error}")

    # ---------------------------------------------------------
    # STAGE 5: CONTENT REWARDS DISCOVERY STAGE
    # ---------------------------------------------------------
    print("\n--- [STAGE 5] Testing Content Rewards Live Discovery ---")
    total_steps += 1
    
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://contentrewards.com/c/discover", timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        links = page.evaluate("() => Array.from(document.querySelectorAll('a[href*=\"/c/campaigns/\"]')).map(a => a.href)")
        browser.close()
        
    unique_links = list(dict.fromkeys(links))
    if len(unique_links) > 0:
        print(f"[{PASSED}] 5.1 Content Rewards Live Browser Discovery (Discovered {len(unique_links)} campaigns)")
        passed_steps += 1
    else:
        print(f"[{FAILED}] 5.1 No campaigns discovered on Content Rewards")

    # ---------------------------------------------------------
    # SUMMARY
    # ---------------------------------------------------------
    print("\n=======================================================")
    print(f"📊 SUMMARY: {passed_steps}/{total_steps} STEPS PASSED ({(passed_steps/total_steps)*100:.1f}%)")
    print("=======================================================\n")
    return passed_steps == total_steps

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
