"""
Vertex AI smoke test on real jobs.
Same 5 problem jobs we tested with llama3.2 so we can compare.
"""
import os
os.environ["LLM_PROVIDER"] = "vertex"

import time

print("Loading modules...", flush=True)
from database.connection import SessionLocal
from sqlalchemy import text
from llm.factory import get_llm_client
from llm.skill_extractor import SkillExtractor
from llm.section_parser import _strip_html
from storage.gcs_client import GCSClient
import config.settings as _cfg

session = SessionLocal()
gcs = GCSClient()
client = get_llm_client()
extractor = SkillExtractor(client)

# 5 random LinkedIn jobs with descriptions
rows = session.execute(text("""
    SELECT id, title, company_name, description FROM jobsql
    WHERE source = 'linkedin'
      AND description IS NOT NULL
    ORDER BY RANDOM()
    LIMIT 5
""")).fetchall()

print(f"\nTesting {len(rows)} jobs through Vertex AI ({_cfg.VERTEX_GEN_MODEL})...\n", flush=True)

total_time = 0.0
for i, row in enumerate(rows, 1):
    desc = row.description
    content = gcs.download_description(desc) if desc and desc.startswith("gs://") else desc
    if not content:
        print(f"[{i}/{len(rows)}] {row.title[:55]} ... SKIPPED (no content)\n", flush=True)
        continue
    plain = _strip_html(content)

    print(f"[{i}/{len(rows)}] {row.title[:60]} @ {row.company_name}", flush=True)
    t0 = time.time()
    result = extractor.extract(plain, company_name=row.company_name)
    elapsed = time.time() - t0
    total_time += elapsed
    if result is None:
        print(f"  -> FAILED ({elapsed:.1f}s)\n", flush=True)
    else:
        skills = result["required_skills"]
        years = result["experience_years"]
        print(f"  -> {len(skills)} skills, experience_years={years} ({elapsed:.1f}s)", flush=True)
        print(f"     skills: {skills}\n", flush=True)

# Embed test on 1 job
print(f"Embedding test on job {rows[0].id} (gemini-embedding-001 @ {_cfg.EMBED_DIM} dim)...", flush=True)
row = rows[0]
desc = row.description
content = gcs.download_description(desc) if desc and desc.startswith("gs://") else desc
plain = _strip_html(content)
t0 = time.time()
v = client.embed(plain[:4000])
print(f"  -> dim={len(v) if v else 'FAILED'}, took {time.time()-t0:.2f}s", flush=True)

print(f"\nTotal LLM wall-time: {total_time:.1f}s for {len(rows)} jobs", flush=True)
print(f"Estimated cost: ~${0.001 * len(rows):.4f} (extraction) + ~${0.00002:.5f} (1 embed)", flush=True)

session.close()
client.close()
