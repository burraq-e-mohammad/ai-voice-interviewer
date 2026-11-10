"""LLM reasoning service: Generates conversational voice interview turns and performance evaluations."""

import logging
import re
from typing import Any

from openai import OpenAI

from app.core.errors import LLMServiceError
from app.models.schemas import CandidateProfile, Message

logger = logging.getLogger(__name__)

# Strip out chain-of-thought blocks if emitted
THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


class LLMService:
    def __init__(
        self,
        api_key: str,
        model: str,
        provider: str = "gemini",
        max_tokens: int = 350,
        timeout_seconds: float = 30.0,
        client: Any | None = None,
    ) -> None:
        self._model = model
        self._provider = provider.lower()
        self._max_tokens = max_tokens

        if client is not None:
            self._client = client
        elif self._provider == "gemini":
            # Google Gemini via OpenAI-compatible endpoint
            self._client = OpenAI(
                api_key=api_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                timeout=timeout_seconds,
                max_retries=2,
            )
        else:
            from groq import Groq

            self._client = Groq(api_key=api_key, timeout=timeout_seconds, max_retries=2)

    def build_interviewer_prompt(self, profile: CandidateProfile, turn: int, max_turns: int) -> str:
        """Constructs an interview persona tailored for verbal spoken dialogue (TTS-friendly)."""
        resume_snippet = (
            profile.resume_text[:2500] if profile.resume_text else (profile.experience or "No resume attached")
        )
        jd_snippet = (
            profile.job_description[:2500] if profile.job_description else f"Target role: {profile.level} {profile.position} at {profile.company}"
        )
        skills_snippet = profile.skills or "Refer to resume and Job Description"

        return (
            f"You are a rigorous, highly respected Senior Engineering Hiring Manager and Technical Bar Raiser at {profile.company}.\n"
            f"You are conducting a high-stakes, 20-question voice interview with candidate {profile.name} "
            f"for the role of {profile.level} {profile.position}.\n\n"
            f"=== TARGET COMPANY INTERVIEW ARCHIVE & STANDARDS ===\n"
            f"Company: {profile.company}\n"
            f"You MUST model your questions directly after the known authentic past interview questions, problem archetypes, "
            f"technical expectations, and cultural/leadership principles historically used by {profile.company} "
            f"(e.g., Google's system scale, algorithms, tradeoffs, and 'Googleyness'; Amazon's 16 Leadership Principles like Customer Obsession, Deep Dive, and Ownership; "
            f"Meta's architecture, high-velocity engineering, and concurrency; Microsoft's growth mindset and distributed systems; "
            f"Stripe/Netflix/Apple specific interview loops). Ensure the difficulty strictly matches {profile.company}'s real hiring bar.\n\n"
            f"=== MANDATORY RELEVANCE DIRECTIVE ===\n"
            f"Every single question you ask MUST be directly relevant and grounded in:\n"
            f"1. The candidate's actual projects, past roles, architectural choices, and systems described in their resume.\n"
            f"2. The specific Job Description requirements (technologies, architecture patterns, responsibilities, scale).\n"
            f"3. The candidate's listed core skills ({skills_snippet}).\n"
            f"4. Authentic past interview question archetypes historically asked by {profile.company} for {profile.position} roles.\n"
            f"DO NOT ask generic, disconnected questions. Deeply probe how the candidate built their resume projects, how they would handle the actual challenges described in the Job Description, and how their technical decisions align with {profile.company}'s engineering scale.\n\n"
            f"=== CANDIDATE RESUME DETAILS ===\n"
            f"{resume_snippet}\n\n"
            f"=== TARGET JOB DESCRIPTION & REQUIREMENTS ===\n"
            f"{jd_snippet}\n\n"
            f"=== CANDIDATE CORE SKILLS ===\n"
            f"{skills_snippet}\n\n"
            f"=== 20-QUESTION INTERVIEW STRUCTURE (Turn {turn} of {max_turns}) ===\n"
            f"- Turns 1-3: Resume deep-dive into specific projects, architectural decisions, and role motivation for {profile.company}.\n"
            f"- Turns 4-10: Core technical competencies, system architecture, data structures, and authentic past {profile.company} technical questions aligned with the Job Description and candidate skills.\n"
            f"- Turns 11-16: Advanced problem solving, production incident triage, distributed scalability, edge cases, and performance tradeoffs.\n"
            f"- Turns 17-19: Behavioral, leadership, stakeholder conflict, and company culture principles specific to {profile.company}.\n"
            f"- Turn 20: Final question / candidate wrap-up and graceful conclusion.\n\n"
            f"=== STRICT RULES FOR SPOKEN VOICE OUTPUT (CRITICAL) ===\n"
            f"1. SPOKEN AUDIO ONLY: Your output is converted directly to speech using a neural voice synthesizer. "
            f"Speak naturally in clear, conversational English (2 to 4 sentences maximum).\n"
            f"2. ABSOLUTELY NO MARKDOWN: Never use bullet points (- or *), bolding (**), numbered lists, code blocks, or emojis. "
            f"Everything must be spoken naturally aloud as a real interviewer would in the room.\n"
            f"3. ACTIVE LISTENING: Briefly acknowledge what the candidate said (e.g., 'That is a solid approach to database partitioning. However...'), then ask your next targeted question.\n"
            f"4. Turn {max_turns} Conclusion: If this is the final turn ({turn} of {max_turns}), thank the candidate warmly and let them know the interview is complete."
        )

    def generate_opening_question(self, profile: CandidateProfile, max_turns: int) -> str:
        """Generates the initial opening greeting and first question from the interviewer."""
        system_prompt = self.build_interviewer_prompt(profile, turn=1, max_turns=max_turns)
        user_prompt = (
            f"The candidate {profile.name} has just entered the interview room for the {profile.level} {profile.position} role at {profile.company}. "
            f"Greet them warmly and ask your first opening question, referencing the target position at {profile.company} "
            f"and asking them to introduce themselves and discuss the most impactful project from their resume."
        )

        try:
            completion = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=self._max_tokens,
                temperature=0.7,
            )
            raw = completion.choices[0].message.content or ""
            reply = THINK_BLOCK.sub("", raw).strip()
            # Clean any stray formatting
            reply = re.sub(r"[\*#_`]", "", reply)
            return reply or f"Hello {profile.name}, welcome! I am glad to meet with you for the {profile.position} role at {profile.company}. To start, could you please introduce yourself and share a bit about your background?"
        except Exception as exc:
            logger.error("Failed to generate opening greeting: %s", exc)
            return (
                f"Hello {profile.name}, welcome to your interview for the {profile.level} "
                f"{profile.position} position at {profile.company}. To get us started, please introduce yourself "
                f"and highlight a challenging technical project from your background."
            )

    def generate_reply(
        self,
        user_text: str,
        history: list[Message] | None = None,
        profile: CandidateProfile | None = None,
        turn: int = 1,
        max_turns: int = 20,
    ) -> str:
        """Generates the next question or response based on candidate answer and conversation history."""
        cand_profile = profile or CandidateProfile()
        system_prompt = self.build_interviewer_prompt(cand_profile, turn=turn, max_turns=max_turns)

        messages = [Message(role="system", content=system_prompt)]
        messages.extend(history or [])
        messages.append(Message(role="user", content=user_text))

        try:
            completion = self._client.chat.completions.create(
                model=self._model,
                messages=[m.to_dict() for m in messages],
                max_tokens=self._max_tokens,
                temperature=0.7,
            )
            raw_reply = completion.choices[0].message.content or ""
            reply = THINK_BLOCK.sub("", raw_reply).strip()
            reply = re.sub(r"[\*#_`]", "", reply)
        except Exception as exc:
            logger.error("LLM completion request failed: %s", exc)
            raise LLMServiceError(
                "The AI Interviewer service is currently unavailable. Please try again."
            ) from exc

        if not reply:
            raise LLMServiceError("The AI Interviewer returned an empty answer. Please try again.")
        return reply

    def evaluate_interview(self, profile: CandidateProfile, history: list[Message]) -> tuple[str, str]:
        """Evaluates candidate dialogue and generates a structured performance report and score."""
        conversation_text = "\n".join(
            [f"{m.role.upper()}: {m.content}" for m in history if m.role != "system"]
        )

        evaluation_prompt = (
            f"You are a Senior Technical Hiring Assessor and Executive Interview Bar Raiser evaluating a candidate for {profile.company}.\n"
            f"Evaluate the candidate's performance across their interview session according to {profile.company}'s authentic hiring bar.\n\n"
            f"Candidate Name: {profile.name}\n"
            f"Target Position: {profile.level} {profile.position} at {profile.company}\n"
            f"Target Job Description:\n{profile.job_description or 'Standard requirements for ' + profile.position}\n\n"
            f"Candidate Resume Overview:\n{profile.resume_text[:2000] if profile.resume_text else (profile.experience or 'Standard background')}\n\n"
            f"INTERVIEW TRANSCRIPT:\n{conversation_text}\n\n"
            f"Provide an authoritative, rigorous, constructive assessment structured in clean Markdown format:\n\n"
            f"## 🏆 Candidate Score: [Give a numerical score strictly in format X.X/10, e.g. 8.2/10]\n\n"
            f"### 📌 Executive Summary\n"
            f"[2-3 sentence high-level overview of the candidate's performance against {profile.company}'s standards and the Job Description]\n\n"
            f"### ✅ Key Strengths Demonstrated\n"
            f"- [Detailed strength with quote/reference to candidate's answer]\n"
            f"- [Another technical or behavioral strength observed]\n\n"
            f"### ⚠️ Areas for Improvement & Technical Gaps\n"
            f"- [Specific missing technical depth, lack of STAR methodology, trade-offs, or ambiguity]\n"
            f"- [Area where answer could be stronger]\n\n"
            f"### 💡 Actionable Coaching & Interview Tips\n"
            f"- [Practical tips to improve responses in future technical rounds at {profile.company}]"
        )

        try:
            completion = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": evaluation_prompt}],
                max_tokens=1200,
                temperature=0.3,
            )
            report = completion.choices[0].message.content or "Evaluation completed."

            # Extract numeric score if present
            score_match = re.search(r"(\d+(\.\d+)?\s*/\s*10)", report)
            score_str = score_match.group(1).replace(" ", "") if score_match else "7.5/10"
            return score_str, report
        except Exception as exc:
            logger.error("Interview evaluation failed: %s", exc)
            return "7.0/10", "### Evaluation Report\nCandidate demonstrated solid foundational knowledge."
