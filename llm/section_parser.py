"""
Extract the highest-signal sections from a job description before embedding.

Pipeline:
1. Strip HTML to plain text (BeautifulSoup) so the embedder doesn't waste capacity on tags.
2. Walk lines and classify each as: requirements / skills / responsibilities / STOP / content.
3. Append content lines to the current bucket; STOP headers (benefits, legal, EEO, "about us")
   reset the cursor so boilerplate never lands in any bucket.
4. Concatenate buckets in priority order: requirements -> skills -> responsibilities.

Falls back to truncated plain text when no recognised section header appears.
"""
import re

from bs4 import BeautifulSoup

_MAX_CHARS = 1500  # ~500 tokens worst-case for mxbai-embed-large's 512-token context
_HEADER_MAX_LEN = 60
_HEADER_MATCH_RATIO = 0.4  # the regex must cover at least this fraction of the line

_RESP_RE = re.compile(
    r"\b(responsibilities|what you(?:'| )?ll do|what you will do|key responsibilities|"
    r"your role|role overview|duties|day[\s\-]to[\s\-]day|in this role|"
    r"what you(?:'| )?ll be doing|about the role|the role|"
    r"you(?:'| )?ll(?: be)?|you will(?: be)?|in your day)\b",
    re.IGNORECASE,
)
_REQ_RE = re.compile(
    r"\b(requirements?|qualifications?|what we(?:'| )?re looking for|what we are looking for|"
    r"what you(?:'| )?ll need|what you will need|must[\s\-]have|"
    r"minimum qualifications?|basic qualifications?|preferred qualifications?|"
    r"required experience|required skills?|minimum requirements?|"
    r"what you (?:should|will|need to) (?:know|have|bring|need)(?:\s*[/&]\s*(?:know|have|bring|need))?|"
    r"you should (?:know|have|bring)|what we need|"
    r"you have|you(?:'| )?ve|you bring|you(?:'| )?ll have|you will have|"
    r"who you are|about you|the ideal candidate|your background|your experience)\b",
    re.IGNORECASE,
)
_SKILL_RE = re.compile(
    r"\b((?:technical |required |preferred |key )?skills?|"
    r"tech(?:nical)? (?:stack|requirements?)|"
    r"tools?(?: and technologies?)?|technologies?|expertise|"
    r"our (?:stack|tools)|tools we use|nice[\s\-]to[\s\-]have|"
    r"bonus (?:points|skills))\b",
    re.IGNORECASE,
)
_STOP_RE = re.compile(
    r"\b(benefits?|perks?|"
    r"what we(?:'| )?ll offer|what we will offer|our offer|we offer|"
    r"what you(?:'| )?ll get|what you will get|"
    r"compensation|salary range|pay range|base pay|"
    r"legal(?: stuff)?|equal (?:opportunity|employment)|eeo|"
    r"hiring is contingent|accommodations?|disclosures?|"
    r"about (?:us|the company|our company|carvana)|who we are|"
    r"our (?:mission|values|culture|story|team|company)|"
    r"why (?:work|join)|diversity(?:,| and| &) inclusion|"
    r"to apply|how to apply|application (?:process|instructions)|"
    r"please note|background check|"
    r"other requirements|basic requirements|additional requirements)\b",
    re.IGNORECASE,
)


_SMART_QUOTES = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"',
    " ": " ",  # non-breaking space
})


def _strip_html(text: str) -> str:
    if not text:
        return ""
    if "<" in text:
        text = BeautifulSoup(text, "lxml").get_text(separator="\n", strip=True)
    return text.translate(_SMART_QUOTES)


def _classify_header(line: str) -> str | None:
    """Return 'STOP' | 'requirements' | 'skills' | 'responsibilities' | None."""
    stripped = line.strip().rstrip(":").strip()
    if not stripped or len(stripped) > _HEADER_MAX_LEN:
        return None

    line_len = len(stripped)

    def _matches_strongly(pattern: re.Pattern) -> bool:
        m = pattern.search(stripped)
        if not m:
            return False
        return (m.end() - m.start()) / line_len >= _HEADER_MATCH_RATIO

    if _matches_strongly(_STOP_RE):
        return "STOP"
    if _matches_strongly(_REQ_RE):
        return "requirements"
    if _matches_strongly(_SKILL_RE):
        return "skills"
    if _matches_strongly(_RESP_RE):
        return "responsibilities"
    return None


def parse(text: str) -> str:
    """Return the most embedding-relevant portion of a job description."""
    plain = _strip_html(text)
    lines = plain.splitlines()
    sections: dict[str, list[str]] = {
        "requirements": [],
        "skills": [],
        "responsibilities": [],
    }
    current: str | None = None

    for line in lines:
        category = _classify_header(line)
        if category == "STOP":
            current = None
        elif category is not None:
            current = category
        elif current and line.strip():
            sections[current].append(line.strip())

    if any(sections.values()):
        parts: list[str] = []
        for key in ("requirements", "skills", "responsibilities"):
            parts.extend(sections[key])
        return " ".join(parts)[:_MAX_CHARS]

    return plain[:_MAX_CHARS]
