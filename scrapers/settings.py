"""
Shared filter configuration for ALL scrapers (LinkedIn, Indeed, Greenhouse, Lever).
This is the single source of truth — change a keyword here and every scraper picks it up.

Per-scraper settings (URLs, delays, search queries) live in scrapers/<name>/settings.py.
"""

# ── Title allowlist ──────────────────────────────────────────────────────────
# Job must contain at least one of these (word-boundary regex match).
TITLE_KEYWORDS = [
    "analyst", "scientist", "developer", "architect",
    "mlops", "devops", "dataops", "machine learning", "data", "bi ",
     "business intelligence", "analytics", "etl","sql",
    "python", "cloud", "database", "pipeline", " ai ", "artificial intelligence",
    "llm", "nlp", "rag", "generative",  "Software Engineer", "platform", "big data", "deep learning",
    "visualization", "reporting", "spark", "hadoop",
    "databricks", "snowflake", "dbt","Information Technology","DevSecOps"
]

# ── Title hard-exclude (rejected even if it matches the allowlist) ───────────
TITLE_EXCLUDE_KEYWORDS = [
    "mechanical engineer", "mechanical engineering",
    "electrical engineer", "electrical engineering",
    "data entry"
]

# ── Company blocklist (staffing agencies, job boards, ATS providers) ─────────
EXCLUDED_COMPANIES = {
    "Mercor","FetchJobs.co","DataAnnotation","Why Hiring","Quik Hire Staffing","6% Não Basta","Jobs Ai", "dice", "remote hunter", "jobright", "jobright.ai", "joveo AI", "Sundayy",
    "carvana","Manha Tech Solutions LLC","Georgia IT, Inc"
    "Joveo Ai", "jobs via equest", "lensa", "talent.com", "adzuna", "jooble",
    "zippia","Tech Consulting", "nexxt", "jobcase", "talentify", "jobot", "hired",
    "jobs via jobright", "recruit.net", "resume-library", "jora",
    "fetch recruit", "built in", "glassdoor", "indeed", "ziprecruiter",
    "snagajob","Inside Higher Ed", "careerbuilder", "monster", "simplyhired", "the ladders",
    "the muse", "wellfound", "lever", "greenhouse", "smartrecruiters",
    "breezy hr", "jobvite", "workable", "betterteam", "jobscore",
    "recruitee", "teamtailor", "pinpoint", "freshteam", "zoho recruit",
    "robert half", "robert half technology", "randstad", "randstad digital",
    "randstad usa", "adecco", "manpower", "manpowergroup", "kelly services",
    "kelly", "kforce", "insight global", "aerotek", "experis", "apex systems",
    "teksystems", "hays", "RemoteHunter", "Remote Hunter", "Jobs via Dice",
    "jobs via lensa", "jobs via talent.com", "jobs via adzuna", "jobs via jooble",
    "hackajob", "Dice", "beacon hill", "addison group", "cybercoders",
    "yoh services", "modis", "volt", "motion recruitment", "judge group",
    "mindlance", "mastech", "mastech digital", "vaco", "horizontal talent",
    "softpath system", "disys", "strategic staffing solutions", "staffmark",
    "staffing solutions", "recruiting solutions", "talent bridge",
    "staffing bridge", "staffing inc", "staffing llc", "staffing group",
    "recruiting group", "hiring group", "talent group", "workforce solutions",
    "workforce staffing", "net2source", "tti", "tanisha systems", "igate",
    "tek systems", "compunnel", "suna solutions", "lancesoft", "nityo infotech",
    "idexcel", "doit software", "cynet systems", "futran solutions",
    "amerit consulting", "inforeliance", "steneral consulting",
    "pyramid consulting", "infotree global solutions", "axelon services",
    "iconma", "mvp staffing",
}

# ── US location filter ───────────────────────────────────────────────────────
US_STATE_CODES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA",
    "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
    "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT",
    "VA","WA","WV","WI","WY","DC",
}

US_KEYWORDS = (
    "united states", "usa", "u.s.a", "u.s.", " us ",
    "remote - us", "remote (us)", "remote, us", "us remote","Dublin"
    # Major US metros — LinkedIn often uses "{City} Area" format with no state code
    "new york", "manhattan", "brooklyn", "bronx", "queens",
    "los angeles", "san francisco", "bay area", "silicon valley", "san jose",
    "seattle", "chicago", "boston", "austin", "dallas", "houston",
    "atlanta", "denver", "phoenix", "philadelphia", "san diego",
    "portland", "minneapolis", "detroit", "charlotte", "nashville",
    "washington, d", "dc metro", "baltimore", "raleigh", "durham",
    "miami", "fort lauderdale", "orlando", "tampa", "jacksonville",
    "las vegas", "salt lake", "sacramento", "san antonio", "columbus",
    "cleveland", "pittsburgh", "richmond", "memphis", "new orleans",
    "hartford", "buffalo", "rochester", "albany", "omaha", "tulsa",
    "louisville", "indianapolis", "cincinnati", "kansas city", "st. louis",
    "milwaukee", "madison", "des moines", "boise", "spokane", "tucson",
    "albuquerque", "el paso", "oklahoma city", "little rock","springfield", "worcester", "providence", "syracuse", "allentown", "erie", "lancaster", "york", "harrisburg", "reading", "scranton", "pennsylvania", "penn", "rhode island", "rhode island", "vermont", "vermont", "maine", "maine", "new hampshire", "new hampshire",
)

NON_US_KEYWORDS = (
    "united kingdom", "uk", "london", "manchester", "edinburgh", "dublin",
    "ireland", "scotland", "wales",
    "berlin", "munich", "frankfurt", "germany", "deutschland",
    "paris", "lyon", "france",
    "amsterdam", "rotterdam", "netherlands", "holland",
    "madrid", "barcelona", "spain",
    "rome", "milan", "italy","india","delhi","bangalore","mumbai","hyderabad","pune","chennai",
    "stockholm", "sweden", "oslo", "norway", "copenhagen", "denmark",
    "helsinki", "finland", "warsaw", "poland", "prague", "czech",
    "lisbon", "portugal", "zurich", "switzerland", "vienna", "austria",
    "toronto", "vancouver", "montreal", "ottawa", "calgary", "canada",
    "mexico city", "mexico", "sydney", "melbourne", "brisbane", "australia",
    "singapore", "tokyo", "japan", "osaka",
    "shanghai", "beijing", "shenzhen", "china", "hong kong",
    "bangalore", "mumbai", "delhi", "hyderabad", "pune", "chennai", "india",
    "dubai", "abu dhabi", "uae", "tel aviv", "israel",
    "são paulo", "sao paulo", "brazil", "buenos aires", "argentina",
    "seoul", "south korea", "bangkok", "thailand", "manila", "philippines",
    "istanbul", "turkey", "lagos", "nigeria", "cape town", "south africa",
    "nairobi", "kenya", "emea", "apac", "latam",
)
