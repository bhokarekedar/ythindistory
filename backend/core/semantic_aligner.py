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
       to find the dialogue cluster most likely corresponding to a recap voiceover sentence.
       Returns separate cosine_similarity, anchor_score, temporal_penalty, and combined_score
       so callers can apply their own confidence thresholds without ambiguity.
    2. Keyframe Snapper: Snaps timestamps to the nearest video I-frame within a small radius.
       NOTE: I-frames are video-encoding keyframes, NOT scene cuts. Use FFmpeg scene-change
       detection (select='gt(scene,N)') if true scene-cut snapping is required.
    """

    _instance = None
    _tokenizer = None
    _model = None

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.model_name = model_name
        # Cache of precomputed cluster embeddings: mapping id(cluster_list) -> tensor
        self._cluster_emb_cache: dict = {}
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

    def precompute_cluster_embeddings(self, dialogue_clusters: list) -> torch.Tensor:
        """
        Pre-encodes all dialogue cluster texts and caches them against the cluster list identity.
        Call this once per unique cluster list before running match_best_dialogue_cluster() in a loop
        to avoid re-encoding the same clusters for every narration segment.
        Returns the cached embedding tensor (shape: [N, 384]).
        """
        cache_key = id(dialogue_clusters)
        if cache_key not in self._cluster_emb_cache:
            texts = [c["text"] for c in dialogue_clusters]
            self._cluster_emb_cache[cache_key] = self.encode(texts)
        return self._cluster_emb_cache[cache_key]

    def match_best_dialogue_cluster(
        self,
        narration_text: str,
        dialogue_clusters: list,
        anchor_quote: str = "",
        expected_time_sec: float = 0.0,
        temporal_window_sec: float = 240.0,
        precomputed_embeddings: torch.Tensor = None
    ) -> dict:
        """
        Finds the dialogue cluster with the highest combined alignment score for a narration segment.

        IMPORTANT: A high combined_score indicates temporal proximity and semantic similarity to
        the dialogue cluster — it does NOT verify that the narration describes the event accurately.
        Factual verification must be performed separately using source dialogue evidence.

        Args:
            narration_text: The generated voiceover sentence to align.
            dialogue_clusters: List of dicts with {'start': float, 'end': float, 'text': str}.
            anchor_quote: Optional short phrase from dialogue to boost alignment precision.
            expected_time_sec: LLM-suggested movie timestamp in seconds (used to filter candidates).
            temporal_window_sec: Search radius around expected_time_sec.
            precomputed_embeddings: Optional pre-encoded tensor for dialogue_clusters (shape: [N, 384]).
                                    Pass the result of precompute_cluster_embeddings() to avoid
                                    re-encoding clusters on every call.

        Returns:
            dict with keys:
                cluster: the matched cluster dict (or None)
                timestamp: matched cluster start time in seconds
                cosine_similarity: raw cosine similarity between narration and cluster (0.0–1.0)
                anchor_score: bonus added for anchor quote token overlap (0.0–0.25)
                temporal_penalty: penalty subtracted for distance from expected_time_sec (0.0–0.30)
                combined_score: cosine_similarity + anchor_score - temporal_penalty
                within_temporal_window: True if match was found within the specified window
                fallback_to_full_movie: True if no candidates existed within window (low confidence)
        """
        if not dialogue_clusters:
            return None

        # Filter candidates by temporal window if expected_time_sec is given
        within_window = True
        if expected_time_sec > 0:
            candidates_idx = [
                i for i, c in enumerate(dialogue_clusters)
                if abs(c["start"] - expected_time_sec) <= temporal_window_sec
            ]
            if not candidates_idx:
                # No candidates within window — fall back to full movie but flag it
                candidates_idx = list(range(len(dialogue_clusters)))
                within_window = False
        else:
            candidates_idx = list(range(len(dialogue_clusters)))

        fallback_to_full = not within_window

        # Encode only the narration query (clusters are pre-computed or computed once here)
        q_emb = self.encode([narration_text])[0]  # shape: [384]

        # Use precomputed embeddings if provided, else compute (and do NOT cache here — caller
        # should call precompute_cluster_embeddings() for efficiency)
        if precomputed_embeddings is not None and len(precomputed_embeddings) == len(dialogue_clusters):
            all_cand_embs = precomputed_embeddings
        else:
            all_cand_embs = self.encode([dialogue_clusters[i]["text"] for i in range(len(dialogue_clusters))])

        # Only consider the filtered candidates
        cand_embs = all_cand_embs[candidates_idx]  # shape: [M, 384]
        cosine_sims = (cand_embs @ q_emb).cpu().tolist()

        norm_quote = re.sub(r"[^a-z0-9\s]", "", (anchor_quote or "").lower()).strip()
        q_tokens = set(norm_quote.split()) if len(norm_quote) >= 4 else set()

        best_cluster = None
        best_combined = -1.0
        best_cosine = 0.0
        best_anchor = 0.0
        best_penalty = 0.0

        for rank, orig_i in enumerate(candidates_idx):
            c = dialogue_clusters[orig_i]
            sim = cosine_sims[rank]

            # Anchor quote bonus: exact substring match → 0.25; token overlap → up to 0.15
            anchor_bonus = 0.0
            c_norm = re.sub(r"[^a-z0-9\s]", "", c["text"].lower())
            if norm_quote and norm_quote in c_norm:
                anchor_bonus = 0.25
            elif q_tokens:
                c_tokens = set(c_norm.split())
                overlap = len(q_tokens.intersection(c_tokens)) / len(q_tokens)
                anchor_bonus = 0.15 * overlap

            # Temporal penalty: stronger than before (max 0.30, rate 0.06/min)
            # This prevents a semantically similar cluster 10+ minutes away from winning
            dist_penalty = 0.0
            if expected_time_sec > 0:
                dist_min = abs(c["start"] - expected_time_sec) / 60.0
                dist_penalty = min(0.30, dist_min * 0.06)

            combined = sim + anchor_bonus - dist_penalty

            if combined > best_combined:
                best_combined = combined
                best_cluster = c
                best_cosine = sim
                best_anchor = anchor_bonus
                best_penalty = dist_penalty

        return {
            "cluster": best_cluster,
            "timestamp": best_cluster["start"] if best_cluster else expected_time_sec,
            "cosine_similarity": round(best_cosine, 4),
            "anchor_score": round(best_anchor, 4),
            "temporal_penalty": round(best_penalty, 4),
            "combined_score": round(best_combined, 4),
            # Keep 'similarity' as alias of combined_score for backward compatibility
            "similarity": round(best_combined, 4),
            "within_temporal_window": within_window,
            "fallback_to_full_movie": fallback_to_full,
        }

    @staticmethod
    def snap_to_nearest_keyframe(movie_path: str, target_sec: float, search_radius_sec: float = 2.0) -> float:
        """
        Finds the nearest video I-frame within search_radius_sec of target_sec and returns its
        absolute timestamp if it falls within 1.5 s of the target.

        NOTE: This snaps to video-encoding keyframes (I-frames), which are inserted periodically
        by the encoder and are NOT the same as scene changes or camera cuts. Use FFmpeg's
        scene-change filter (select='gt(scene,N)') for true scene-cut detection.
        This function is best used as a final editing optimization to avoid mid-frame tearing,
        not as scene-change evidence.
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
            key_times = []
            for line in res.stderr.splitlines():
                if "iskey:1" in line:
                    match = re.search(r"pts_time:([\d\.]+)", line)
                    if match:
                        # pts_time is relative to the -ss seek point
                        offset = float(match.group(1))
                        key_times.append(start_probe + offset)

            if key_times:
                closest = min(key_times, key=lambda kt: abs(kt - target_sec))
                if abs(closest - target_sec) <= 1.5:
                    return round(closest, 3)
        except Exception:
            pass

        return round(target_sec, 3)
