# skill: summarize
# description: Summarize text into key bullet points
# tags: text, productivity, utility
# version: 1.0
# created: 2026-04-28

def run(text: str = "", max_bullets: int = 5, **kwargs) -> str:
    if not text:
        return "Provide text to summarize: skill_summarize text=<your text>"
    sentences = [s.strip() for s in text.replace('\n', ' ').split('.') if len(s.strip()) > 20]
    if len(sentences) <= 3:
        return text
    n = min(int(max_bullets), len(sentences))
    step = max(1, len(sentences) // n)
    selected = [sentences[i * step] for i in range(n) if i * step < len(sentences)]
    return "Summary:\n" + "\n".join(f"• {s.strip('., ')}" for s in selected)
