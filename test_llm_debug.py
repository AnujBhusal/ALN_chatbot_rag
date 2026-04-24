"""
Standalone LLM debug script.
Run: python test_llm_debug.py
"""
import os, sys, logging

# Force UTF-8 stdout so no encoding crashes on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("llm_debug")

try:
    from dotenv import load_dotenv
    load_dotenv()
    logger.info(".env loaded")
except ImportError:
    logger.warning("python-dotenv not installed, reading system env only")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
USE_GROQ     = os.getenv("USE_GROQ", "true")
REDIS_URL    = os.getenv("REDIS_URL", "")

print("\n" + "="*60)
print("ENVIRONMENT VARIABLES")
print("="*60)
print(f"  USE_GROQ     : {USE_GROQ}")
print(f"  GROQ_MODEL   : {GROQ_MODEL}")
print(f"  GROQ_API_KEY : {'SET (' + GROQ_API_KEY[:8] + '...)' if GROQ_API_KEY else '[NOT SET]'}")
redis_scheme = "rediss://" if REDIS_URL.startswith("rediss") else "redis://" if REDIS_URL.startswith("redis") else "[NOT SET]"
print(f"  REDIS_URL    : {redis_scheme}...")
print("="*60 + "\n")

# ── Test 1: Import groq ───────────────────────────────────────────────────────
print("TEST 1: Import groq package")
try:
    from groq import Groq
    print("  [PASS] groq package imported\n")
except ImportError as e:
    print(f"  [FAIL] groq not installed: {e}")
    print("  --> Fix: pip install groq\n")
    sys.exit(1)

# ── Test 2: Init client ───────────────────────────────────────────────────────
print("TEST 2: Initialize Groq client")
if not GROQ_API_KEY:
    print("  [FAIL] GROQ_API_KEY is empty\n")
    sys.exit(1)
try:
    client = Groq(api_key=GROQ_API_KEY)
    print("  [PASS] Groq client initialized\n")
except Exception as e:
    print(f"  [FAIL] {type(e).__name__}: {e}\n")
    sys.exit(1)

# ── Test 3: List models ───────────────────────────────────────────────────────
print("TEST 3: List available Groq models")
try:
    models = client.models.list()
    model_ids = sorted([m.id for m in models.data])
    print(f"  [PASS] {len(model_ids)} models available:")
    for m in model_ids:
        tag = "  <-- CONFIGURED" if m == GROQ_MODEL else ""
        print(f"      - {m}{tag}")
    if GROQ_MODEL not in model_ids:
        print(f"\n  [FAIL] GROQ_MODEL='{GROQ_MODEL}' is NOT in the list above!")
        print("  --> Update GROQ_MODEL in Render env vars to one listed above.\n")
    else:
        print(f"\n  [PASS] GROQ_MODEL='{GROQ_MODEL}' is valid\n")
except Exception as e:
    print(f"  [WARN] Could not list models: {type(e).__name__}: {e}\n")

# ── Test 4: Chat completion ───────────────────────────────────────────────────
TEST_QUERY = "Tell me about Kathmandu city in 2-3 sentences."
print(f"TEST 4: Chat completion")
print(f"  Model : {GROQ_MODEL}")
print(f"  Query : {TEST_QUERY}")
try:
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": TEST_QUERY}],
        temperature=0.3,
        max_tokens=256,
    )
    answer = response.choices[0].message.content if response.choices else None
    if answer:
        print(f"\n  [PASS] Got response ({len(answer)} chars):")
        print("  " + "-"*50)
        print(f"  {answer.strip()}")
        print("  " + "-"*50 + "\n")
    else:
        print("  [FAIL] Response was empty\n")
except Exception as e:
    print(f"\n  [FAIL] {type(e).__name__}: {e}\n")

# ── Test 5: Redis ─────────────────────────────────────────────────────────────
print("TEST 5: Redis connection")
if not REDIS_URL:
    print("  [SKIP] REDIS_URL not set\n")
else:
    try:
        import redis as redis_lib
        is_ssl = REDIS_URL.startswith("rediss://")
        extra = {"ssl_cert_reqs": "none"} if is_ssl else {}
        r = redis_lib.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=5, **extra)
        r.ping()
        print("  [PASS] Redis connected and PING successful\n")
    except Exception as e:
        print(f"  [FAIL] {type(e).__name__}: {e}")
        if not REDIS_URL.startswith("rediss://"):
            print("  --> HINT: Change REDIS_URL from redis:// to rediss://")
        print()

print("="*60)
print("DONE")
print("="*60)
