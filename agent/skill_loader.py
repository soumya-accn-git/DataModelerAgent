"""
Skill loader — reads a SKILL.md file and returns its content as a string
to be injected into LLM system prompts as guardrails.
"""
import os

def load_skill(skill_path: str, max_chars: int = 2000) -> str:
    """
    Load a SKILL.md file and return a condensed version for LLM injection.
    Strips YAML frontmatter and trims to max_chars to avoid bloating the prompt.
    """
    if not os.path.exists(skill_path):
        return ""
    try:
        with open(skill_path, "r", encoding="utf-8") as f:
            content = f.read()
        # Strip YAML frontmatter (--- ... ---)
        if content.startswith("---"):
            end = content.find("---", 3)
            if end != -1:
                content = content[end+3:].strip()
        # Keep only the most critical sections (rules 1-3 + examples)
        # to stay within token budget
        return content[:max_chars]
    except Exception:
        return ""
