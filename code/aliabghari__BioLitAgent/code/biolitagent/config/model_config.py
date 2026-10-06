"""
config/model_config.py
----------------------
Single source of truth for the default Gemini model used across all BioLitAgent agents
(literature_scout.py, regulatory_watch.py, etc.).

Rationale for 'gemini-2.5-flash':
1. 'gemini-2.0-flash' has been retired and returns HTTP 404 from the Gemini API.
2. 'gemini-3.8-flash' carries an extremely low free-tier quota (20 requests/day per project),
   causing rapid 429 RESOURCE_EXHAUSTED errors.
3. 'gemini-2.5-flash' provides stable free-tier quotas, supports structured JSON schema
   output, and reliably delivers accurate paraphrases and regulatory extractions.
"""

DEFAULT_MODEL: str = "gemini-2.5-flash"
