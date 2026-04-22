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
