import os

class ApiKeyManager:
    """Manages rotation of GROQ API keys across application restarts."""
    
    def __init__(self, state_file="temp/api_key_state.txt"):
        self.state_file = state_file
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        
    def get_next_key(self) -> str:
        key1 = os.environ.get("GROQ_API_KEY")
        key2 = os.environ.get("GROQ_API_KEY_TWO")
        
        if not key1 and not key2:
            return None
        if key1 and not key2:
            return key1
        if key2 and not key1:
            return key2
            
        # Both keys exist, read state
        last_used = "1"
        if os.path.exists(self.state_file):
            with open(self.state_file, "r") as f:
                last_used = f.read().strip()
                
        if last_used == "1":
            next_key_str = "2"
            key_to_use = key2
        else:
            next_key_str = "1"
            key_to_use = key1
            
        with open(self.state_file, "w") as f:
            f.write(next_key_str)
            
        print(f"[API KEY] Using GROQ_API_KEY_{'TWO' if next_key_str == '2' else 'ONE'}")
        return key_to_use
