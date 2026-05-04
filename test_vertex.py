"""Vertex AI connectivity smoke test — verifies auth, region, models."""
import os
import sys
import time

# Force vertex provider for this test
os.environ["LLM_PROVIDER"] = "vertex"

print("Loading modules...", flush=True)
from llm.factory import get_llm_client
import config.settings as _cfg

print(f"Project : {_cfg.GCP_PROJECT_ID}", flush=True)
print(f"Region  : {_cfg.GCP_REGION}", flush=True)
print(f"Gen     : {_cfg.VERTEX_GEN_MODEL}", flush=True)
print(f"Embed   : {_cfg.VERTEX_EMBED_MODEL} @ {_cfg.EMBED_DIM} dim", flush=True)
print(f"GCS Key : {_cfg.GCS_KEY_PATH}", flush=True)
print(f"Key exists: {os.path.exists(_cfg.GCS_KEY_PATH)}", flush=True)
print()

print("Creating client...", flush=True)
try:
    client = get_llm_client()
except Exception as e:
    print(f"  CLIENT INIT FAILED: {e}", flush=True)
    sys.exit(1)

print("\n[1/3] Embedding 'hello world'...", flush=True)
t0 = time.time()
v = client.embed("hello world")
if v is None:
    print("  EMBED FAILED — see error above", flush=True)
    sys.exit(1)
print(f"  OK: dim={len(v)}, first 4 vals={v[:4]}, took {time.time()-t0:.2f}s", flush=True)

print("\n[2/3] Generating with JSON mode...", flush=True)
t0 = time.time()
prompt = 'Return ONLY this JSON, nothing else: {"skills": ["Python", "SQL"]}'
resp = client.generate(prompt)
print(f"  Raw response: {resp!r}", flush=True)
print(f"  Took: {time.time()-t0:.2f}s", flush=True)

print("\n[3/3] Parsing as JSON...", flush=True)
import json
try:
    parsed = json.loads(resp)
    print(f"  OK: {parsed}", flush=True)
except json.JSONDecodeError as e:
    print(f"  JSON PARSE FAILED: {e}", flush=True)
    sys.exit(1)

print("\nAll Vertex smoke tests PASSED.", flush=True)
