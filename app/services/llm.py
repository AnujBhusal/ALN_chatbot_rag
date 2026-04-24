
from typing import Dict, List, Optional, Tuple
import logging
import os
import re

import requests

logger = logging.getLogger(__name__)

try:
    from groq import Groq
except ImportError:
    Groq = None


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name, str(default)).strip().lower()
    return value in {"1", "true", "yes", "on"}

class LLMService:
    """Handles LLM calls with Groq/Ollama/HuggingFace and fallback summarization."""

    def __init__(self):
        self.use_groq = _env_flag("USE_GROQ", default=True)
        self.use_ollama = _env_flag("USE_OLLAMA", default=False)
        self.use_hf = _env_flag("USE_HF", default=False)

        self.groq_api_key = os.getenv("GROQ_API_KEY", "")
        self.groq_model = os.getenv("GROQ_MODEL") or "llama3-8b-8192"

        self.ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
        self.ollama_model = os.getenv("OLLAMA_MODEL") or os.getenv("LLM_MODEL") or "mistral"

        self.hf_api_key = os.getenv("HF_API_KEY", "")

        self.groq_client = None
        
        # Detailed logging for Groq initialization
        logger.info(f"Groq init: use_groq={self.use_groq}, groq_api_key_present={bool(self.groq_api_key)}, Groq_class={Groq is not None}")
        
        if self.use_groq and self.groq_api_key and Groq is not None:
            try:
                self.groq_client = Groq(api_key=self.groq_api_key)
                logger.info(f"✅ LLM Service initialized with Groq provider (model={self.groq_model})")
            except Exception as e:
                logger.error(f"❌ Failed to initialize Groq client: {e}")
        elif self.use_groq and not self.groq_api_key:
            logger.warning("❌ Groq provider enabled but GROQ_API_KEY is missing")
        elif self.use_groq and Groq is None:
            logger.warning("❌ Groq provider enabled but groq package is missing")

        self.hf_headers = None
        if self.use_hf and self.hf_api_key:
            self.hf_headers = {"Authorization": f"Bearer {self.hf_api_key}"}
            logger.info("LLM Service initialized with HuggingFace provider")

        if not any([self.groq_client, self.use_ollama, self.hf_headers]):
            logger.warning("⚠️  No LLM providers configured. Falling back to extractive responses.")

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

Context: {context[:4000]}

Chat History:
{history_text}

Question: {query}
Answer:"""
        return prompt

    def call_llm(self, prompt: str) -> str:
        """Call configured LLM providers in priority order and return best response."""
        if self.groq_client:
            logger.debug("Attempting Groq API call...")
            response = self._call_groq_api(prompt)
            if response:
                logger.info("✅ Got response from Groq")
                return response
            logger.warning("⚠️  Groq returned None, trying next provider")

        if self.use_ollama:
            logger.debug("Attempting Ollama API call...")
            response = self._call_ollama_api(prompt)
            if response:
                logger.info("✅ Got response from Ollama")
                return response

        if self.hf_headers:
            logger.debug("Attempting HuggingFace API call...")
            response = self._call_huggingface_api(prompt)
            if response:
                logger.info("✅ Got response from HuggingFace")
                return response

        logger.warning("⚠️  All LLM providers failed, using fallback")
        return self._enhanced_fallback_response(prompt)

    def answer_general_question(self, query: str, history: Optional[List[Dict[str, str]]] = None) -> str:
        """Answer open-domain questions without requiring document context."""
        history = history or []
        instruction = (
            "You are a concise, factual assistant. "
            "Answer general knowledge questions directly in 1-3 sentences. "
            "If uncertain, say you are not fully sure."
        )
        prompt = self.build_prompt(query, "", history, system_instruction=instruction)
        answer = self.call_llm(prompt)

        # If document-context fallback leaked into general mode, replace with a generic assistant fallback.
        lower = answer.lower()
        if "could not find enough" in lower or "document context" in lower or "aln documents" in lower:
            return self._general_knowledge_fallback(query)

        return answer

    def _general_knowledge_fallback(self, query: str) -> str:
        """Provide rule-based answers for common questions when LLM is unavailable."""
        normalized = query.lower().strip().rstrip("?")

        if any(greet in normalized for greet in ["hello", "hi", "hey"]):
            return "Hello! Ask me a general question or an ALN document question."

        # Built-in knowledge base for common questions
        knowledge_base = {
            "shahrukh khan": "Shah Rukh Khan is an Indian actor, film producer, and television personality. He is widely regarded as one of the biggest Bollywood stars and has appeared in numerous hit films spanning multiple decades.",
            "narendra modi": "Narendra Modi is the Prime Minister of India since 2014. He is a prominent political figure who leads the Bharatiya Janata Party (BJP) and is known for his development-focused governance model.",
            "lamine yamal": "Lamine Yamal is a Spanish professional footballer who plays as a winger for FC Barcelona and the Spain national team. He is widely regarded as one of football's top young talents.",
            "prime minister of nepal": "As of 2026, K. P. Sharma Oli is the Prime Minister of Nepal. Nepal has a complex parliamentary system with frequent government changes.",
            "warren buffett": "Warren Buffett is an American investor and philanthropist who is the chairman of Berkshire Hathaway. He is one of the world's most successful investors and richest people.",
            "elon musk": "Elon Musk is a South African-born entrepreneur known for founding Tesla, SpaceX, and co-founding Neuralink. He is known for ambitious projects in electric vehicles, space, and neural interfaces.",
            "virat kohli": "Virat Kohli is an Indian cricketer and former captain of the Indian national cricket team. He is widely considered one of the greatest batsmen in cricket history.",
        }
        
        # Check for matches
        for key, answer in knowledge_base.items():
            if key in normalized:
                return answer

        if normalized.startswith("who is ") or normalized.startswith("what is "):
            return "I can help with general questions and ALN document-based questions. Feel free to ask!"

        return "I can help with general questions and ALN document-based questions."

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

    def _strip_structured_context_markers(self, text: str) -> str:
        """Remove bracketed metadata headers used in retrieval context blocks."""
        text = re.sub(r"\[(?:Title|Type|Year|Document):[^\]]*\]", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"\s{2,}", " ", text)
        return text.strip()

    def _extractive_summary(self, text: str, question: str, max_sentences: int = 4, max_chars: int = 650) -> str:
        """Create a small extractive summary from context when APIs are unavailable."""
        clean = self._clean_text(text)
        clean = self._strip_structured_context_markers(clean)
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

    def _call_groq_api(self, prompt: str) -> Optional[str]:
        """Call Groq chat completion API."""
        if not self.groq_client:
            logger.error("❌ Groq client is not initialized")
            return None

        try:
            logger.debug(f"Calling Groq API with model={self.groq_model}, prompt_len={len(prompt)}")
            response = self.groq_client.chat.completions.create(
                model=self.groq_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=1024,
            )
            message = response.choices[0].message.content if response.choices else None
            if message and len(message.strip()) > 10:
                logger.debug(f"✅ Groq returned {len(message)} chars")
                return message.strip()
            else:
                logger.warning(f"⚠️  Groq returned short/empty response: {message}")
        except Exception as e:
            logger.error(f"❌ Groq call failed for model {self.groq_model}: {type(e).__name__}: {e}")
        return None

    def _call_ollama_api(self, prompt: str) -> Optional[str]:
        """Call local or remote Ollama server for completion."""
        try:
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.3},
                },
                timeout=30,
            )
            if response.status_code != 200:
                logger.warning(f"Ollama API error: {response.status_code} - {response.text}")
                return None

            result = response.json()
            output = (result.get("response") or "").strip()
            if len(output) > 10:
                return output
        except Exception as e:
            logger.warning(f"Ollama call failed for model {self.ollama_model}: {e}")
        return None

    def _call_huggingface_api(self, prompt: str) -> Optional[str]:
        """Call HuggingFace API as fallback."""
        if not self.hf_headers:
            return None
            
        try:
            models_to_try = [
                os.getenv("LLM_MODEL", "google/flan-t5-base"),
                "google/flan-t5-base",
                "mistralai/Mistral-7B-Instruct-v0.2",
            ]
            
            for model_name in models_to_try:
                try:
                    model_url = f"https://api-inference.huggingface.co/models/{model_name}"
                    payload = {"inputs": prompt[-600:]}
                    
                    response = requests.post(
                        model_url,
                        headers=self.hf_headers,
                        json=payload,
                        timeout=20
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        if isinstance(result, list) and len(result) > 0:
                            generated_text = result[0].get("generated_text", "").strip()
                            if len(generated_text) > 10:
                                logger.info(f"Successfully generated response using HuggingFace {model_name}")
                                return generated_text.replace(prompt[-600:], "").strip() or generated_text
                    
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
            clean_context = self._strip_structured_context_markers(clean_context)

            if clean_context and len(clean_context) > 40:
                summary = self._extractive_summary(clean_context, question)

                if any(term in question.lower() for term in ["what is this pdf about", "what is this document about", "summary", "summarize"]):
                    return f"Document summary: {summary}"

                return f"From the referenced documents: {summary}"

            return "I could not find enough matching document context to answer that. Please try a more specific question."

        except Exception as e:
            logger.error(f"Error in enhanced fallback: {e}")
            return self._fallback_response(prompt)
