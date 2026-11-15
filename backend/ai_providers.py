"""
AI provider abstraction layer.

Each provider implements a tiny common interface (`is_configured()` and
`call(prompt, timeout)`), so the orchestrator in ai_engine.py can try them
in priority order without knowing anything about each vendor's specific
API shape. Adding a new provider means adding one class here and
registering it in PROVIDERS — nothing else in the codebase changes.

Priority order (fixed): Gemini -> OpenRouter -> Groq -> rule-based.
AI_PROVIDER in .env picks which one is tried FIRST; if that one fails for
any reason (quota, auth, network, malformed response), the orchestrator
automatically falls through the remaining CONFIGURED providers in that
fixed order, and only reaches rule-based if every configured provider
fails. Every failure is logged with the exact provider name and reason —
never a silent fallback.
"""
import logging

import requests

from config import config

logger = logging.getLogger("scholarai.ai_providers")

DEFAULT_TIMEOUT = 15


class ProviderError(Exception):
    """Raised by a provider's call() on any failure. Always carries a
    human-readable reason so the orchestrator can log exactly what happened
    (e.g. 'HTTP 429 RESOURCE_EXHAUSTED: quota exceeded, limit: 0')."""
    def __init__(self, provider_name, reason):
        self.provider_name = provider_name
        self.reason = reason
        super().__init__(f"[{provider_name}] {reason}")


class BaseProvider:
    name = "base"

    def is_configured(self):
        raise NotImplementedError

    def call(self, prompt, timeout=DEFAULT_TIMEOUT):
        """Returns the model's text response, or raises ProviderError."""
        raise NotImplementedError


class GeminiProvider(BaseProvider):
    name = "gemini"
    ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def is_configured(self):
        return bool(config.GEMINI_API_KEY)

    def call(self, prompt, timeout=DEFAULT_TIMEOUT):
        url = self.ENDPOINT.format(model=config.GEMINI_MODEL)
        try:
            resp = requests.post(
                url,
                params={"key": config.GEMINI_API_KEY},
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=timeout,
            )
        except requests.RequestException as e:
            raise ProviderError(self.name, f"network error: {e}") from e

        if resp.status_code == 429:
            # Gemini's quota-exhausted response — surface the exact body
            # (e.g. "RESOURCE_EXHAUSTED ... quota exceeded, limit: 0")
            # rather than a generic "429" so the real reason is logged.
            raise ProviderError(self.name, f"HTTP 429 quota/rate-limit exceeded: {resp.text[:300]}")
        if not resp.ok:
            raise ProviderError(self.name, f"HTTP {resp.status_code}: {resp.text[:300]}")

        try:
            data = resp.json()
            candidates = data.get("candidates") or []
            if not candidates:
                raise ValueError("no candidates in response (possibly blocked by safety filters)")
            parts = candidates[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts).strip()
            if not text:
                raise ValueError("empty text in response")
            return text
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            raise ProviderError(self.name, f"response parsing failed: {e}") from e


class OpenRouterProvider(BaseProvider):
    """OpenRouter exposes an OpenAI-compatible chat completions API across
    many underlying models."""
    name = "openrouter"
    ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

    def is_configured(self):
        return bool(config.OPENROUTER_API_KEY)

    def call(self, prompt, timeout=DEFAULT_TIMEOUT):
        try:
            resp = requests.post(
                self.ENDPOINT,
                headers={
                    "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": config.OPENROUTER_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=timeout,
            )
        except requests.RequestException as e:
            raise ProviderError(self.name, f"network error: {e}") from e

        if resp.status_code == 429:
            raise ProviderError(self.name, f"HTTP 429 quota/rate-limit exceeded: {resp.text[:300]}")
        if not resp.ok:
            raise ProviderError(self.name, f"HTTP {resp.status_code}: {resp.text[:300]}")

        try:
            data = resp.json()
            text = data["choices"][0]["message"]["content"].strip()
            if not text:
                raise ValueError("empty text in response")
            return text
        except (ValueError, KeyError, TypeError, IndexError, AttributeError) as e:
            raise ProviderError(self.name, f"response parsing failed: {e}") from e


class GroqProvider(BaseProvider):
    """Groq also exposes an OpenAI-compatible chat completions API."""
    name = "groq"
    ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

    def is_configured(self):
        return bool(config.GROQ_API_KEY)

    def call(self, prompt, timeout=DEFAULT_TIMEOUT):
        try:
            resp = requests.post(
                self.ENDPOINT,
                headers={
                    "Authorization": f"Bearer {config.GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": config.GROQ_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=timeout,
            )
        except requests.RequestException as e:
            raise ProviderError(self.name, f"network error: {e}") from e

        if resp.status_code == 429:
            raise ProviderError(self.name, f"HTTP 429 quota/rate-limit exceeded: {resp.text[:300]}")
        if not resp.ok:
            raise ProviderError(self.name, f"HTTP {resp.status_code}: {resp.text[:300]}")

        try:
            data = resp.json()
            text = data["choices"][0]["message"]["content"].strip()
            if not text:
                raise ValueError("empty text in response")
            return text
        except (ValueError, KeyError, TypeError, IndexError, AttributeError) as e:
            raise ProviderError(self.name, f"response parsing failed: {e}") from e


# Fixed priority order — this is the order the orchestrator falls through
# after trying whatever AI_PROVIDER names as the first choice.
PRIORITY_ORDER = ["gemini", "openrouter", "groq"]

PROVIDERS = {
    "gemini": GeminiProvider(),
    "openrouter": OpenRouterProvider(),
    "groq": GroqProvider(),
}


VALID_AI_PROVIDER_VALUES = {"gemini", "openrouter", "groq", "auto", ""}


def ordered_providers():
    """Returns provider instances in the order they should be tried.
    AI_PROVIDER=<name> tries that provider first, then the rest of
    PRIORITY_ORDER. AI_PROVIDER=auto (or unset/blank) tries PRIORITY_ORDER
    as-is: Gemini -> OpenRouter -> Groq. An unrecognized value is treated
    the same as "auto", but logged as a warning so a typo doesn't silently
    change behavior unnoticed."""
    first = config.AI_PROVIDER
    if first and first not in VALID_AI_PROVIDER_VALUES:
        logger.warning(f"Unrecognized AI_PROVIDER value '{first}' — falling back to auto order "
                        f"({' -> '.join(PRIORITY_ORDER)}). Valid values: gemini, openrouter, groq, auto.")
        first = "auto"

    order = []
    if first and first != "auto" and first in PROVIDERS:
        order.append(first)
    for name in PRIORITY_ORDER:
        if name not in order:
            order.append(name)
    return [PROVIDERS[name] for name in order]


def any_provider_configured():
    return any(p.is_configured() for p in PROVIDERS.values())


def call_with_fallback(prompt, timeout=DEFAULT_TIMEOUT):
    """
    Tries each configured provider in order, logging the current provider
    being attempted, the exact reason for any failure, a notice when
    switching to the next provider, and the final provider used with its
    response time. Returns (text, provider_name) from the first provider
    that succeeds. Raises AllProvidersFailedError only if every configured
    provider failed (caller should catch this and use the rule-based
    engine) — this function itself never falls back to rule-based, that
    decision belongs to ai_engine.py.
    """
    import time

    order = ordered_providers()
    configured = [p for p in order if p.is_configured()]
    if not configured:
        raise AllProvidersFailedError([])

    logger.info(f"AI request: provider order = {[p.name for p in configured]}")
    attempted = []
    for idx, provider in enumerate(configured):
        attempted.append(provider.name)
        logger.info(f"Current provider: {provider.name}")
        t0 = time.time()
        try:
            text = provider.call(prompt, timeout=timeout)
            elapsed_ms = round((time.time() - t0) * 1000, 1)
            logger.info(f"Final provider used: {provider.name} (response time: {elapsed_ms}ms)")
            return text, provider.name
        except ProviderError as e:
            elapsed_ms = round((time.time() - t0) * 1000, 1)
            logger.warning(f"Provider '{provider.name}' failed after {elapsed_ms}ms — reason: {e.reason}")
            if idx + 1 < len(configured):
                logger.warning(f"Provider switched: {provider.name} -> {configured[idx + 1].name}")
            continue
        except Exception as e:
            elapsed_ms = round((time.time() - t0) * 1000, 1)
            # Defensive catch-all: a provider must never be able to crash
            # the request — log it as a failure and move on, same as a
            # normal ProviderError.
            logger.warning(f"Provider '{provider.name}' raised an unexpected error after {elapsed_ms}ms: {e}")
            if idx + 1 < len(configured):
                logger.warning(f"Provider switched: {provider.name} -> {configured[idx + 1].name}")
            continue

    raise AllProvidersFailedError(attempted)


class AllProvidersFailedError(Exception):
    def __init__(self, attempted_providers):
        self.attempted_providers = attempted_providers
        if attempted_providers:
            msg = f"All configured AI providers failed (tried: {', '.join(attempted_providers)})"
        else:
            msg = "No AI provider is configured"
        super().__init__(msg)
