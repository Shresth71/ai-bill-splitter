import json
import os
import google.generativeai as genai
from dotenv import load_dotenv
import datetime

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
            You are an expense parsing assistant.
            Extract bill details STRICTLY in this JSON format:
            {
                "amount": number, 
                "paid_by": string (default: "You"),
                "participants": list (including payer),
                "description": string,
                "date": string (YYYY-MM-DD, default: today),
                "category": string (optional, e.g., Food, Travel)
            }
            
            Return ONLY the JSON with no additional text or explanation.
            If amount is missing, return {"error": "No amount found"}
            
            User expense: 
        """

    def process_expense(self, input_text: str):
        """Parse and return structured expense data"""
        try:
            # Combine the prompt prefix with the user input
            full_prompt = self.prompt_prefix + input_text
            
            response = self.model.generate_content(full_prompt)
            response_text = response.text.strip()
            
            # Extract JSON from response (remove any markdown code blocks if present)
            if "```json" in response_text or "```" in response_text:
                json_str = response_text.replace("```json", "").replace("```", "").strip()
            else:
                json_str = response_text
            
            # Handle potential formatting issues in the response
            json_str = json_str.replace('\n', ' ').replace('\r', '')
            
            # Print for debugging
            print(f"Received JSON: {json_str}")
            
            data = json.loads(json_str)

            # Basic validation
            if "error" in data:
                return {"status": "error", "message": data["error"]}
            if "amount" not in data or data["amount"] is None:
                return {"status": "error", "message": "No amount specified"}

            # Handle 'today' as date
            if data.get("date") == "today":
                data["date"] = datetime.datetime.now().strftime("%Y-%m-%d")
                
            # Ensure participants is a list and contains at least the payer
            if "participants" not in data or not data["participants"]:
                data["participants"] = [data.get("paid_by", "You")]
            elif data.get("paid_by") not in data["participants"]:
                data["participants"].append(data.get("paid_by", "You"))

            # Build the result object
            result = {
                "status": "success",
                "amount": float(data["amount"]),
                "paid_by": data.get("paid_by", "You"),
                "description": data.get("description", "expense"),
                "date": data.get("date"),
                "participants": list(set(data.get("participants", ["You"]))),
                "category": data.get("category", "Other")
            }
            
            # Print for debugging
            print(f"Processed expense: {result}")
            
            return result

        except json.JSONDecodeError as e:
            print(f"JSON Decode Error: {str(e)}")
            print(f"Response text: {response.text}")
            return {"status": "error", "message": f"Invalid JSON response: {str(e)}"}
        except Exception as e:
            print(f"Error in process_expense: {str(e)}")
            return {"status": "error", "message": f"Parsing failed: {str(e)}"}
