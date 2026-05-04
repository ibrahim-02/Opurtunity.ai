SKILL_EXTRACTION_PROMPT = """Extract two things from the job description below:
  1. required_skills — technical skills, tools, programming languages, frameworks, platforms, libraries, databases, cloud services, methodologies, and compliance/regulatory frameworks that are EXPLICITLY named.
  2. experience_years — the minimum number of years of relevant experience required (single integer), or null if not stated.

STRICT RULES — read all before answering:

1. required_skills: only output items that appear word-for-word in the text. Do NOT infer skills that "would be needed" for this role.
2. Output the COMPLETE term — never truncate. "Global Illumination" stays as "Global Illumination", not "Global Illu". "Generative AI" stays as "Generative AI".
3. Output the canonical short form: "Microsoft Power BI" -> "Power BI"; "Amazon Web Services" -> "AWS"; "Google Cloud Platform" -> "GCP"; "Microsoft SQL Server" -> "SQL Server"; "Node.js" -> "Node.js".
4. NEVER output any of these as a skill:
   - Company names (e.g. "Roblox", "Carvana", "Datadog") — even if mentioned in the JD
   - Team names or product names internal to the company
   - Generic field labels: "AI", "ML", "Engineering", "Software Engineering", "Computer Science", "Programming", "Development", "Technology", "Information Technology"
   - Degree fields: "Computer Science", "Mathematics", "Statistics"
   - Soft skills: "communication", "leadership", "teamwork", "problem solving"
   - Buzz phrases: "data-driven", "fast-paced", "cross-functional"
   - Years of experience or seniority levels (those go in experience_years instead)
5. Specific tools and named compliance regimes (SOC 2, GDPR, HIPAA, PCI-DSS, ISO 27001) ARE valid. "Machine Learning" alone is NOT a skill — but "scikit-learn", "PyTorch", "TensorFlow", "XGBoost", "LangChain", "LlamaIndex", "Hugging Face" ARE.
6. experience_years rules — extract the MINIMUM numeric years whenever a number appears near the word "year/years", regardless of what field/domain it qualifies:
   - "5+ years" or "5 or more years"             -> 5
   - "3 to 5 years" or "3-5 years"               -> 3 (always take the lower bound)
   - "minimum 2 years"                           -> 2
   - "3+ years of experience in Sales Ops"       -> 3  (domain qualifier doesn't matter)
   - "7-10 years of experience in the field"     -> 7
   - "at least 4 years of relevant experience"   -> 4
   - "10 years experience with..."               -> 10
   - Multiple top-level mentions -> take the smallest (the minimum required)
   - "8+ years..., including 2+ years in X"      -> 8  (2 is a sub-requirement; always take the overall)
   - Bullet-list style ("13+ years total • 6+ years leadership • 3+ years Kubernetes") -> 13 (the first/overall requirement)
   - "Senior" / "Junior" / "Lead" alone, no number -> null
   - No number anywhere near "year/years"        -> null
7. Do NOT pad. If only 2 skills are named, return only those 2. If none, return [].
8. Return ONLY the JSON object — no markdown fences, no commentary.

Output format (always include both keys):
{{"required_skills": ["<skill 1>", "<skill 2>", ...], "experience_years": <integer or null>}}

Examples of CORRECT extraction:

Description: "5+ years in Go and Postgres, ETL pipelines on Kubernetes."
Output: {{"required_skills": ["Go", "PostgreSQL", "ETL", "Kubernetes"], "experience_years": 5}}

Description: "Build dashboards in Tableau and analyse data with SQL. Bachelor's in Computer Science required."
Output: {{"required_skills": ["Tableau", "SQL"], "experience_years": null}}

Description: "Minimum 3 years writing CUDA kernels and training large language models in PyTorch."
Output: {{"required_skills": ["CUDA", "PyTorch", "LLM"], "experience_years": 3}}

Description: "Senior GRC Analyst at Roblox. 7-10 years experience. Maintain SOC 2 and ISO 27001 audits. Use SQL Server, Tableau, Archer."
Output: {{"required_skills": ["SOC 2", "ISO 27001", "SQL Server", "Tableau", "Archer"], "experience_years": 7}}

Description: "Senior Frontend Engineer at Roblox. Build Profile UI in React and Next.js with TypeScript. Style with Tailwind. Test with Jest and Playwright."
Output: {{"required_skills": ["React", "Next.js", "TypeScript", "Tailwind CSS", "Jest", "Playwright"], "experience_years": null}}

Description: "Sr. Pipeline Programs Analyst. 3+ years of experience in Sales Operations, Revenue Operations, or a related field. Proficiency in Salesforce and GTM tools."
Output: {{"required_skills": ["Salesforce", "GTM"], "experience_years": 3}}

Description: "8+ years in growth marketing, product management, systems, or operations, including 2+ years in GTM Engineering, AI Engineering, or Solutions Engineering."
Output: {{"required_skills": [], "experience_years": 8}}

Description: "13+ years of professional experience. 6+ years of hands-on technical leadership. 3+ years of experience with Kubernetes and containerization. Experience with CI/CD and cloud platforms."
Output: {{"required_skills": ["Kubernetes", "CI/CD"], "experience_years": 13}}

Examples of WRONG extraction (DO NOT do this):

Description: "Senior SWE, Safety Data / ML Infra at Roblox. Build ML pipelines."
WRONG: {{"required_skills": ["Roblox", "AI", "Machine Learning", "Computer Science", "Engineering"], "experience_years": null}}
RIGHT: {{"required_skills": [], "experience_years": null}}  -> no specific tools named; "Machine Learning" alone is too generic.

Description: "Senior Frontend at Roblox. The role is part of the Profile team."
WRONG: {{"required_skills": ["Roblox", "Profile"], "experience_years": null}}
RIGHT: {{"required_skills": [], "experience_years": null}}

Now extract from this job description:

{description}
"""

# ── Broad second-pass prompt ──────────────────────────────────────────────────
# Used only when the strict pass returns fewer than 2 skills.
# Higher recall, same blocklist/cross-check guardrails applied in Python.
SKILL_EXTRACTION_BROAD_PROMPT = """Scan this job description and list EVERY technical skill, tool, or technology mentioned.

Include: programming languages, frameworks, libraries, databases, cloud services, infrastructure tools,
protocols, APIs, data-pipeline tools, monitoring tools, compliance frameworks, and any named software product.

Rules:
- Only output items that actually appear in the text — do NOT invent or infer.
- Do NOT output generic labels: "AI", "Machine Learning", "software", "data", "cloud", "engineering", "technology".
- Do NOT output soft skills, degrees, or seniority levels.
- Return ONLY the JSON object — no markdown, no explanation.

Output format:
{{"required_skills": ["skill1", "skill2", ...]}}

Job description:
{description}
"""

YEARS_EXTRACTION_PROMPT = """Read the job description below and extract the minimum years of relevant experience required.

Rules:
- Return ONLY a JSON object: {{"experience_years": <integer or null>}}
- experience_years must be a single integer — the MINIMUM years of experience required overall.
- If the requirement is a range ("3-5 years"), return the lower bound (3).
- If only sub-requirements are listed ("including 2+ years in X"), return the sub-requirement value.
- Understand natural-language phrasings:
    - "a decade of experience"                    -> 10
    - "several years" / "multiple years"          -> null  (no specific number)
    - "entry-level" / "new grad" / "0-1 years"   -> 0
    - "mid-level" alone with no number            -> null
    - "at least four years"                       -> 4
    - "ten or more years"                         -> 10
    - "two to three years"                        -> 2
- If no years of experience are mentioned anywhere, return null.
- Return ONLY the JSON — no explanation, no markdown.

Job description:
{description}
"""

EXTRACTION_PROMPT = """You are a job data extraction assistant. Given raw HTML from a LinkedIn job card, extract the following fields and return ONLY valid JSON.

Required JSON schema:
{{
  "company_name": "string or null",
  "title": "string",
  "description": "string (brief summary of the role if visible)",
  "link": "string (full URL)",
  "location": "string",
  "posted_date": "ISO 8601 datetime string or null",
  "salary": {{"min": number, "max": number, "currency": "string"}} or null
}}

Rules:
- Return ONLY the JSON object, no explanation or markdown
- If a field cannot be found, use null
- For salary, extract numeric values only. If no salary info, use null
- For posted_date, convert relative times like "2 hours ago" to approximate ISO datetime based on current time
- For description, extract whatever role info is visible in the card
- Use the provided link if the HTML doesn't contain one

Link hint: {link}

HTML:
{html}
"""
