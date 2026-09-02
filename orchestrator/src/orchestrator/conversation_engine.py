"""LLM-powered conversational engine for DaantShaant assistant.

All assistant text generation flows through the shared, provider-neutral
:class:`~orchestrator.ai.gateway.AIGateway` (Phase 2A.4): Qwen primary with a
Gemini technical fallback. This module never talks to a provider SDK, and it
composes the gateway lazily so importing it costs no AI-adapter work.
"""

import logging
import re
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from orchestrator.chat_schemas import AnalysisHistoryContext, MessageContext
from orchestrator.rag.retrieval_service import retrieval_service
from orchestrator import conversation_state as cs

if TYPE_CHECKING:  # pragma: no cover - typing only, keeps runtime import cheap
    from orchestrator.ai.gateway import AIGateway

logger = logging.getLogger(__name__)


ASSISTANT_SYSTEM_PROMPT = """You are DaantShaant - a friendly, knowledgeable local dentist texting a patient or friend. You are chill, professional (70% professional, 30% friendly human), and you have a great memory.

Tone & Personality Rules:
- Sound like a real person texting, not a chatbot. Use casual transitions like "Honestly", "Unfortunately", "Actually", "Usually".
- Subtle dentist humor is great: "Your gums are basically protesting a bit 😅" or "That yellow hard stuff sounds like tartar honestly."
- Use natural contractions (you're, it's, don't, can't). Avoid clinical/medical jargon unless simplified first.
- NO markdown formatting ever. Output plain text only. No bold (**), no bullet points, no numbered lists, no headers (#). Use a natural single-paragraph flow or simple line breaks.

ANSWER-FIRST RULE (MANDATORY — HIGHEST PRIORITY):
- You MUST answer the user's question or address their concern FIRST, in the very first 1-3 sentences of your response.
- If the user asks "Why do gums bleed?" — your FIRST sentence must explain WHY gums bleed. Do NOT start with a follow-up question like "Does it happen while brushing?".
- If the user describes a symptom — your FIRST sentence must acknowledge and explain it. Give the cause, explanation, or advice BEFORE asking anything.
- Follow-up questions are ONLY allowed AFTER you have fully answered. They go at the END of your message, never at the beginning.
- NEVER start your response with a question. NEVER respond to a factual dental query with only a question.
- Example of CORRECT behavior: User says "Why do gums bleed?" → You say "Gums usually bleed because plaque builds up near the gumline and irritates the tissue..." then optionally ask a clarifying question at the end.
- Example of WRONG behavior: User says "Why do gums bleed?" → You say "Does it happen while brushing?" — this is FORBIDDEN.

No Repetitive Patterns & Opening Variation:
- DO NOT start consecutive or multi-turn messages with templated phrases like: "Oh no", "That sounds rough", "Yeah that can happen", "I see", "Usually it's because".
- VARY your openers! Start directly with the topic or advice. For example: "Honestly, that yellow stuff is...", "Actually, sensitivity is super common...", "Warm saltwater rinses will...", "If your teeth are aching...".
- Keep your conversational openings extremely diverse and direct.

RAG Naturalization (Invisible Knowledge):
- Synthesize, simplify, and conversationalize all dental knowledge. Never sound like you copied an article.
- NEVER cite organizations, dentistry boards (like "ADA" or "American Dental Association"), journals, or scientific studies.
- Speak entirely from your own expert perspective as their friendly dentist. Translate terms like "gingivitis" or "dental calculus" into "irritated gums" or "hardened plaque (tartar)". Keep it simple and practical!

Dentist Recommendations:
- Suggest a dentist visit naturally and only when it's really needed (e.g., severe pain, swelling, infection, hard tartar, deep cavities). Don't paste clinical disclaimers at the end of every message.
"""


# Phrases the LLM should never output — caught in post-processing
BANNED_PHRASES = [
    r"what would you like to know",
    r"how may i assist",
    r"how can i assist",
    r"feel free to ask",
    r"i'm here to help",
    r"i am here to help",
    r"don't hesitate to ask",
    r"let me know if you have",
    r"is there anything else",
    r"how can i help you today",
    r"what can i help you with",
    r"i'd be happy to help",
    r"i can certainly help",
    r"as an ai",
    r"can you tell me more",
    r"could you describe",
    r"could you tell me",
]


class ConversationEngine:
    """Conversation engine backed by the shared DaantShaant AI gateway."""

    def __init__(self, gateway: "AIGateway | None" = None) -> None:
        # Injectable for tests; production resolves the lazily composed
        # process-wide gateway on first generation (never at import time).
        self._gateway = gateway

    @property
    def gateway(self) -> "AIGateway":
        if self._gateway is None:
            from orchestrator.ai.factory import get_ai_gateway

            self._gateway = get_ai_gateway()
        return self._gateway

    async def _generate_text(
        self,
        *,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.7,
        max_tokens: int = 600,
        user_raw_message: str = "",
        active_issue: Optional[str] = None,
    ) -> str:
        """Generate assistant text through :class:`AIGateway` (Qwen -> Gemini).

        The model is intentionally not set on the request: each provider
        resolves its own configured model (``QWEN_CHAT_MODEL`` primary,
        ``GEMINI_MODEL`` fallback), which keeps this caller provider-neutral.

        Configuration and programming errors propagate untouched (they must
        never be masked by a provider switch). Only a fully technical
        double-provider failure degrades to the historic issue-aware
        deterministic dental answer, so the patient still gets a reply.
        """
        from orchestrator.ai.exceptions import AllProvidersFailedError
        from orchestrator.ai.schemas import ChatMessage, TextRequest

        request = TextRequest(
            messages=[
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(role="user", content=user_message),
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        started = time.perf_counter()
        try:
            result = await self.gateway.generate_text(request)
        except AllProvidersFailedError as exc:
            from orchestrator.ai.fallbacks import get_deterministic_fallback

            logger.warning(
                "[CHAT] status=all_providers_failed reason=%s latency_ms=%s",
                type(exc).__name__,
                round((time.perf_counter() - started) * 1000.0, 1),
            )
            return get_deterministic_fallback(user_raw_message or user_message, active_issue)

        content = (result.content or "").strip()
        self._log_ai_result("main", result)
        logger.info(
            "[CHAT] status=%s provider=%s model=%s latency_ms=%s fallback_used=%s",
            "ok" if content else "empty",
            result.provider,
            result.model,
            result.latency_ms,
            result.fallback_used,
        )
        if not content:
            from orchestrator.ai.fallbacks import get_deterministic_fallback

            return get_deterministic_fallback(user_raw_message or user_message, active_issue)
        return content

    def _is_incomplete(self, text: str) -> bool:
        """Check if a text represents an incomplete, truncated, or dangling response."""
        if not text:
            return False
        text = text.strip()
        
        # 1. Basic check: typical sentence ending punctuation or common friendly emojis
        valid_endings = ('.', '!', '?', '"', ')', '😅', '🦷', '😊', '👍', '😉', '👌', 'side', 'day', 'week')
        if not text.endswith(valid_endings):
            return True

        # 2. Check for hanging conjunctions/prepositions/contraction auxiliaries at the very end
        words = text.split()
        if words:
            last_word = words[-1].lower().strip(".,!?\"'()😅🦷😊👍😉👌")
            hanging_words = {
                "and", "but", "if", "because", "so", "or", "with", "for", "at", 
                "by", "to", "then", "they'll", "i'm", "you're", "it's", "we've", "who", "which", "than",
                "about", "like", "just", "probably", "maybe", "should", "would", "could", "will", "can", "from"
            }
            if last_word in hanging_words:
                return True

        # 3. Check for dangling future promises, unfinished explanations, or incomplete semantic clauses
        # E.g., "They'll...", "You should probably...", "If that continues...", "Because...", "Make sure to..."
        dangling_patterns = [
            r'\b(they\'ll|you\s+should|you\s+probably|if\s+that|make\s+sure|so\s+if|because|we\s+will|you\s+can|you\'ll|it\s+will|you\s+need|try\s+to|it\'s\s+best\s+to|should\s+probably|if\s+it|when\s+you|seems\s+like|make\s+sure\s+you|would\s+be|could\s+be|you\s+might\s+want\s+to)\s*$',
            r'\b(and|but|if|because|so|or|with|for|at|by|to|then|who|which|than|about|like|just|probably|maybe|should|would|could|will|can|from)\s*$',
            r'\b(if\s+that\s+continues|if\s+this\s+keeps\s+up|if\s+it\s+hurts|if\s+the\s+pain)\s*$'
        ]
        text_lower = text.lower().strip(".,!?\"'()😅🦷😊👍😉👌")
        for pattern in dangling_patterns:
            if re.search(pattern, text_lower):
                return True
                
        return False

    def _log_ai_result(self, stage: str, result) -> None:
        """Log AI call metadata without exposing sensitive data."""
        logger.info(
            "[CHAT_AI] stage=%s provider=%s model=%s fallback_used=%s provider_latency_ms=%.1f",
            stage,
            result.provider,
            result.model,
            result.fallback_used,
            result.latency_ms,
        )

    async def _try_complete_response(self, system_prompt: str, user_message: str, partial_response: str) -> str:
        """Attempt to complete an abruptly ended response using a fast gateway completion call, falling back to trimming."""
        if not partial_response:
            return partial_response
            
        partial_response = partial_response.strip()
        if not self._is_incomplete(partial_response):
            return partial_response
            
        logger.info(f"[ENGINE] Detected incomplete response: '{partial_response[-35:]}'. Attempting tail completion.")
        
        # Fast continuation prompt
        continuation_prompt = f"""The assistant was replying to this message: "{user_message}"
The assistant generated this partial response: "{partial_response}"

Finish the final sentence naturally and completely. Do not repeat what was already written. Respond with ONLY the missing tail part to make it a complete sentence. Output plain text only."""
        
        try:
            tail = await self._generate_text(
                system_prompt="You complete half-finished sentences from another assistant. Output only the completion. No repeating. Keep it extremely brief.",
                user_message=continuation_prompt,
                temperature=0.5,
                max_tokens=60,
                user_raw_message="",
            )
            tail = tail.strip()
            # Clean tail of prefix markers if any
            if ":" in tail and any(tail.lower().startswith(p) for p in ["completion:", "tail:", "reply:", "response:"]):
                tail = tail.split(":", 1)[1].strip()
                
            combined = f"{partial_response} {tail}"
            combined = re.sub(r'\s+', ' ', combined).strip()
            
            if not self._is_incomplete(combined):
                logger.info(f"[ENGINE] Successfully completed response: '{combined[-35:]}'")
                return combined
        except Exception as e:
            logger.warning(f"[ENGINE] Failed to complete response via API: {e}")
            
        # Fallback: Trim back to the last punctuation mark (making sure we don't trim to another incomplete state)
        logger.info("[ENGINE] Falling back to sentence trimming for completion.")
        current_trimmed = partial_response
        for _ in range(3):  # up to 3 passes of trimming to avoid trailing dangling markers
            last_punc = -1
            for i in range(len(current_trimmed) - 1, -1, -1):
                if current_trimmed[i] in ('.', '!', '?'):
                    last_punc = i
                    break
                    
            if last_punc != -1:
                candidate = current_trimmed[:last_punc + 1].strip()
                if len(candidate) > 15 and not self._is_incomplete(candidate):
                    return candidate
                current_trimmed = current_trimmed[:last_punc].strip()  # step past this punctuation mark and keep looking back
            else:
                break
                
        return partial_response
    
    def _build_conversation_memory(self, recent_messages: List[MessageContext]) -> str:
        """Build conversational memory with priority on recent context."""
        if not recent_messages:
            return "No previous conversation."
        
        # Priority: Last 6 messages (3 exchanges) for active context
        memory_parts = []
        for msg in recent_messages[-6:]:
            sender = "User" if msg.sender == "user" else "You"
            # Keep full context for recent messages
            text = msg.text[:200] + "..." if len(msg.text) > 200 else msg.text
            memory_parts.append(f"{sender}: {text}")
        
        return "Recent conversation:\n" + "\n".join(memory_parts)
    
    def _clean_response(self, response: str) -> str:
        """Clean response to remove markdown, generic phrases, and improve formatting."""
        if not response:
            return None
            
        # Remove markdown bold
        response = re.sub(r'\*\*([^*]+)\*\*', r'\1', response)
        
        # Remove markdown italics
        response = re.sub(r'\*([^*]+)\*', r'\1', response)
        
        # Remove markdown headers
        response = re.sub(r'^#+\s+', '', response, flags=re.MULTILINE)
        
        # Remove bullet points
        response = re.sub(r'^\s*[-*•]\s+', '', response, flags=re.MULTILINE)
        
        # Remove numbered lists (1. 2. 3.)
        response = re.sub(r'^\s*\d+\.\s+', '', response, flags=re.MULTILINE)
        
        # Collapse excessive spacing
        response = re.sub(r'\n{3,}', '\n\n', response)
        response = re.sub(r' {2,}', ' ', response)
        
        # Strip banned generic phrases
        for phrase in BANNED_PHRASES:
            response = re.sub(phrase + r'[^.!?]*[.!?]?', '', response, flags=re.IGNORECASE)
        
        # Trim and clean
        response = response.strip()
        
        # Remove duplicate disclaimers
        if response.count("dentist") > 2:
            lines = response.split('\n')
            dentist_lines = [i for i, line in enumerate(lines) if "dentist" in line.lower()]
            if len(dentist_lines) > 1:
                for idx in dentist_lines[:-1]:
                    lines[idx] = ""
                response = '\n'.join([line for line in lines if line])
        
        # Final safety: if response is empty after cleaning, don't return blank
        if not response.strip():
            return None  # Signal caller to use contextual recovery
        
        return response
    
    def _needs_dentist_recommendation(self, user_message: str, context: Dict[str, Any]) -> bool:
        """Determine if dentist recommendation is needed."""
        serious_indicators = [
            'severe pain', 'swelling', 'swollen', 'infection', 'pus',
            'loose tooth', 'broken tooth', 'trauma', 'accident',
            'persistent bleeding', 'won\'t stop bleeding', 'bleeding for days'
        ]
        
        message_lower = user_message.lower()
        return any(indicator in message_lower for indicator in serious_indicators)
    
    async def generate_greeting(self) -> str:
        """Generate a brief, natural greeting."""
        logger.info("[LLM] Generating greeting")
        prompt = "User just greeted you. Respond naturally in 1-2 sentences. Be friendly and casual. Don't introduce yourself or list what you can do."
        
        response = await self._generate_text(
            system_prompt=ASSISTANT_SYSTEM_PROMPT,
            user_message=prompt,
            temperature=0.9,
            max_tokens=80,
            user_raw_message="hello",
        )
        logger.info("[LLM] Greeting generated successfully")
        cleaned = self._clean_response(response)
        if cleaned:
            cleaned = await self._try_complete_response(ASSISTANT_SYSTEM_PROMPT, prompt, cleaned)
        return cleaned or "Hey! What's going on?"
    
    def generate_off_domain_response(self, user_message: str) -> str:
        """Generate polite redirect for non-dental medical questions.
        
        Deterministic — no LLM call needed. Saves tokens.
        """
        logger.info("[ENGINE] Generating off-domain redirect (no LLM)")
        
        responses = [
            "That sounds rough 😅 but I mainly focus on teeth and oral health. A doctor would be better for that one.",
            "Oof, that doesn't sound fun. I'm really only good with dental stuff though — you'd want a doctor for that.",
            "I wish I could help with that but I'm strictly a teeth person 😅 Definitely worth checking with a doctor though.",
        ]
        
        # Simple rotation based on message length for variety
        idx = len(user_message) % len(responses)
        return responses[idx]
    
    def generate_correction_response(self, user_message: str, conversation_id: str) -> str:
        """Generate response acknowledging a correction.
        
        Deterministic — no LLM call. Uses state to re-anchor the conversation.
        """
        logger.info("[ENGINE] Generating correction response (no LLM)")
        
        state = cs.get_state(str(conversation_id))
        
        if state.active_dental_issue:
            issue = state.active_dental_issue
            responses = {
                "toothache": f"Ah got you 😅 So your tooth is hurting. Does it ache constantly or mainly while eating?",
                "bleeding gums": f"Oh my bad 😅 So your gums are bleeding. Does it happen mainly while brushing or randomly?",
                "sensitivity": f"Got it, sorry about that 😅 So your teeth are sensitive. Is it more with cold stuff or hot?",
                "tartar/plaque buildup": f"Ah okay 😅 So you're the one with the buildup. Is the yellow stuff hard or more like a film?",
                "discolored teeth": f"My bad 😅 So your teeth are looking yellow. Has it been like that for a while or is it recent?",
                "cavity/tooth decay": f"Got it 😅 So you're dealing with the cavity situation. Any pain or just visible?",
                "swollen gums": f"Oh okay 😅 So your gums are swollen. Any pain or bleeding along with it?",
                "gum pain": f"Ah right 😅 So your gums are hurting. Does it feel sore all the time or mainly when eating?",
            }
            return responses.get(issue, f"Ah got you 😅 So you're the one dealing with {issue}. Tell me more about what's going on.")
        
        return "Oh my bad 😅 Got it, we're talking about you. So what's been going on with your teeth?"
    
    async def generate_conversational_response(
        self,
        user_message: str,
        recent_messages: List[MessageContext],
        previous_analyses: Optional[List[AnalysisHistoryContext]] = None,
        context_info: Optional[Dict[str, Any]] = None,
        conversation_id: Optional[str] = None,
        skip_rag: bool = False,
    ) -> str:
        """Generate natural conversational response."""
        logger.info("[LLM] Generating conversational response (skip_rag=%s)", skip_rag)
        _prompt_t0 = time.perf_counter()
        
        # Build conversation memory with priority on recent context
        conversation_memory = self._build_conversation_memory(recent_messages)
        
        # Get compact state context (priority over everything else)
        state_context = ""
        if conversation_id:
            state_context = cs.get_context_summary(str(conversation_id))
        
        # Handle casual address naturally
        display_message = user_message
        if context_info and context_info.get("has_casual_address"):
            display_message = context_info.get("cleaned_text", user_message)
        
        # Check if user is asking for summary
        is_summary_request = any(word in user_message.lower() for word in ["summarize", "summary", "sum up", "recap", "tldr"])
        
        if is_summary_request:
            prompt = f"""The user asked you to summarize. Summarize YOUR CONVERSATION with them in 2-3 sentences. Focus on what THEY told you and what YOU advised.

{conversation_memory}

{state_context}

Summarize the conversation naturally and concisely. Don't give generic dental advice."""
        else:
            # Build prompt with state context at TOP (highest priority)
            prompt = f"""The user said: "{user_message}"

{state_context}

{conversation_memory}

IMPORTANT: Answer the user's question or address their concern FIRST in your opening sentences. Do NOT start with a follow-up question.
Respond naturally in 2-4 sentences. Stay on the active topic. Reference what they told you before. If they ask a vague follow-up, answer directly using the active issue."""
        
        # Enhance with RAG only if not a summary request and RAG not skipped
        if not is_summary_request and not skip_rag:
            _rag_t0 = time.perf_counter()
            try:
                enhanced_prompt = await retrieval_service.get_enhanced_prompt(
                    display_message, prompt, conversation_id
                )
                logger.info("[RAG] Enhanced prompt with context")
            except Exception as e:
                logger.warning(f"[RAG] Failed to enhance prompt: {e}")
                enhanced_prompt = prompt
            _rag_retrieval_ms = (time.perf_counter() - _rag_t0) * 1000
            logger.info("[CHAT_TIMING] rag_retrieval_ms=%.1f", _rag_retrieval_ms)
        else:
            if skip_rag:
                logger.info("[RAG] Skipped for this intent")
            enhanced_prompt = prompt
        _prompt_build_ms = (time.perf_counter() - _prompt_t0) * 1000
        logger.info("[CHAT_TIMING] prompt_build_ms=%.1f", _prompt_build_ms)
        
        # Get active issue for deterministic fallback
        active_issue = None
        if conversation_id:
            state = cs.get_state(str(conversation_id))
            active_issue = state.active_dental_issue
        
        # Generate response via the shared AI gateway (Qwen -> Gemini fallback)
        _ai_t0 = time.perf_counter()
        response = await self._generate_text(
            system_prompt=ASSISTANT_SYSTEM_PROMPT,
            user_message=enhanced_prompt,
            temperature=0.8,
            max_tokens=300,
            user_raw_message=user_message,
            active_issue=active_issue,
        )
        _ai_call_ms = (time.perf_counter() - _ai_t0) * 1000
        logger.info("[CHAT_TIMING] ai_call_ms=%.1f", _ai_call_ms)
        
        # Clean response
        response = self._clean_response(response) or response
        
        # Ensure completeness
        if self._is_incomplete(response):
            _tail_t0 = time.perf_counter()
            response = await self._try_complete_response(ASSISTANT_SYSTEM_PROMPT, enhanced_prompt, response)
            _tail_ms = (time.perf_counter() - _tail_t0) * 1000
            logger.info("[CHAT_TIMING] tail_completion_ms=%.1f", _tail_ms)
        
        # Add dentist recommendation only if needed
        if self._needs_dentist_recommendation(user_message, {}):
            if "dentist" not in response.lower():
                response += "\n\nThis sounds like something worth getting checked out by a dentist."
        
        logger.info("[LLM] Conversational response generated successfully")
        return response
    
    async def generate_symptom_response(
        self,
        user_message: str,
        recent_messages: List[MessageContext],
        previous_analyses: Optional[List[AnalysisHistoryContext]] = None,
        context_info: Optional[Dict[str, Any]] = None,
        conversation_id: Optional[str] = None,
        skip_rag: bool = False,
    ) -> str:
        """Generate empathetic response to symptoms."""
        logger.info("[LLM] Generating symptom response (skip_rag=%s)", skip_rag)
        
        conversation_memory = self._build_conversation_memory(recent_messages)
        
        # Get compact state context
        state_context = ""
        active_issue = None
        if conversation_id:
            state_context = cs.get_context_summary(str(conversation_id))
            state = cs.get_state(str(conversation_id))
            active_issue = state.active_dental_issue
        
        # Handle casual address
        display_message = user_message
        if context_info and context_info.get("has_casual_address"):
            display_message = context_info.get("cleaned_text", user_message)
        
        prompt = f"""The user is describing a symptom: "{user_message}"

{state_context}

{conversation_memory}

CRITICAL: Your FIRST 1-3 sentences MUST explain what causes this symptom and give practical advice. Do NOT start with a follow-up question.
After your explanation, you may optionally ask ONE brief follow-up question at the end if it would help you give better advice.
Respond with empathy in 3-5 sentences. Be conversational and supportive. Plain text only."""
        
        # Enhance with RAG context (lowest priority) — skip if requested
        _rag_t0 = time.perf_counter()
        if not skip_rag:
            try:
                enhanced_prompt = await retrieval_service.get_enhanced_prompt(
                    display_message, prompt, conversation_id
                )
            except Exception as e:
                logger.warning(f"[RAG] Failed to enhance prompt: {e}")
                enhanced_prompt = prompt
        else:
            logger.info("[RAG] Skipped for this intent")
            enhanced_prompt = prompt
        _rag_retrieval_ms = (time.perf_counter() - _rag_t0) * 1000
        logger.info("[CHAT_TIMING] rag_retrieval_ms=%.1f", _rag_retrieval_ms)
        
        # Generate via the shared AI gateway (Qwen -> Gemini fallback)
        _ai_t0 = time.perf_counter()
        response = await self._generate_text(
            system_prompt=ASSISTANT_SYSTEM_PROMPT,
            user_message=enhanced_prompt,
            temperature=0.8,
            max_tokens=400,
            user_raw_message=user_message,
            active_issue=active_issue,
        )
        _ai_call_ms = (time.perf_counter() - _ai_t0) * 1000
        logger.info("[CHAT_TIMING] ai_call_ms=%.1f", _ai_call_ms)
        
        # Clean response
        response = self._clean_response(response) or response
        
        # Ensure completeness
        if self._is_incomplete(response):
            _tail_t0 = time.perf_counter()
            response = await self._try_complete_response(ASSISTANT_SYSTEM_PROMPT, enhanced_prompt, response)
            _tail_ms = (time.perf_counter() - _tail_t0) * 1000
            logger.info("[CHAT_TIMING] tail_completion_ms=%.1f", _tail_ms)
        
        # Add dentist recommendation for serious symptoms
        if self._needs_dentist_recommendation(user_message, {}):
            if "dentist" not in response.lower():
                response += "\n\nThis sounds like something you should have a dentist check out."
        
        logger.info("[LLM] Symptom response generated successfully")
        return response
    
    async def generate_analysis_response(
        self,
        user_message: str,
        analysis_result: dict,
        recent_messages: List[MessageContext],
        previous_analyses: Optional[List[AnalysisHistoryContext]] = None
    ) -> str:
        """Generate conversational response for image analysis."""
        logger.info("[LLM] Generating analysis response")
        
        diagnosis = analysis_result.get("diagnosis", {})
        condition = diagnosis.get("condition_label", "Unknown")
        severity = diagnosis.get("severity", "unknown")
        confidence = diagnosis.get("confidence", 0.0)
        
        conversation_memory = self._build_conversation_memory(recent_messages)
        
        prompt = f"""The user shared a photo of their teeth. You analyzed it and found:
- Condition: {condition}
- Severity: {severity}  
- Confidence: {confidence:.0%}

{conversation_memory}

Explain what you see in 4-6 sentences. Be conversational and honest but not alarming. Give practical advice. Keep it natural. Plain text only."""
        
        _ai_t0 = time.perf_counter()
        response = await self._generate_text(
            system_prompt=ASSISTANT_SYSTEM_PROMPT,
            user_message=prompt,
            temperature=0.8,
            max_tokens=400,
            user_raw_message=user_message,
        )
        _ai_call_ms = (time.perf_counter() - _ai_t0) * 1000
        logger.info("[CHAT_TIMING] ai_call_ms=%.1f", _ai_call_ms)
        
        # Clean response
        response = self._clean_response(response) or response
        
        # Ensure completeness
        if self._is_incomplete(response):
            response = await self._try_complete_response(ASSISTANT_SYSTEM_PROMPT, prompt, response)
        
        if not response or len(response.strip()) < 10:
            response = self._fallback_analysis_response(condition, severity)
        
        # Add disclaimer for analysis
        if "analysis" not in response.lower() and "tool" not in response.lower():
            response += "\n\n*This is just an analysis tool - for a proper diagnosis, you'd want to see a dentist.*"
        
        logger.info("[LLM] Analysis response generated successfully")
        return response
    
    async def generate_follow_up_response(
        self,
        user_message: str,
        recent_messages: List[MessageContext],
        conversation_id: Optional[str] = None,
        skip_rag: bool = True,
    ) -> str:
        """Generate natural follow-up response with active issue context.
        
        RAG is skipped by default for follow-ups — they rely on conversation
        context, not external dental knowledge.
        """
        logger.info("[LLM] Generating follow-up response (skip_rag=%s)", skip_rag)
        
        conversation_memory = self._build_conversation_memory(recent_messages)
        
        # Get state context — critical for follow-ups
        state_context = ""
        resolved_issue = None
        if conversation_id:
            state = cs.get_state(str(conversation_id))
            state_context = cs.get_context_summary(str(conversation_id))
            resolved_issue = cs.resolve_follow_up(user_message, state)
        
        # Build a more targeted prompt for follow-ups
        if resolved_issue:
            prompt = f"""The user sent a follow-up message: "{user_message}"

This is about their {resolved_issue} that they mentioned earlier.

{state_context}

{conversation_memory}

Respond naturally in 2-4 sentences. Connect your answer directly to their {resolved_issue}. Be practical and conversational. Plain text only."""
        else:
            prompt = f"""The user sent a brief message: "{user_message}"

{state_context}

{conversation_memory}

Respond naturally in 1-3 sentences based on the conversation context. Remember what you were just talking about. Plain text only."""
        
        # Get active issue for fallback
        active_issue = None
        if conversation_id:
            active_issue = state.active_dental_issue if hasattr(state, 'active_dental_issue') else None
        
        _ai_t0 = time.perf_counter()
        response = await self._generate_text(
            system_prompt=ASSISTANT_SYSTEM_PROMPT,
            user_message=prompt,
            temperature=0.8,
            max_tokens=300,
            user_raw_message=user_message,
            active_issue=active_issue or resolved_issue,
        )
        _ai_call_ms = (time.perf_counter() - _ai_t0) * 1000
        logger.info("[CHAT_TIMING] ai_call_ms=%.1f", _ai_call_ms)
        
        cleaned = self._clean_response(response) or response
        
        # Ensure completeness
        if self._is_incomplete(cleaned):
            _tail_t0 = time.perf_counter()
            cleaned = await self._try_complete_response(ASSISTANT_SYSTEM_PROMPT, prompt, cleaned)
            _tail_ms = (time.perf_counter() - _tail_t0) * 1000
            logger.info("[CHAT_TIMING] tail_completion_ms=%.1f", _tail_ms)
        
        logger.info("[LLM] Follow-up response generated successfully")
        return cleaned

    async def generate_comparison_response(
        self,
        user_message: str,
        analysis_result: Optional[dict],
        previous_analyses: Optional[List[AnalysisHistoryContext]]
    ) -> str:
        """Generate a response comparing current teeth photo findings with history."""
        logger.info("[LLM] Generating comparison response")
        
        if not previous_analyses:
            return "I don't have any previous dental photos in your history to compare this with yet! Try sending a picture first so we have a starting point."
        
        # Sort previous analyses by date descending to find the latest previous one
        sorted_prev = sorted(previous_analyses, key=lambda x: x.created_at, reverse=True)
        latest_prev = sorted_prev[0]
        
        prev_cond = latest_prev.condition_label
        prev_sev = latest_prev.severity
        
        curr_cond = "Healthy"
        curr_sev = "none"
        
        if analysis_result and "diagnosis" in analysis_result:
            diag = analysis_result["diagnosis"]
            curr_cond = diag.get("condition_label", "Healthy")
            curr_sev = diag.get("severity", "none")
        
        # Build prompt for comparisons
        prompt = f"""The user is asking to compare their current dental photo results with their history.
Current results:
- Condition: {curr_cond}
- Severity: {curr_sev}

Previous results (from {latest_prev.created_at.strftime('%Y-%m-%d')}):
- Condition: {prev_cond}
- Severity: {prev_sev}

Analyze if their condition got better, worse, or stayed the same, and respond in 3-4 friendly sentences. Be encouraging, conversational, and direct. Plain text only."""
        
        _ai_t0 = time.perf_counter()
        response = await self._generate_text(
            system_prompt=ASSISTANT_SYSTEM_PROMPT,
            user_message=prompt,
            temperature=0.8,
            max_tokens=300,
            user_raw_message=user_message,
        )
        _ai_call_ms = (time.perf_counter() - _ai_t0) * 1000
        logger.info("[CHAT_TIMING] ai_call_ms=%.1f", _ai_call_ms)
        cleaned = self._clean_response(response) or response
        if self._is_incomplete(cleaned):
            cleaned = await self._try_complete_response(ASSISTANT_SYSTEM_PROMPT, prompt, cleaned)
        return cleaned or f"Looking at your history, your {curr_cond.lower()} looks about the same as last time. Make sure you're keeping up with brushing and flossing!"
    
    def _fallback_analysis_response(self, condition: str, severity: str) -> str:
        """Simple fallback for analysis if LLM fails."""
        if condition == "Healthy":
            return "Looking good! Your teeth appear healthy. Keep up with your regular brushing and flossing."
        elif "cavity" in condition.lower():
            return "I can see some signs that might indicate tooth decay. Worth having a dentist take a closer look."
        elif "plaque" in condition.lower():
            return "I notice some plaque buildup. Regular brushing and flossing should help with that."
        elif "gum" in condition.lower():
            return "Your gums look a bit inflamed. Try gentle brushing along the gum line and daily flossing."
        else:
            return "I had trouble getting a clear read on this image. Try taking another photo in better lighting."


# Global conversation engine instance
conversation_engine = ConversationEngine()
