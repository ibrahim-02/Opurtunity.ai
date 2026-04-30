SKILL_EXTRACTION_PROMPT = """Extract the technical skills, tools, programming languages, frameworks, platforms, libraries, databases, cloud services, methodologies, and compliance/regulatory frameworks that are EXPLICITLY named in the job description below.

STRICT RULES — read all before answering:

1. Only output items that appear word-for-word in the text. Do NOT infer skills that "would be needed" for this role.
3. Output the COMPLETE term — never truncate. "Global Illumination" stays as "Global Illumination", not "Global Illu" or "Global". "Generative AI" stays as "Generative AI", not "Gen".
4. NEVER output any of these:
   - Company names (e.g. "Roblox", "Carvana", "Datadog") — even if the company name appears in the JD
   - Team names or product names internal to the company
   - Generic field labels: "AI", "ML", "Engineering", "Software Engineering", "Computer Science", "Programming", "Development", "Technology", "Information Technology"
   - Degree fields: "Computer Science", "Mathematics", "Statistics" (these are degrees, not skills)
   - Soft skills: "communication", "leadership", "teamwork", "problem solving"
   - Buzz phrases: "data-driven", "fast-paced", "cross-functional"
   - Years of experience or seniority levels
5. Specific tools, named technologies, named frameworks, named compliance regimes (SOC 2, GDPR, HIPAA, PCI-DSS, ISO 27001) ARE valid. "Machine Learning" alone is NOT a skill — but "scikit-learn", "PyTorch", "TensorFlow", "XGBoost", "LangChain", "LlamaIndex", "Transformers", "Hugging Face" ARE.
6. Do NOT pad. If only 2 skills are named, return only those 2. If none, return [].
7. Return ONLY the JSON object — no markdown fences, no commentary.

Output format:
{{"skills": ["<exact skill 1>", "<exact skill 2>", ...]}}

Examples of CORRECT extraction:

Description: "We need someone fluent in Go and Postgres, ETL, with experience deploying services on Kubernetes."
Output: {{"skills": ["Go", "PostgreSQL", "Kubernetes", "ETL"]}}

Description: "Build dashboards in Tableau and analyse data with SQL. Bachelor's in Computer Science required."
Output: {{"skills": ["Tableau", "SQL"]}}

Description: "Write CUDA kernels and train large language models in PyTorch on multi-GPU clusters."
Output: {{"skills": ["CUDA", "PyTorch", "LLM"]}}

Description: "Senior GRC Analyst at Roblox. Maintain SOC 2 and ISO 27001 audit programs. Use SQL Server, Tableau, and Archer."
Output: {{"skills": ["SOC 2", "ISO 27001", "SQL Server", "Tableau", "Archer"]}}

Description: "Senior Frontend Engineer at Roblox. Build Profile UI in React and Next.js with TypeScript. Style with Tailwind. Test with Jest and Playwright."
Output: {{"skills": ["React", "Next.js", "TypeScript", "Tailwind CSS", "Jest", "Playwright"]}}

Description: "Senior Rendering Engineer. Deep knowledge of Vulkan, Metal, DirectX, and OpenGL. Familiar with PBR, global illumination, shadow mapping, and modern GPU architectures."
Output: {{"skills": ["Vulkan", "Metal", "DirectX", "OpenGL", "PBR", "Global Illumination", "Shadow Mapping"]}}

Examples of WRONG extraction (DO NOT do this):

Description: "Senior SWE, Safety Data / ML Infra at Roblox. Build ML pipelines."
WRONG: {{"skills": ["Roblox", "AI", "Machine Learning", "Computer Science", "Engineering"]}}
RIGHT: {{"skills": []}}  =>BECAUSE the JD does not explicitly name any specific AI/ML tools, frameworks, or methodologies. "Machine Learning" alone is too generic and not a specific skill.

Description: "Senior Frontend at Roblox. The role is part of the Profile team."
WRONG: {{"skills": ["Roblox", "Profile"]}}
RIGHT: {{"skills": []}}

Now extract from this job description:

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
