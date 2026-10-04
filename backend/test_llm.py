import os
import json
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
client = Groq()

segments = [
    {"id": 1, "text": "मैं यहां तुमसे बात करने आया था।\nपिछली बार हमने सब कुछ सच-सच नहीं बताया"},
    {"id": 2, "text": "था।"},
    {"id": 3, "text": "आज तुम्हारे मैनेजर का कॉल आया था कि वो\nतुम्हारा इंतजार कर रहा था। अब यह मत कहना"},
    {"id": 4, "text": "तुम जीहान के साथ आई हो।\nक्या? नहीं। तुम फिर से पुरानी आदतों का"}
]

prompt = """You are a Hindi linguistic expert.
Your task is to analyze fragmented subtitle text and determine which fragments should be merged to form logical, complete sentences.
Rules:
1. Return strictly a JSON object with a single key 'groups' containing a list of lists of the IDs that should be merged.
2. Example Output: {"groups": [[1, 2], [3], [4, 5, 6]]}
3. KEEP GROUPS AS SMALL AS POSSIBLE! If a fragment ends with a natural pause (like a comma, clause boundary, or words like 'hai', 'tha', 'ho'), DO NOT merge it with the next one.
4. ONLY merge fragments that are completely broken mid-sentence and require immediate continuation to make grammatical sense.
5. Make sure every single ID provided in the input is accounted for exactly once in the output groups.
"""
input_data = [{"id": s["id"], "text": s["text"]} for s in segments]
user_content = f"Fragments:\n{json.dumps(input_data, ensure_ascii=False)}"

completion = client.chat.completions.create(
    model="llama3-70b-8192",
    messages=[
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_content}
    ],
    response_format={"type": "json_object"},
    temperature=0.0
)

print(completion.choices[0].message.content)
