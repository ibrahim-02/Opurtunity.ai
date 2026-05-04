import json
import re

from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from llm.prompts import SKILL_EXTRACTION_BROAD_PROMPT, SKILL_EXTRACTION_PROMPT


# ── Hard blocklist (lowercase, exact match after normalisation) ───────────────
_BLOCKLIST = {
    # generic field/category labels
    "ai", "ml", "ai/ml", "ml/ai",
    "engineering", "software engineering", "software", "development", "developer",
    "computer science", "computer engineering",
    "mathematics", "math", "statistics",
    "programming", "coding",
    "technology", "information technology", "it",
    "data", "data science", "data analytics", "analytics",
    "machine learning", "deep learning", "artificial intelligence",
    "cloud", "cloud computing", "devops", "mlops", "dataops",
    "research",
    # soft skills / phrases
    "communication", "leadership", "teamwork", "problem solving", "problem-solving",
    "collaboration", "stakeholder management",
    "data-driven", "fast-paced", "cross-functional", "agile mindset",
    # degrees
    "bachelor", "bachelors", "bachelor's", "master", "masters", "master's",
    "phd", "ph.d", "ph.d.", "doctorate",
    # filler words
    "experience", "skills", "tools", "frameworks", "platforms", "languages",
    "english", "fluent",
}

_MIN_LEN = 3
_SHORT_ALLOWED = {"go", "r", "c", "c#", "c++", "f#", "vb", "qa", "ui", "ux", "qa/qe"}

_NORMALIZE = {
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "nodejs": "Node.js",
    "node js": "Node.js",
    "node.js": "Node.js",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "mssql": "SQL Server",
    "ms sql": "SQL Server",
    "microsoft sql server": "SQL Server",
    "amazon web services": "AWS",
    "google cloud platform": "GCP",
    "google cloud": "GCP",
    "microsoft azure": "Azure",
    "microsoft power bi": "Power BI",
    "powerbi": "Power BI",
    "tailwind": "Tailwind CSS",
    "tailwindcss": "Tailwind CSS",
}

# ── Known-technology registry: lowercase key → canonical display name ─────────
# Used for a deterministic scan that catches what the LLM misses or truncates.
_SKILL_REGISTRY: dict[str, str] = {
    # Programming languages
    "python": "Python", "javascript": "JavaScript", "typescript": "TypeScript",
    "go": "Go", "golang": "Go", "rust": "Rust", "java": "Java", "ruby": "Ruby",
    "swift": "Swift", "kotlin": "Kotlin", "scala": "Scala", "php": "PHP",
    "elixir": "Elixir", "haskell": "Haskell", "perl": "Perl", "lua": "Lua",
    "dart": "Dart", "julia": "Julia", "ocaml": "OCaml", "erlang": "Erlang",
    "clojure": "Clojure", "bash": "Bash", "c#": "C#", "c++": "C++", "f#": "F#",
    # Web / frontend
    "react": "React", "next.js": "Next.js", "nextjs": "Next.js",
    "vue.js": "Vue.js", "vuejs": "Vue.js", "angular": "Angular", "svelte": "Svelte",
    "webpack": "Webpack", "vite": "Vite", "redux": "Redux", "html": "HTML", "css": "CSS",
    # Backend / frameworks / protocols
    "django": "Django", "flask": "Flask", "fastapi": "FastAPI",
    "rails": "Ruby on Rails", "ruby on rails": "Ruby on Rails",
    "spring boot": "Spring Boot", "express.js": "Express.js",
    "nestjs": "NestJS", "nest.js": "NestJS",
    "graphql": "GraphQL", "grpc": "gRPC", "node.js": "Node.js", "nodejs": "Node.js",
    "rest api": "REST API", "restful": "RESTful",
    # Databases
    "postgresql": "PostgreSQL", "postgres": "PostgreSQL", "mysql": "MySQL",
    "mongodb": "MongoDB", "redis": "Redis", "elasticsearch": "Elasticsearch",
    "snowflake": "Snowflake", "bigquery": "BigQuery", "dynamodb": "DynamoDB",
    "cassandra": "Cassandra", "sqlite": "SQLite", "neo4j": "Neo4j",
    "clickhouse": "ClickHouse", "pinecone": "Pinecone", "weaviate": "Weaviate",
    "chroma": "Chroma", "qdrant": "Qdrant", "sql": "SQL", "oracle": "Oracle",
    "sql server": "SQL Server",
    # Cloud & infra
    "aws": "AWS", "gcp": "GCP", "azure": "Azure",
    "kubernetes": "Kubernetes", "k8s": "Kubernetes", "docker": "Docker",
    "terraform": "Terraform", "helm": "Helm", "ansible": "Ansible",
    "pulumi": "Pulumi", "cloudformation": "CloudFormation", "cdk": "AWS CDK",
    # CI/CD
    "ci/cd": "CI/CD", "github actions": "GitHub Actions", "jenkins": "Jenkins",
    "circleci": "CircleCI", "gitlab ci": "GitLab CI", "argocd": "ArgoCD",
    "spinnaker": "Spinnaker",
    # Data & streaming
    "kafka": "Kafka", "apache spark": "Apache Spark", "spark": "Apache Spark",
    "pyspark": "PySpark", "airflow": "Airflow", "apache airflow": "Airflow",
    "dbt": "dbt", "flink": "Apache Flink", "databricks": "Databricks", "hive": "Hive",
    # ML / AI
    "pytorch": "PyTorch", "tensorflow": "TensorFlow", "keras": "Keras",
    "scikit-learn": "scikit-learn", "sklearn": "scikit-learn",
    "langchain": "LangChain", "llamaindex": "LlamaIndex",
    "hugging face": "Hugging Face", "transformers": "Transformers",
    "cuda": "CUDA", "xgboost": "XGBoost", "lightgbm": "LightGBM",
    "ray": "Ray", "jax": "JAX", "onnx": "ONNX", "mlflow": "MLflow",
    "deepspeed": "DeepSpeed", "megatron-lm": "Megatron-LM",
    # Security / auth / compliance
    "scim": "SCIM", "saml": "SAML", "oauth": "OAuth", "openid": "OpenID",
    "soc 2": "SOC 2", "gdpr": "GDPR", "hipaa": "HIPAA",
    "pci-dss": "PCI-DSS", "iso 27001": "ISO 27001",
    # Observability
    "prometheus": "Prometheus", "grafana": "Grafana",
    "opentelemetry": "OpenTelemetry", "datadog": "Datadog",
    "splunk": "Splunk", "new relic": "New Relic", "newrelic": "New Relic",
    # SaaS / platforms
    "salesforce": "Salesforce", "stripe": "Stripe", "twilio": "Twilio",
    "zendesk": "Zendesk", "tableau": "Tableau", "looker": "Looker",
    "power bi": "Power BI", "powerbi": "Power BI",
    "amplitude": "Amplitude", "mixpanel": "Mixpanel",
    "fivetran": "Fivetran", "segment": "Segment",
    # Tooling
    "git": "Git", "github": "GitHub", "gitlab": "GitLab", "jira": "Jira",
    "linux": "Linux", "unix": "Unix", "protobuf": "Protobuf",
    "rabbitmq": "RabbitMQ", "nginx": "Nginx", "celery": "Celery",
    "etl": "ETL", "microservices": "Microservices",
    "rag": "RAG", "llm": "LLM",
    # Quantum
    "qiskit": "Qiskit", "cirq": "Cirq", "pennylane": "PennyLane",
    "amazon braket": "Amazon Braket", "braket": "Amazon Braket",
    "quantum error correction": "quantum error correction",
    "quantum error mitigation": "quantum error mitigation",
    # Mobile
    "react native": "React Native", "flutter": "Flutter",
    "swiftui": "SwiftUI", "jetpack compose": "Jetpack Compose",
    "expo": "Expo",
    # Testing
    "jest": "Jest", "playwright": "Playwright", "cypress": "Cypress",
    "pytest": "pytest", "vitest": "Vitest", "storybook": "Storybook",
    "selenium": "Selenium",
    # Auth / identity
    "auth0": "Auth0", "okta": "Okta", "cognito": "AWS Cognito",
    "clerk": "Clerk",
    # GraphQL ecosystem
    "apollo": "Apollo", "trpc": "tRPC",
    # ORM / DB tooling
    "prisma": "Prisma", "sqlalchemy": "SQLAlchemy", "sequelize": "Sequelize",
    "supabase": "Supabase", "planetscale": "PlanetScale",
    # Hosting / edge
    "vercel": "Vercel", "netlify": "Netlify", "cloudflare workers": "Cloudflare Workers",
    # Protocols
    "websocket": "WebSocket", "mqtt": "MQTT", "grpc": "gRPC",
    # Hardware / embedded / EDA
    "matlab": "MATLAB", "vhdl": "VHDL", "verilog": "Verilog",
    "labview": "LabVIEW", "fpga": "FPGA", "rtos": "RTOS",
    # LLM APIs / AI platforms
    "openai api": "OpenAI API", "openai": "OpenAI API",
    "anthropic": "Anthropic API", "langsmith": "LangSmith",
    "vertex ai": "Vertex AI", "bedrock": "AWS Bedrock",
    # ERP / finance SaaS
    "netsuite": "NetSuite", "sap": "SAP", "workday": "Workday",
    "quickbooks": "QuickBooks",
    # Additional data / analytics
    "dax": "DAX", "looker studio": "Looker Studio",
    "pandas": "pandas", "numpy": "NumPy", "polars": "Polars",
    "jupyter": "Jupyter", "matplotlib": "Matplotlib", "plotly": "Plotly",
}


def _key_in_text(key: str, text_lower: str) -> bool:
    """Case-insensitive word-boundary match of registry key in pre-lowercased text."""
    if key not in text_lower:
        return False
    escaped = re.escape(key)
    # Keys ending in non-alphanumeric (C++, C#) need lookaround instead of \b
    if key[-1].isalnum() or key[-1] in ("_",):
        pattern = r"\b" + escaped + r"\b"
    else:
        pattern = r"(?<![a-z0-9])" + escaped + r"(?![a-z0-9])"
    return bool(re.search(pattern, text_lower))


def _scan_known_skills(text: str) -> list[str]:
    """Scan full description for registry-known tech skills (deterministic, no LLM)."""
    text_lower = text.lower()
    found: dict[str, str] = {}  # canonical_lower → canonical (dedup)
    for key, canonical in _SKILL_REGISTRY.items():
        if _key_in_text(key, text_lower):
            found[canonical.lower()] = canonical
    return list(found.values())


# ── Experience-year extraction ────────────────────────────────────────────────

# Matches: "5+ years of experience", "10 years experience", "3-5 years in Sales Ops",
#          "8+ years in growth marketing"
_YEARS_RE = re.compile(
    r"(\d{1,2})\s*(?:\+|[-–]\s*\d{1,2}|\s+(?:to|or\s+more)\s+\d{0,2})?\s*"
    r"\+?\s*years?\s+(?:(?:of\s+)?(?:relevant\s+|professional\s+|work\s+|related\s+)?"
    r"(?:experience|exp(?:erience)?)|in\b)",
    re.IGNORECASE,
)

# Sub-requirements introduced by "including / of which / comprising" must be excluded
# so "8+ years ..., including 2+ years in X" → 8, not 2
_SUB_YEARS_RE = re.compile(
    r"(?:including|of\s+which|comprising|of\s+that|plus)\s+(\d{1,2})\s*\+?\s*years?",
    re.IGNORECASE,
)


def _extract_years_fallback(description: str) -> int | None:
    """
    Deterministic regex scan for experience_years when LLM returns null.

    Returns the FIRST main year mention (primary requirement always comes first in JDs).
    Sub-requirements introduced by 'including / of which / comprising' are excluded.
    """
    sub_values = {int(m) for m in _SUB_YEARS_RE.findall(description) if 1 <= int(m) <= 20}

    # Collect (text-position, value) so we can return the first-appearing one
    main_hits: list[tuple[int, int]] = []
    all_hits: list[tuple[int, int]] = []
    for m in _YEARS_RE.finditer(description):
        val = int(m.group(1))
        if not 1 <= val <= 20:
            continue
        all_hits.append((m.start(), val))
        if val not in sub_values:
            main_hits.append((m.start(), val))

    candidates = main_hits if main_hits else all_hits
    if not candidates:
        return None
    # Sort by position and take the first (= the primary/overall requirement)
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


# ── Skill filtering / normalisation ──────────────────────────────────────────

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def _filter_skills(
    raw_skills: list[str],
    description: str,
    company_name: str | None,
) -> list[str]:
    """
    Apply guardrails to a merged skill list (LLM output + registry scan):
    1. Drop blocklisted generic terms / soft skills / degrees
    2. Drop the company name and its tokens
    3. Drop tokens below minimum length (unless allow-listed)
    4. Cross-check: skill must appear in source text (kills LLM hallucinations;
       registry skills always pass since they were found by substring match)
    5. Normalize to canonical forms
    6. Dedupe case-insensitively
    """
    desc_lower = description.lower() if description else ""
    company_lower = _norm(company_name) if company_name else None

    company_tokens: set[str] = set()
    if company_lower:
        company_tokens.add(company_lower)
        for tok in re.split(r"[\s,.&]+", company_lower):
            tok = tok.strip().lower()
            if tok and tok not in {"inc", "corp", "llc", "ltd", "co", "the"}:
                company_tokens.add(tok)

    seen: set[str] = set()
    out: list[str] = []
    for raw in raw_skills:
        if not isinstance(raw, str):
            continue
        s = raw.strip()
        if not s:
            continue
        norm = _norm(s)

        if len(norm) < _MIN_LEN and norm not in _SHORT_ALLOWED:
            continue
        if norm in _BLOCKLIST:
            continue
        if norm in company_tokens:
            continue
        if desc_lower and norm not in desc_lower:
            continue

        canonical = _NORMALIZE.get(norm, s)
        key = canonical.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(canonical)

    return out


# ── Main extractor ────────────────────────────────────────────────────────────

class SkillExtractor:
    def __init__(self, client):
        """`client` must expose generate(prompt) -> JSON string."""
        self.client = client

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def _call_llm(self, prompt: str) -> str:
        return self.client.generate(prompt)

    def _broad_pass(self, description: str, company_name: str | None) -> list[str]:
        """High-recall second pass — fires only when strict pass + registry found < 2 skills."""
        prompt = SKILL_EXTRACTION_BROAD_PROMPT.format(description=description[:4000])
        try:
            raw = self._call_llm(prompt)
            parsed = json.loads(raw)
            raw_skills = parsed.get("required_skills", [])
            if not isinstance(raw_skills, list):
                return []
            return _filter_skills(raw_skills, description, company_name)
        except Exception as e:
            logger.debug(f"Broad pass failed: {e}")
            return []

    def extract(
        self,
        description: str,
        company_name: str | None = None,
    ) -> dict | None:
        """
        Returns {"required_skills": [...], "experience_years": int | None}
        or None on hard failure.

        Strategy:
        - LLM sees first 4 000 chars → good at nuanced/named skills
        - Registry scan on FULL text → catches skills beyond truncation + fills gaps
        - Union of both, deduplicated through the same guardrail filter
        """
        truncated = description[:4000]
        prompt = SKILL_EXTRACTION_PROMPT.format(description=truncated)
        try:
            raw = self._call_llm(prompt)
            parsed = json.loads(raw)

            # LLM skills (may miss things after char 4000 or be sparse)
            llm_skills: list[str] = parsed.get("required_skills", parsed.get("skills", []))
            if not isinstance(llm_skills, list):
                llm_skills = []

            # Registry scan on full text — deterministic, never hallucinates
            registry_skills = _scan_known_skills(description)

            # Union: LLM first (preserves ordering/nuance), then registry additions
            merged = list(llm_skills) + registry_skills

            # Apply all guardrails once to the merged list
            cleaned_skills = _filter_skills(merged, description, company_name)

            # Broad second pass: fires only for genuinely sparse results (< 2 skills).
            # Catches niche/proprietary tech neither the strict LLM prompt nor the
            # registry know about. Single extra LLM call; skipped for normal jobs.
            if len(cleaned_skills) < 2:
                broad = self._broad_pass(description, company_name)
                existing_lower = {s.lower() for s in cleaned_skills}
                additions = [s for s in broad if s.lower() not in existing_lower]
                if additions:
                    cleaned_skills.extend(additions)
                    logger.debug(f"Broad pass added {len(additions)} skills: {additions}")

            if len(registry_skills) > len(llm_skills):
                logger.debug(
                    f"Registry added {len(registry_skills) - len(llm_skills)} skills "
                    f"beyond LLM output"
                )

            # Experience years — LLM first, regex fallback if null
            raw_years = parsed.get("experience_years")
            years: int | None = None
            if isinstance(raw_years, int) and raw_years >= 0:
                years = raw_years
            elif isinstance(raw_years, float) and raw_years >= 0:
                years = int(raw_years)
            elif isinstance(raw_years, str):
                m = re.search(r"\d+", raw_years)
                if m:
                    years = int(m.group())

            if years is None and description:
                years = _extract_years_fallback(description)
                if years is not None:
                    logger.debug(f"experience_years filled by regex fallback: {years}")

            return {"required_skills": cleaned_skills, "experience_years": years}

        except json.JSONDecodeError as e:
            logger.warning(f"Skill extraction JSON parse error: {e}")
            return None
        except Exception as e:
            logger.error(f"Skill extraction failed: {e}")
            return None
