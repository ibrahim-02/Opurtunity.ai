"""Quick skill extractor test on 5 random embedded jobs."""
import time

print("Loading modules...", flush=True)
from database.connection import SessionLocal
from sqlalchemy import text
from llm.ollama_client import OllamaClient
from llm.skill_extractor import SkillExtractor
from llm.section_parser import _strip_html
from storage.gcs_client import GCSClient

print("Connecting to DB and Ollama...", flush=True)
session = SessionLocal()
gcs = GCSClient()
client = OllamaClient()
extractor = SkillExtractor(client)

if not client.is_available():
    print("ERROR: Ollama is not running. Start it with: ollama serve", flush=True)
    raise SystemExit(1)

print("Fetching 5 random jobs from DB...", flush=True)
rows = session.execute(text("""
    SELECT id, title, company_name, description FROM jobsql
    WHERE embedding IS NOT NULL
    ORDER BY RANDOM()
    LIMIT 5
""")).fetchall()
print(f"Got {len(rows)} jobs. Starting extraction...\n", flush=True)

for i, row in enumerate(rows, 1):
    print(f"[{i}/{len(rows)}] Calling LLM for job {row.id}: {row.title[:60]}...", flush=True)
    t0 = time.time()
    desc = row.description
    content = gcs.download_description(desc) if desc and desc.startswith("gs://") else desc
    if not content:
        print(f"  → SKIPPED (no content)\n", flush=True)
        continue
    plain = _strip_html(content)
    result = extractor.extract(plain, company_name=row.company_name)
    elapsed = time.time() - t0
    if result is None:
        print(f"  → FAILED ({elapsed:.1f}s)\n", flush=True)
    else:
        skills = result["required_skills"]
        years = result["experience_years"]
        print(f"  → {len(skills)} skills, experience_years={years} ({elapsed:.1f}s)", flush=True)
        print(f"    skills: {skills}\n", flush=True)

session.close()
client.close()
print("Done.", flush=True)
