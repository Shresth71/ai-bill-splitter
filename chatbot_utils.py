import json
import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

class GeminiExpenseChatbot:
    def __init__(self):
        self.model = genai.GenerativeModel(model_name="gemini-1.5-flash")
        self.instruction = """
        Extract bill details STRICTLY in this JSON format:
        {
            "amount": number, 
            "paid_by": string (default: "You"),
            "participants": list (including payer),
            "description": string,
            "date": string (YYYY-MM-DD, default: today),
            "category": string (optional, e.g., Food, Travel)
        }
        If amount is missing, return {"error": "No amount found"}
        """

    def process_expense(self, input_text: str):
        """Parse and return structured expense data"""
        try:
            response = self.model.generate_content([
                {"role": "system", "parts": [self.instruction]},
                {"role": "user", "parts": [input_text]}
            ])
            json_str = response.text.strip().removeprefix("```json").removesuffix("```").strip()
            data = json.loads(json_str)

            if "error" in data:
                return {"status": "error", "message": data["error"]}
            if "amount" not in data or data["amount"] is None:
                return {"status": "error", "message": "No amount specified"}

            return {
                "status": "success",
                "amount": float(data["amount"]),
                "paid_by": data.get("paid_by", "You"),
                "description": data.get("description", "expense"),
                "date": data.get("date", "today"),
                "participants": list(set(data.get("participants", ["You"]))),
                "category": data.get("category", "other")
            }

        except Exception as e:
            return {"status": "error", "message": f"Parsing failed: {str(e)}"}
