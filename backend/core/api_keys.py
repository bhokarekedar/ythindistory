import os

class ApiKeyManager:
    """Manages rotation of GROQ API keys across application restarts."""
    
    def __init__(self, state_file="temp/api_key_state.txt"):
        self.state_file = state_file
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        
    def get_next_key(self) -> str:
        keys = []
        for name in ["GROQ_API_KEY", "GROQ_API_KEY_TWO", "GROQ_API_KEY_THREE", "GROQ_API_KEY_FOUR"]:
            val = os.environ.get(name)
            if val and val not in keys:
                keys.append(val)
                
        if not keys:
            return None
            
        last_idx = 0
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    last_idx = int(f.read().strip())
            except:
                last_idx = 0
                
        next_idx = (last_idx + 1) % len(keys)
        try:
            with open(self.state_file, "w") as f:
                f.write(str(next_idx))
        except:
            pass
            
        print(f"[API KEY] Using Groq Key #{next_idx + 1} of {len(keys)}")
        return keys[next_idx]
