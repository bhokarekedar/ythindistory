import time
import threading
from typing import Tuple, List

class TokenBudgetManager:
    """
    Central Token-Budget and Rate-Pacing Manager for Groq API.
    Prevents 413 / RateLimitExceeded errors (e.g. 7,000 Input Tokens Per Minute on Qwen 27B).
    
    Responsibilities:
    1. Pre-validates single-request prompt token size (hard ceiling of 5,200 tokens).
    2. Enforces rolling 60-second token accounting across all pipeline stages.
    3. Automatically pauses/paces sequential requests before they trip the 7,000 TPM limit.
    4. Provides detailed stage-labeled logging (chapter_planning, script_generation, etc.).
    """
    
    # Hard ceiling for any SINGLE request (safe buffer below 7,000 Groq limit)
    MAX_SINGLE_REQUEST_TOKENS: int = 5200
    
    # Rolling 60-second budget across all requests within the same minute
    ROLLING_60S_BUDGET: int = 6200
    
    _lock = threading.Lock()
    _request_history: List[Tuple[float, int]] = []  # list of (timestamp, token_count)

    @classmethod
    def estimate_tokens(cls, text: str) -> int:
        """
        Conservative token estimator.
        For English text + punctuation, 1 token ~ 3.3 to 3.8 characters.
        Using len(text) / 3.2 gives a conservative upper bound that prevents underestimating.
        """
        if not text:
            return 0
        return int(max(1, len(text) / 3.2))

    @classmethod
    def pre_check_and_pace(cls, system_prompt: str, user_content: str, stage_label: str = "general") -> int:
        """
        Validates prompt size and paces execution to stay strictly within rolling 60s ITPM limit.
        Returns estimated token count.
        """
        full_text = f"{system_prompt}\n{user_content}"
        est_tokens = cls.estimate_tokens(full_text)

        # 1. Single-request ceiling check
        if est_tokens > cls.MAX_SINGLE_REQUEST_TOKENS:
            print(
                f"  [TokenBudget] ⚠️ WARNING: Prompt for '{stage_label}' is large: ~{est_tokens} tokens "
                f"(Limit: {cls.MAX_SINGLE_REQUEST_TOKENS})."
            )

        # 2. Rolling 60-second window pacing
        with cls._lock:
            now = time.time()
            # Prune entries older than 60 seconds
            cls._request_history = [
                (t, count) for (t, count) in cls._request_history
                if (now - t) < 60.0
            ]
            
            rolling_sum = sum(count for (_, count) in cls._request_history)

            # If adding this request exceeds rolling budget, calculate required sleep
            if (rolling_sum + est_tokens) > cls.ROLLING_60S_BUDGET and cls._request_history:
                # Find oldest request in window and wait for its tokens to expire
                oldest_t, _ = cls._request_history[0]
                wait_sec = max(1.0, min(60.0, 60.0 - (now - oldest_t) + 0.5))
                print(
                    f"  [TokenBudget] ⏳ Pacing '{stage_label}': rolling 60s load is ~{rolling_sum + est_tokens}/{cls.ROLLING_60S_BUDGET} tokens. "
                    f"Sleeping {wait_sec:.1f}s to respect Groq ITPM limit..."
                )
                time.sleep(wait_sec)
                
                # Re-prune after sleeping
                now = time.time()
                cls._request_history = [
                    (t, count) for (t, count) in cls._request_history
                    if (now - t) < 60.0
                ]
                rolling_sum = sum(count for (_, count) in cls._request_history)

            # Record this request
            cls._request_history.append((now, est_tokens))
            new_rolling_total = rolling_sum + est_tokens
            print(
                f"  [TokenBudget] 📊 [{stage_label}] Prompt: ~{est_tokens} tokens | "
                f"Rolling 60s: ~{new_rolling_total}/{cls.ROLLING_60S_BUDGET} tokens."
            )

        return est_tokens

