"""
Analyze job posting patterns for 5 target roles.
Query database for sample jobs per role, send to Gemini for pattern analysis.
"""
import json
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from loguru import logger

from llm.factory import get_llm_client

logger.remove()
logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}")

# Database connection
DATABASE_URL = "postgresql+psycopg2://postgres:JobScraperDB2025!@34.44.83.223:5432/Linked_job_scrapping"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

ROLE_PATTERNS = {
    "Data Engineer": ["data engineer", "data eng"],
    "ML Engineer": ["machine learning", "ml engineer", "ml eng"],
    "AI Engineer": ["ai engineer", "artificial intelligence engineer"],
    "MLOps": ["mlops", "ml ops", "machine learning ops"],
    "Software Engineer": ["software engineer", "backend engineer", "senior engineer"],
}

SAMPLE_SIZE = 5  # Get 5 jobs per role


def fetch_jobs_for_role(session, role_name: str, patterns: list, sample_size: int = 5):
    """Fetch sample jobs matching role patterns."""
    conditions = " OR ".join([f"title ILIKE '%{p}%'" for p in patterns])
    query = text(f"""
        SELECT id, title, company_name, description
        FROM jobsql
        WHERE ({conditions}) AND description IS NOT NULL
        LIMIT :limit
    """)
    result = session.execute(query, {"limit": sample_size}).fetchall()
    return result


def analyze_role_with_gemini(role_name: str, job_descriptions: list, client) -> dict:
    """Send sample job descriptions to Gemini for pattern analysis."""
    if not job_descriptions:
        logger.warning(f"No jobs found for {role_name}")
        return None

    # Combine job descriptions for analysis
    descriptions_text = "\n\n---\n\n".join([
        f"Title: {title}\nCompany: {company}\n\nDescription:\n{desc[:1000]}"
        for _, title, company, desc in job_descriptions
    ])

    prompt = f"""Analyze these {len(job_descriptions)} job postings for "{role_name}" roles.
Extract the TOP 20 keywords/skills/patterns that companies value most for this role.

Focus on:
1. Technical skills (languages, frameworks, tools)
2. Domain concepts (e.g., "real-time systems", "data pipelines", "distributed computing")
3. Action verbs (e.g., "design", "optimize", "scale")
4. Experience patterns

Return ONLY a JSON object:
{{
  "role": "{role_name}",
  "key_keywords": ["keyword1", "keyword2", "..."],
  "key_skills": ["skill1", "skill2", "..."],
  "key_concepts": ["concept1", "concept2", "..."],
  "action_verbs": ["verb1", "verb2", "..."],
  "experience_emphasis": "What years of experience companies want",
  "ideal_profile": "1-2 sentence description of ideal candidate"
}}

JOB DESCRIPTIONS:
{descriptions_text}
"""

    try:
        raw = client.generate(prompt)
        data = json.loads(raw)
        logger.info(f"✓ Analyzed {role_name}: {len(data.get('key_keywords', []))} keywords extracted")
        return data
    except Exception as e:
        logger.error(f"Failed to analyze {role_name}: {e}")
        return None


def main():
    logger.info("Connecting to database...")
    session = SessionLocal()

    logger.info("Initializing LLM client...")
    client = get_llm_client()
    if not client.is_available():
        logger.error("LLM client not available")
        session.close()
        return

    logger.info(f"Fetching sample jobs for {len(ROLE_PATTERNS)} roles...")

    analysis_results = {}

    for role_name, patterns in ROLE_PATTERNS.items():
        logger.info(f"\n{'='*60}")
        logger.info(f"Analyzing: {role_name}")
        logger.info(f"{'='*60}")

        # Fetch jobs
        jobs = fetch_jobs_for_role(session, role_name, patterns, SAMPLE_SIZE)
        if not jobs:
            logger.warning(f"  No jobs found for {role_name}")
            continue

        logger.info(f"  Found {len(jobs)} sample jobs")
        for job_id, title, company, _ in jobs:
            logger.info(f"    - {title} @ {company}")

        # Analyze with Gemini
        analysis = analyze_role_with_gemini(role_name, jobs, client)
        if analysis:
            analysis_results[role_name] = analysis

    session.close()

    # Save results
    output_path = "scripts/role_patterns_analysis.json"
    with open(output_path, "w") as f:
        json.dump(analysis_results, f, indent=2)

    logger.info(f"\n{'='*60}")
    logger.info(f"Analysis saved to {output_path}")
    logger.info(f"{'='*60}")

    # Print summary
    logger.info("\n=== SUMMARY ===")
    for role, analysis in analysis_results.items():
        logger.info(f"\n{role}:")
        logger.info(f"  Keywords: {', '.join(analysis.get('key_keywords', [])[:5])}")
        logger.info(f"  Skills: {', '.join(analysis.get('key_skills', [])[:5])}")
        logger.info(f"  Experience: {analysis.get('experience_emphasis', 'N/A')}")


if __name__ == "__main__":
    main()
