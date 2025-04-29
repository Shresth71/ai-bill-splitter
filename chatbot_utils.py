import json
import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

class GeminiExpenseChatbot:
    def __init__(self):
        # For version 0.4.1, we need to use a different approach instead of system_instruction
        self.model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
        )
        
        # The prompt prefix that will be prepended to user inputs
        self.prompt_prefix = """
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
            
            User input: 
        """

    def process_expense(self, input_text: str):
        """Parse and return structured expense data"""
        try:
            # Combine the prompt prefix with the user input
            full_prompt = self.prompt_prefix + input_text
            
            response = self.model.generate_content(full_prompt)
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
