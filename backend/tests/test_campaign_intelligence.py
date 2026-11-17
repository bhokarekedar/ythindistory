import os
import sys
import unittest

# Ensure backend in sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from core.campaign_intelligence import (
    CampaignAnalyzer,
    CampaignRepository,
    ChannelProfile
)


class TestCampaignIntelligence(unittest.TestCase):

    def setUp(self):
        self.analyzer = CampaignAnalyzer()
        self.profile = ChannelProfile()  # Brand new ViralLoop profile (0 subs, 0 followers)

    def test_01_gaming_campaign_approved(self):
        brief = """
        CAMPAIGN: Minecraft Speedrun Highlights Season 4
        PLATFORM: Content Rewards
        DESCRIPTION: We are paying creator clippers to create viral YouTube Shorts and TikToks from authorized Minecraft streamer VODs!
        Source footage drive: https://drive.google.com/drive/folders/minecraft_authorized
        ELIGIBILITY: Open to all creators, big or small! No minimum subscriber or follower count required. New channels welcome.
        FORMAT: 9:16 vertical video with captions.
        PAYOUT: $2.50 CPM up to $500 per video.
        HASHTAGS: #Minecraft #GamingClips #Speedrun
        """
        record = self.analyzer.analyze_campaign(raw_brief=brief, title="Minecraft Speedrun Season 4", channel_profile=self.profile)
        self.assertEqual(record.status, "APPROVED")
        self.assertGreaterEqual(record.analysis.overall_score, 75)
        self.assertGreaterEqual(record.analysis.niche_compatibility_score, 75)
        self.assertIn("#minecraft", [h.lower() for h in record.posting_metadata.hashtags])

    def test_02_requires_2000_subscribers_rejected(self):
        brief = """
        CAMPAIGN: Top Tier Valorant Clips
        REQUIREMENTS: Channels must have at least 2,000 subscribers on YouTube to qualify for monetization.
        Payout: $4.00 CPM.
        Footage: Provided in portal.
        """
        record = self.analyzer.analyze_campaign(raw_brief=brief, title="Top Tier Valorant", channel_profile=self.profile)
        self.assertEqual(record.status, "REJECTED")
        self.assertTrue(any("2,000" in r or "subscribers" in r for r in record.analysis.rejection_reasons))

    def test_03_requires_viral_videos_rejected(self):
        brief = """
        CAMPAIGN: Fortnite Pro Moments
        ELIGIBILITY: Must submit at least 3 previous viral video URLs (100k+ views) to receive campaign approval code.
        """
        record = self.analyzer.analyze_campaign(raw_brief=brief, title="Fortnite Pro Moments", channel_profile=self.profile)
        self.assertEqual(record.status, "REJECTED")
        self.assertTrue(any("viral video" in r.lower() for r in record.analysis.rejection_reasons))

    def test_04_mrbeast_style_challenge_approved(self):
        brief = """
        CAMPAIGN: Extreme Stunts & Challenge Clips
        DESCRIPTION: Clip the craziest challenge moments from our authorized YouTube channel.
        ELIGIBILITY: No follower requirement. Open to anyone who can edit entertaining 9:16 vertical shorts.
        PAYOUT: $3.00 CPM.
        TAGS: #Challenge #CrazyExperiments #Viral
        """
        record = self.analyzer.analyze_campaign(raw_brief=brief, title="Extreme Stunts", channel_profile=self.profile)
        self.assertEqual(record.status, "APPROVED")
        self.assertGreaterEqual(record.analysis.niche_compatibility_score, 70)

    def test_05_face_camera_required_rejected(self):
        brief = """
        CAMPAIGN: AI Productivity App Review
        REQUIREMENTS: Creator must film themselves on camera (face cam mandatory) demonstrating the web interface.
        No faceless voiceovers allowed.
        """
        record = self.analyzer.analyze_campaign(raw_brief=brief, title="AI App Review", channel_profile=self.profile)
        self.assertEqual(record.status, "REJECTED")
        self.assertTrue(any("face" in r.lower() for r in record.analysis.rejection_reasons))

    def test_06_unclear_footage_permissions_needs_info(self):
        brief = """
        CAMPAIGN: Internet Drama Clips
        DESCRIPTION: Create short videos about recent internet drama.
        PAYMENT: $1.50 CPM.
        Note: You find your own footage across Twitter and YouTube. We do not provide licenses.
        """
        record = self.analyzer.analyze_campaign(raw_brief=brief, title="Internet Drama Clips", channel_profile=self.profile)
        self.assertIn(record.status, ["NEEDS_INFO", "REJECTED"])

    def test_07_mandatory_hashtags_and_cta_extracted(self):
        brief = """
        CAMPAIGN: Roblox Brookhaven Story Clips
        RULES: You must include #RobloxStories and #Brookhaven in the caption.
        MANDATORY CTA: Comment 'KEY' to win Robux!
        MENTION: @RobloxDevTeam
        Open to all creators, 0 subs required.
        """
        record = self.analyzer.analyze_campaign(raw_brief=brief, title="Roblox Stories", channel_profile=self.profile)
        # Verify hashtags and mentions are extracted
        tags_lower = [t.lower() for t in record.posting_metadata.hashtags]
        self.assertTrue(any("roblox" in t for t in tags_lower))
        if record.posting_metadata.cta:
            self.assertIn("KEY", record.posting_metadata.cta)

    def test_08_tier1_audience_needs_info(self):
        brief = """
        CAMPAIGN: US Mobile Game Launch
        REQUIREMENTS: Channels must have at least 60% of their audience located in Tier 1 countries (US, UK, CA, AU).
        No minimum follower count.
        """
        record = self.analyzer.analyze_campaign(raw_brief=brief, title="US Game Launch", channel_profile=self.profile)
        self.assertIn(record.status, ["NEEDS_INFO", "REJECTED"])
        self.assertTrue(any("tier 1" in u.lower() or "audience" in u.lower() for u in record.analysis.unverified_requirements + record.analysis.rejection_reasons))

    def test_09_daily_post_limit_extracted(self):
        brief = """
        CAMPAIGN: Streamer Reaction Loops
        POSTING RULES: Maximum 2 posts per day allowed per creator.
        Open to all channels.
        """
        record = self.analyzer.analyze_campaign(raw_brief=brief, title="Streamer Reactions", channel_profile=self.profile)
        self.assertTrue(
            record.posting_metadata.posting_frequency_limit is not None or
            any("2" in r for r in record.posting_metadata.other_posting_instructions + record.analysis.risks)
        )

    def test_10_repository_duplicate_and_override(self):
        import tempfile
        tmp_dir = tempfile.mkdtemp()
        repo = CampaignRepository(data_dir=tmp_dir)
        brief = "CAMPAIGN: Unique Test Campaign\nOpen to all creators.\n#UniqueTag"
        rec1 = self.analyzer.analyze_campaign(brief, title="Unique Test Campaign", channel_profile=self.profile)
        repo.save(rec1)

        # Duplicate check
        dup = repo.find_duplicate(raw_brief=brief, title="Unique Test Campaign")
        self.assertIsNotNone(dup)
        self.assertEqual(dup.campaign_id, rec1.campaign_id)

        # Manual verdict override test
        updated = repo.update_verdict(rec1.campaign_id, "APPROVED", reason="Manual override test")
        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, "APPROVED")
        self.assertTrue(updated.manual_override)
        self.assertEqual(updated.manual_verdict, "APPROVED")


if __name__ == "__main__":
    unittest.main()
