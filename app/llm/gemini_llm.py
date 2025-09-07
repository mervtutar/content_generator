# app/llm/gemini_llm.py
import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

class GeminiLLM:
    def __init__(self, model="gemini-2.5-flash", temperature=0.7):
        self.model = genai.GenerativeModel(model)
        self.temperature = temperature

    def invoke(self, prompt: str) -> str:
        resp = self.model.generate_content(
            prompt,
            generation_config={"temperature": self.temperature}
        )
        return (resp.text or "").strip()
