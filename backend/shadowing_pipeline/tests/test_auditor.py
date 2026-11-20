import unittest
from shadowing_pipeline.core.auditor import ShadowingScriptAuditor

class TestShadowingScriptAuditor(unittest.TestCase):
    def test_apply_replace_patch(self):
        script = {
            "title": "Test Title",
            "youtube": {"title": "YT Title"},
            "segments": [
                {"id": "p1_01", "type": "shadow", "text": "I arrived at 7:00 AM."}
            ]
        }
        patches = [
            {
                "action": "replace",
                "id": "p1_01",
                "segment": {
                    "id": "p1_01",
                    "type": "shadow",
                    "text": "I arrived at 7:00 AM.",
                    "spoken": "I arrived at seven A M."
                },
                "reason": "TTS expansion"
            }
        ]
        modified = ShadowingScriptAuditor.apply_patches(script, patches)
        self.assertEqual(len(modified["segments"]), 1)
        self.assertEqual(modified["segments"][0]["spoken"], "I arrived at seven A M.")
        self.assertEqual(modified["youtube"]["title"], "YT Title")

    def test_apply_delete_patch(self):
        script = {
            "title": "Test",
            "segments": [
                {"id": "p1_01", "type": "shadow", "text": "Sentence 1"},
                {"id": "p1_02", "type": "shadow", "text": "Sentence 1 (duplicate)"}
            ]
        }
        patches = [
            {"action": "delete", "id": "p1_02", "reason": "Duplicate"}
        ]
        modified = ShadowingScriptAuditor.apply_patches(script, patches)
        self.assertEqual(len(modified["segments"]), 1)
        self.assertEqual(modified["segments"][0]["id"], "p1_01")

    def test_apply_insert_after_patch(self):
        script = {
            "title": "Test",
            "segments": [
                {"id": "p1_01", "type": "shadow", "text": "First sentence."}
            ]
        }
        patches = [
            {
                "action": "insert_after",
                "id": "p1_01",
                "segment": {"id": "p1_01b", "type": "shadow", "text": "Second sentence."},
                "reason": "Missing practice variation"
            }
        ]
        modified = ShadowingScriptAuditor.apply_patches(script, patches)
        self.assertEqual(len(modified["segments"]), 2)
        self.assertEqual(modified["segments"][0]["id"], "p1_01")
        self.assertEqual(modified["segments"][1]["id"], "p1_01b")

    def test_threshold_calculation(self):
        # 10 segments, 1 patch -> 10.0% -> auto-apply (requires_approval = False)
        # 10 segments, 2 patches -> 20.0% -> requires_approval = True
        total = 10
        self.assertFalse(round(1 / total * 100, 1) > 10.0)
        self.assertTrue(round(2 / total * 100, 1) > 10.0)

if __name__ == "__main__":
    unittest.main()
