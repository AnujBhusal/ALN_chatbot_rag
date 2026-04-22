
from typing import List, Dict, Tuple
import os
import requests
import logging
import time
import re

# Set up logger first
logger = logging.getLogger(__name__)

try:
    import cohere
    COHERE_AVAILABLE = True
except ImportError:
    COHERE_AVAILABLE = False
    logger.warning("Cohere library not installed. Install with: pip install cohere")

# Cohere API configuration
COHERE_API_KEY = os.getenv("COHERE_API_KEY")
USE_COHERE = os.getenv("USE_COHERE", "false").lower() == "true"

# HuggingFace fallback configuration
HF_API_KEY = os.getenv("HF_API_KEY")

class LLMService:
    """Handles LLM prompts and responses with Cohere and HuggingFace fallback."""

    def __init__(self):
        if USE_COHERE and COHERE_API_KEY and COHERE_AVAILABLE:
            # Initialize Cohere client with current working models
            self.cohere_client = cohere.Client(api_key=COHERE_API_KEY)
            self.cohere_headers = {
                "Authorization": f"Bearer {COHERE_API_KEY}",
                "Content-Type": "application/json"
            }
            self.use_cohere = True
            logger.info(f"LLM Service initialized with Cohere API client")
        else:
            self.use_cohere = False
            
        # Always initialize HF headers for fallback
        if HF_API_KEY:
            self.hf_headers = {"Authorization": f"Bearer {HF_API_KEY}"}
            logger.info(f"LLM Service initialized with HuggingFace API fallback")
        else:
            self.hf_headers = None
            logger.warning("No API keys available, using fallback responses only")

    def build_prompt(
        self,
        query: str,
        context: str,
        history: List[Dict[str, str]],
        system_instruction: str | None = None,
    ) -> str:
        """Combine query, context, and history into a single prompt."""
        context = self._clean_text(context)

        # Keep history short for better results
        recent_history = history[-3:] if len(history) > 3 else history
        history_text = "\n".join([f"{h['role']}: {h['message']}" for h in recent_history])
        
        instruction_block = system_instruction or "You are a helpful assistant. Use the provided context to answer the question accurately."

        prompt = f"""{instruction_block}

Context: {context[:1500]}

Chat History:
{history_text}

Question: {query}
Answer:"""
        return prompt

    def call_llm(self, prompt: str) -> str:
        """Call LLM API with Cohere priority and HuggingFace fallback."""
        if self.use_cohere:
            response = self._call_cohere_api(prompt)
            if response:
                return response
        
        # Try HuggingFace fallback
        if HF_API_KEY and self.hf_headers:
            response = self._call_huggingface_api(prompt)
            if response:
                return response
        
        # Use enhanced fallback
        return self._enhanced_fallback_response(prompt)

    def _extract_prompt_parts(self, prompt: str) -> Tuple[str, str]:
        """Extract context and question segments from the formatted prompt."""
        context = ""
        question = ""

        context_match = re.search(r"Context:\s*(.*?)\s*Chat History:", prompt, flags=re.DOTALL)
        question_match = re.search(r"Question:\s*(.*?)\s*Answer:\s*$", prompt, flags=re.DOTALL)

        if context_match:
            context = context_match.group(1).strip()
        if question_match:
            question = question_match.group(1).strip()

        return context, question

    def _clean_text(self, text: str) -> str:
        """Normalize whitespace-heavy OCR/PDF text into readable prose."""
        try:
            repaired = text.encode("latin-1", errors="ignore").decode("utf-8", errors="replace")
            if repaired and repaired.count("â") < text.count("â"):
                text = repaired
        except Exception:
            pass

        replacements = {
            "â€™": "'",
            "â€œ": '"',
            "â€\x9d": '"',
            "â€“": "-",
            "â€”": "-",
            "â€": '"',
            "â": "",
        }
        for bad, good in replacements.items():
            text = text.replace(bad, good)

        # Fix remaining patterns like Nepalâs -> Nepal's.
        text = re.sub(r"â([A-Za-z])", r"'\1", text)
        text = re.sub(r"\sâ\s", " - ", text)

        # Collapse spaced-out line breaks common in extracted PDFs.
        text = re.sub(r"\n\s*\n+", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _extractive_summary(self, text: str, question: str, max_sentences: int = 4, max_chars: int = 650) -> str:
        """Create a small extractive summary from context when APIs are unavailable."""
        clean = self._clean_text(text)
        if not clean:
            return "I could not find enough document context to summarize."

        sentences = re.split(r"(?<=[.!?])\s+", clean)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 30]

        if not sentences:
            return clean[:450] + ("..." if len(clean) > 450 else "")

        question_tokens = set(re.findall(r"[a-zA-Z]{3,}", question.lower()))
        stop = {
            "about", "this", "that", "from", "with", "what", "when", "where", "which",
            "have", "has", "were", "they", "them", "their", "into", "than", "then",
        }
        question_tokens = {t for t in question_tokens if t not in stop}

        scored = []
        for i, sentence in enumerate(sentences):
            tokens = set(re.findall(r"[a-zA-Z]{3,}", sentence.lower()))
            overlap = len(tokens & question_tokens)
            # Prefer earlier sentences for "what is this document about" style questions.
            position_bonus = max(0, 3 - i)
            score = overlap * 3 + position_bonus
            scored.append((score, i, sentence))

        # Keep chronological flow by sorting selected sentences by original index.
        top = sorted(sorted(scored, key=lambda x: x[0], reverse=True)[:max_sentences], key=lambda x: x[1])
        summary = " ".join([s for _, _, s in top]).strip()

        if len(summary) < 80:
            summary = clean[:500] + ("..." if len(clean) > 500 else "")

        if len(summary) > max_chars:
            summary = summary[:max_chars].rsplit(" ", 1)[0].strip() + "..."

        return summary

    def _call_cohere_api(self, prompt: str) -> str:
        """Call Cohere API with current available models."""
        try:
            # Current working models (as of Sept 2025)
            models_to_try = [
                "command-nightly",          # Fast and working
                "command-a-03-2025",        # Latest flagship
                "command-r7b-12-2024",      # Reliable option
                "c4ai-aya-expanse-8b",      # Open source option
                "command-r-08-2024",        # Stable release
            ]
            
            for model_name in models_to_try:
                try:
                    response = self._cohere_chat_api(prompt, model_name)
                    if response and len(response.strip()) > 10:
                        logger.info(f"Successfully generated response using Cohere {model_name}")
                        return response.strip()
                        
                except Exception as model_error:
                    logger.warning(f"Error with Cohere {model_name}: {model_error}")
                    continue
            
            return None
            
        except Exception as e:
            logger.error(f"Error calling Cohere API: {e}")
            return None

    def _cohere_chat_api(self, prompt: str, model: str) -> str:
        """Call Cohere's Chat API using the official client."""
        try:
            response = self.cohere_client.chat(
                message=prompt,
                model=model,
                temperature=0.7,
                max_tokens=300
            )
            
            return response.text.strip() if response.text else None
            
        except Exception as e:
            # Check if it's a rate limit error
            if "rate limit" in str(e).lower() or "429" in str(e):
                logger.warning(f"Cohere rate limit hit with {model}")
                time.sleep(2)
                return None
            else:
                logger.warning(f"Error with Cohere {model}: {e}")
                return None

    def _cohere_generate_api(self, prompt: str, model: str) -> str:
        """Generate API was removed September 15, 2025. Use chat API instead."""
        logger.warning("Generate API is deprecated, using chat API instead")
        return self._cohere_chat_api(prompt, model)

    def _call_huggingface_api(self, prompt: str) -> str:
        """Call HuggingFace API as fallback."""
        if not self.hf_headers:
            return None
            
        try:
            models_to_try = [
                "microsoft/DialoGPT-medium",
                "facebook/blenderbot-400M-distill",
                "google/flan-t5-base"
            ]
            
            for model_name in models_to_try:
                try:
                    model_url = f"https://api-inference.huggingface.co/models/{model_name}"
                    payload = {"inputs": prompt[-500:]}
                    
                    response = requests.post(
                        model_url,
                        headers=self.hf_headers,
                        json=payload,
                        timeout=20
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        if isinstance(result, list) and len(result) > 0:
                            generated_text = result[0].get("generated_text", "")
                            if len(generated_text.strip()) > 10:
                                logger.info(f"Successfully generated response using HuggingFace {model_name}")
                                return generated_text.replace(prompt[-500:], "").strip()
                    
                except Exception as model_error:
                    logger.warning(f"Error with HuggingFace {model_name}: {model_error}")
                    continue
                    
            return None
            
        except Exception as e:
            logger.error(f"Error calling HuggingFace API: {e}")
            return None

    def _fallback_response(self, prompt: str) -> str:
        """Provide a concise fallback response when model APIs are unavailable."""
        context, question = self._extract_prompt_parts(prompt)
        clean_context = self._clean_text(context)

        if clean_context and len(clean_context) > 40:
            summary = self._extractive_summary(clean_context, question)
            return f"Here is a summary based on the uploaded document: {summary}"

        if "booking" in prompt.lower():
            return "I can help you with booking appointments. Please provide your name, email, date, and time."

        return "I could not find enough document context to answer that clearly right now."

    def _enhanced_fallback_response(self, prompt: str) -> str:
        """Generate a higher quality fallback response from retrieved context."""
        try:
            context, question = self._extract_prompt_parts(prompt)
            clean_context = self._clean_text(context)

            if clean_context and len(clean_context) > 40:
                summary = self._extractive_summary(clean_context, question)

                if any(term in question.lower() for term in ["what is this pdf about", "what is this document about", "summary", "summarize"]):
                    return f"This document is about: {summary}"

                return f"Based on the retrieved document context: {summary}"

            return "I could not find enough matching document context to answer that. Please try a more specific question."

        except Exception as e:
            logger.error(f"Error in enhanced fallback: {e}")
            return self._fallback_response(prompt)
