"""OpenRouter API client for LLM responses."""

import logging
from typing import Optional
import httpx
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def _load_env_var(key: str, default: Optional[str] = None) -> Optional[str]:
    """Load environment variable, checking .env file if not in os.environ."""
    value = os.getenv(key)
    if value:
        return value
    
    # Try to load from .env file in repo root
    try:
        env_file = Path(__file__).parent.parent.parent.parent / ".env"
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        env_key, env_value = line.split('=', 1)
                        if env_key.strip() == key:
                            return env_value.strip()
    except Exception as e:
        logger.warning(f"Failed to load {key} from .env file: {e}")
    
    return default


class OpenRouterClient:
    """Simple OpenRouter API client using httpx."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 2
    ):
        self.api_key = api_key or _load_env_var("OPENROUTER_API_KEY")
        self.model = model or _load_env_var("OPENROUTER_MODEL", "deepseek/deepseek-chat-v3-0324:free")
        self.timeout = timeout
        self.max_retries = max_retries
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        
        if not self.api_key:
            logger.warning("OPENROUTER_API_KEY not set - LLM responses will fail")
        else:
            logger.info(f"OpenRouter client initialized with model={self.model}")
    
    async def generate_chat_response(
        self,
        system_prompt: str,
        user_message: str,
        conversation_context: Optional[list[dict]] = None,
        temperature: float = 0.7,
        max_tokens: int = 600
    ) -> str:
        """
        Generate chat response from OpenRouter.
        
        Args:
            system_prompt: System instructions for the model
            user_message: Current user message
            conversation_context: Optional list of previous messages [{"role": "user/assistant", "content": "..."}]
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum response length
            
        Returns:
            Generated response text
            
        Raises:
            RuntimeError: If API call fails after retries
        """
        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY not configured")
        
        # Build messages array
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add conversation context if provided
        if conversation_context:
            messages.extend(conversation_context)
        
        # Add current user message
        messages.append({"role": "user", "content": user_message})
        
        logger.info(f"[OPENROUTER] Generating response with model={self.model}, messages={len(messages)}")
        
        # Prepare request
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://dantshaant.local",
            "X-Title": "DaantShaant"
        }
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        # Retry logic
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        self.base_url,
                        headers=headers,
                        json=payload
                    )
                    
                    if response.status_code == 200:
                        try:
                            data = response.json()
                        except Exception as e:
                            logger.error(f"[OPENROUTER] Failed to parse JSON response: {e}")
                            last_error = RuntimeError(f"Malformed JSON response: {response.text}")
                            continue
                            
                        if not isinstance(data, dict):
                            logger.error(f"[OPENROUTER] Response is not a JSON object: {data}")
                            last_error = RuntimeError("Response is not a JSON object")
                            continue
                            
                        choices = data.get("choices")
                        if not choices or not isinstance(choices, list) or len(choices) == 0:
                            logger.error(f"[OPENROUTER] Empty or missing choices in response: {data}")
                            last_error = RuntimeError("Empty choices list from OpenRouter")
                            continue
                            
                        choice = choices[0]
                        if not isinstance(choice, dict):
                            logger.error(f"[OPENROUTER] Choice is not a dict: {choice}")
                            last_error = RuntimeError("Choice is not a dict")
                            continue
                            
                        message = choice.get("message")
                        if not message or not isinstance(message, dict):
                            logger.error(f"[OPENROUTER] Message missing or not a dict in choice: {choice}")
                            last_error = RuntimeError("Message missing in choice")
                            continue
                            
                        content = message.get("content")
                        if content is None:
                            logger.error(f"[OPENROUTER] Content is None in choices message: {message}")
                            last_error = RuntimeError("Null content from OpenRouter")
                            continue
                        
                        logger.info(f"[OPENROUTER] Response generated successfully ({len(content)} chars)")
                        return content.strip()
                    else:
                        error_msg = f"OpenRouter API error: {response.status_code} - {response.text}"
                        logger.error(f"[OPENROUTER] {error_msg}")
                        last_error = RuntimeError(error_msg)
                        
                        # Don't retry on client errors (4xx) except timeouts/rate limits
                        if 400 <= response.status_code < 500 and response.status_code not in (408, 429):
                            raise last_error
                        
            except httpx.TimeoutException as e:
                logger.warning(f"[OPENROUTER] Timeout on attempt {attempt + 1}/{self.max_retries + 1}")
                last_error = RuntimeError(f"OpenRouter API timeout: {e}")
                
            except httpx.RequestError as e:
                logger.warning(f"[OPENROUTER] Request error on attempt {attempt + 1}/{self.max_retries + 1}: {e}")
                last_error = RuntimeError(f"OpenRouter API request error: {e}")
            
            except Exception as e:
                logger.error(f"[OPENROUTER] Unexpected error: {e}", exc_info=True)
                last_error = RuntimeError(f"OpenRouter API error: {e}")
                break  # Don't retry on unexpected programming errors
        
        # All retries failed
        logger.error(f"[OPENROUTER] Failed after {self.max_retries + 1} attempts")
        raise last_error or RuntimeError("OpenRouter API failed")


# Global client instance
openrouter_client = OpenRouterClient()
