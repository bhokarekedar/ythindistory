import os
import re
import subprocess
import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModel

class SemanticAligner:
    """
    Advanced Deterministic Alignment Engine:
    1. Semantic Vector Matcher: Uses local transformer embeddings (all-MiniLM-L6-v2)
       to find the exact dialogue cluster corresponding to any recap voiceover sentence.
    2. Keyframe Scene Cut Snapper: Snaps timestamps to the nearest visual I-frame (camera transition)
       so video cuts happen cleanly without mid-frame motion tearing.
    """

    _instance = None
    _tokenizer = None
    _model = None

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._load_model()

    def _load_model(self):
        if SemanticAligner._model is None:
            print("  [SemanticAligner] 🧠 Initializing local embedding model (all-MiniLM-L6-v2)...")
            SemanticAligner._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            SemanticAligner._model = AutoModel.from_pretrained(self.model_name)
            SemanticAligner._model.eval()
            print("  [SemanticAligner] ✅ Embedding model ready.")
        self.tokenizer = SemanticAligner._tokenizer
        self.model = SemanticAligner._model

    @staticmethod
    def _mean_pooling(model_output, attention_mask):
        token_embeddings = model_output[0]
        input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        return torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(input_mask_expanded.sum(1), min=1e-9)

    def encode(self, texts: list) -> torch.Tensor:
        """Encodes a list of strings into normalized 384-dimensional dense semantic vectors."""
        if not texts:
            return torch.empty((0, 384))
        encoded = self.tokenizer(texts, padding=True, truncation=True, max_length=128, return_tensors="pt")
        with torch.no_grad():
            out = self.model(**encoded)
        emb = self._mean_pooling(out, encoded["attention_mask"])
        return F.normalize(emb, p=2, dim=1)

    def match_best_dialogue_cluster(
        self,
        narration_text: str,
        dialogue_clusters: list,
        anchor_quote: str = "",
        expected_time_sec: float = 0.0,
        temporal_window_sec: float = 240.0
    ) -> dict:
        """
        Finds the dialogue cluster with the highest combined semantic similarity and token overlap,
        penalizing temporal distance from expected_time_sec if provided.
        Each item in dialogue_clusters must have: {'start': float, 'end': float, 'text': str}
        """
        if not dialogue_clusters:
            return None

        # Filter candidates by temporal window if expected_time_sec is given
        if expected_time_sec > 0:
            candidates = [
                c for c in dialogue_clusters
                if abs(c["start"] - expected_time_sec) <= temporal_window_sec
            ]
            if not candidates:
                candidates = dialogue_clusters
        else:
            candidates = dialogue_clusters

        # Encode narration query
        q_emb = self.encode([narration_text])[0]  # shape: [384]

        # Gather or compute candidate embeddings
        cand_texts = [c["text"] for c in candidates]
        cand_embs = self.encode(cand_texts)  # shape: [N, 384]

        # Compute cosine similarities
        cosine_sims = (cand_embs @ q_emb).cpu().tolist()  # list of floats

        norm_quote = re.sub(r"[^a-z0-9\s]", "", (anchor_quote or "").lower()).strip()
        q_tokens = set(norm_quote.split()) if len(norm_quote) >= 4 else set()

        best_cluster = None
        best_score = -1.0

        for i, c in enumerate(candidates):
            sim = cosine_sims[i]

            # Bonus for exact anchor quote or token overlap
            bonus = 0.0
            c_norm = re.sub(r"[^a-z0-9\s]", "", c["text"].lower())
            if norm_quote and norm_quote in c_norm:
                bonus += 0.25
            elif q_tokens:
                c_tokens = set(c_norm.split())
                overlap = len(q_tokens.intersection(c_tokens)) / len(q_tokens)
                bonus += 0.15 * overlap

            # Slight penalty for massive distance from expected time
            dist_penalty = 0.0
            if expected_time_sec > 0:
                dist_min = abs(c["start"] - expected_time_sec) / 60.0
                dist_penalty = min(0.15, dist_min * 0.03)

            score = sim + bonus - dist_penalty

            if score > best_score:
                best_score = score
                best_cluster = c

        return {
            "cluster": best_cluster,
            "similarity": best_score,
            "timestamp": best_cluster["start"] if best_cluster else expected_time_sec
        }

    @staticmethod
    def snap_to_nearest_keyframe(movie_path: str, target_sec: float, search_radius_sec: float = 2.0) -> float:
        """
        Queries video stream for I-frames (scene transitions / keyframes) around target_sec,
        snapping the cut point to the nearest camera transition for a clean, artifact-free edit.
        """
        if not os.path.exists(movie_path):
            return target_sec

        start_probe = max(0.0, target_sec - search_radius_sec)
        dur_probe = search_radius_sec * 2.0

        cmd = [
            "ffmpeg", "-y", "-ss", str(start_probe), "-t", str(dur_probe),
            "-i", movie_path,
            "-vf", "showinfo",
            "-f", "null", "-"
        ]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            # Find all keyframe occurrences
            # Example log: iskey:1 type:I ... pts_time:0.75
            key_times = []
            for line in res.stderr.splitlines():
                if "iskey:1" in line:
                    match = re.search(r"pts_time:([\d\.]+)", line)
                    if match:
                        offset = float(match.group(1))
                        key_times.append(start_probe + offset)

            if key_times:
                # Pick the keyframe closest to target_sec
                closest = min(key_times, key=lambda kt: abs(kt - target_sec))
                # Only snap if within 1.5s of target
                if abs(closest - target_sec) <= 1.5:
                    return round(closest, 3)
        except Exception:
            pass

        return round(target_sec, 3)
