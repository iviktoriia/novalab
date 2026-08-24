
class AIAgent:
    """Заглушка: AI-анализ кода отключён."""
    def analyze_code(self, *args, **kwargs):
        return {"error": "AI disabled", "suggested_grade": None, "main_issues": [], "suggestions": [], "style_issues": 0, "message": "AI отключён"}

    def is_model_loaded(self):
        return False

ai_agent = AIAgent()
