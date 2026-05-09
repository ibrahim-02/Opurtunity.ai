"""
Standalone Workday discovery — no DB, no Docker.
Run directly on any machine with internet access.

Saves results to workday_discovered.csv.

Usage:
    python scrapers/workday/run_discovery.py
    python scrapers/workday/run_discovery.py --limit 500
    python scrapers/workday/run_discovery.py --concurrency 40
"""
import argparse
import asyncio
import csv
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from loguru import logger
logger.remove()
logger.add(sys.stderr, level="INFO",
           format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}")

# ── Large company seed list ───────────────────────────────────────────────────
# ~300 well-known companies across tech, finance, healthcare, consulting, retail
# that are known or likely to use Workday ATS.

COMPANY_NAMES = [
    # Tech / SaaS
    "Salesforce", "Adobe", "ServiceNow", "Workday", "Oracle", "SAP",
    "Cisco", "NVIDIA", "Intel", "Qualcomm", "Broadcom", "Marvell Technology",
    "Snowflake", "Datadog", "CrowdStrike", "Palantir", "Cloudflare",
    "MongoDB", "Elastic", "Zscaler", "UiPath", "Twilio", "Okta", "Splunk",
    "Palo Alto Networks", "Fortinet", "Veeva Systems", "Zendesk",
    "Zoom Video Communications", "Box", "Dropbox", "DocuSign",
    "Coupa Software", "Procore Technologies", "Paylocity", "Paycom",
    "Pegasystems", "NICE Systems", "Ceridian HCM", "Cornerstone OnDemand",
    "Instructure", "Domo", "Medallia", "Qualtrics", "Sprinklr",
    "Bazaarvoice", "Demandware", "Apttus", "Conga", "Verint Systems",
    "PROS Holdings", "Informatica", "MicroStrategy", "Teradata", "Alteryx",
    "Thoughtworks", "EPAM Systems", "Globant", "WEX", "Marqeta",
    "nCino", "Q2 Holdings", "Green Dot", "Shift4 Payments",
    "NCR Corporation", "Unisys", "DXC Technology", "Conduent",
    "Concentrix", "TTEC Holdings", "Teleperformance", "Sykes Enterprises",
    "iGate", "Mphasis", "Hexaware Technologies", "Kforce",
    "Cognizant Technology Solutions", "Infosys", "Wipro", "HCL Technologies",
    "Tech Mahindra", "Tata Consultancy Services",
    # Consulting / Defense
    "Accenture", "Capgemini", "CGI", "Leidos", "SAIC",
    "Booz Allen Hamilton", "ManTech", "CACI International",
    "Gartner", "Forrester Research", "IHS Markit",
    "Parsons Corporation", "AECOM", "Jacobs Engineering",
    "Perspecta", "Engility", "PAE", "Maximus", "SAIC",
    "Tetra Tech", "ICF International", "Noblis",
    # Finance / Fintech
    "JPMorgan Chase", "Goldman Sachs", "Morgan Stanley", "Citigroup",
    "Bank of America", "Wells Fargo", "US Bancorp", "PNC Financial",
    "Truist Financial", "Regions Financial", "Huntington Bancshares",
    "KeyCorp", "Comerica", "Cullen Frost Bankers", "First Horizon",
    "Western Alliance Bancorporation", "Glacier Bancorp",
    "American Express", "Visa", "Mastercard", "Discover Financial",
    "Capital One", "Synchrony Financial", "Ally Financial",
    "Equifax", "TransUnion", "Dun Bradstreet",
    "Verisk Analytics", "Fair Isaac", "Black Knight",
    "Fiserv", "Jack Henry Associates", "Broadridge Financial",
    "SS&C Technologies", "Advent Software", "SimCorp",
    "Charles Schwab", "TD Ameritrade", "E*TRADE", "Interactive Brokers",
    "Raymond James Financial", "Stifel Financial", "LPL Financial",
    "Northwestern Mutual", "Principal Financial Group",
    "Lincoln National", "Unum Group", "Aflac", "MetLife",
    "Prudential Financial", "Sun Life Financial", "Manulife",
    "Hartford Financial Services", "Travelers Companies",
    "Chubb", "AIG", "Marsh McLennan", "Aon", "Willis Towers Watson",
    "Gallagher", "Ryan Specialty Group",
    # Healthcare / Pharma
    "Johnson Johnson", "Pfizer", "Merck", "AbbVie", "Bristol Myers Squibb",
    "Eli Lilly", "Amgen", "Gilead Sciences", "Biogen", "Regeneron",
    "Vertex Pharmaceuticals", "Moderna", "BioNTech",
    "Becton Dickinson", "Baxter International", "Boston Scientific",
    "Medtronic", "Stryker", "Zimmer Biomet", "Edwards Lifesciences",
    "Intuitive Surgical", "Hologic", "Integra LifeSciences",
    "McKesson", "AmerisourceBergen", "Cardinal Health",
    "CVS Health", "Walgreens Boots Alliance", "Rite Aid",
    "UnitedHealth Group", "Anthem", "Humana", "Cigna", "Aetna",
    "Centene", "Molina Healthcare", "WellCare Health Plans",
    "HCA Healthcare", "Tenet Healthcare", "Community Health Systems",
    "DaVita", "DaVita Kidney Care", "LabCorp", "Quest Diagnostics",
    "IQVIA Holdings", "Covance", "PPD", "Syneos Health",
    # Retail / Consumer
    "Amazon", "Walmart", "Target", "Costco", "Kroger",
    "Home Depot", "Lowes", "Best Buy", "Staples",
    "Nike", "Adidas", "Under Armour", "VF Corporation",
    "PVH Corp", "Hanesbrands", "Carter", "Columbia Sportswear",
    "Nordstrom", "Macys", "Gap", "L Brands", "PVH",
    "Procter Gamble", "Unilever", "Colgate Palmolive", "Church Dwight",
    "Kimberly Clark", "Energizer Holdings", "Spectrum Brands",
    "General Mills", "Kellogg", "Kraft Heinz", "Mondelez",
    "Hershey", "Campbell Soup", "Conagra Brands", "Tyson Foods",
    "Hormel Foods", "JM Smucker", "TreeHouse Foods",
    # Energy / Industrial
    "ExxonMobil", "Chevron", "ConocoPhillips", "Halliburton",
    "Baker Hughes", "Schlumberger", "Valero Energy",
    "NextEra Energy", "Duke Energy", "Southern Company",
    "Dominion Energy", "Exelon", "Consolidated Edison",
    "Honeywell", "Emerson Electric", "Parker Hannifin",
    "Illinois Tool Works", "Dover Corporation", "Roper Technologies",
    "Danaher", "Fortive", "Xylem", "IDEX Corporation",
    "Watts Water Technologies", "Mueller Water Products",
    "Caterpillar", "Deere", "AGCO", "CNH Industrial",
    "General Electric", "Eaton Corporation", "Rockwell Automation",
    "ABB", "Siemens", "Schneider Electric",
    # Media / Telecom
    "AT&T", "Verizon", "T-Mobile", "Comcast", "Charter Communications",
    "Walt Disney", "NBCUniversal", "WarnerMedia", "Paramount",
    "News Corp", "Fox Corporation", "AMC Networks",
    "Spotify", "Pandora", "iHeartMedia",
    # Real Estate / Property Tech
    "CBRE Group", "Jones Lang LaSalle", "Cushman Wakefield",
    "CoStar Group", "RealPage", "Yardi Systems", "MRI Software",
    "Zillow", "Redfin", "Opendoor",
    # Staffing / HR
    "ManpowerGroup", "Robert Half", "Korn Ferry", "Spencer Stuart",
    "Heidrick Struggles", "Russell Reynolds", "Egon Zehnder",
    "Allegis Group", "Randstad", "Adecco", "Kelly Services",
    # Logistics / Supply Chain
    "UPS", "FedEx", "XPO Logistics", "CH Robinson", "Expeditors",
    "JB Hunt Transport", "Werner Enterprises", "Landstar System",
    "Ryder System", "GATX Corporation",
    # Aerospace / Defense
    "Lockheed Martin", "Raytheon Technologies", "Northrop Grumman",
    "General Dynamics", "L3Harris Technologies", "Textron",
    "Spirit AeroSystems", "TransDigm Group", "Heico Corporation",
    "Curtiss Wright", "DRS Technologies",
]


def _load_from_db(limit: int | None) -> list[str] | None:
    try:
        from sqlalchemy import text
        from database.connection import SessionLocal
        session = SessionLocal()
        rows = session.execute(text("SELECT company_name FROM public.sec_companies"))
        names = [r[0] for r in rows if r[0]]
        session.close()
        if limit:
            names = names[:limit]
        logger.info("Loaded {} company names from sec_companies DB", len(names))
        return names
    except Exception as e:
        logger.warning("DB unavailable: {} — using built-in list", e)
        return None


def _save_to_db(found: list) -> None:
    try:
        from database.connection import SessionLocal, upgrade_schema
        from scrapers.workday.database.repository import CompanyRepository
        upgrade_schema()
        session = SessionLocal()
        repo = CompanyRepository(session)
        new, updated = 0, 0
        known = repo.known_tenants()
        for company_name, tenant, wd_num, career_site, job_count in found:
            repo.save(company_name, tenant, wd_num, career_site, job_count)
            if tenant in known:
                updated += 1
            else:
                new += 1
        session.close()
        logger.info("DB saved → {} new  |  {} updated  |  {} total in workday_companies",
                    new, updated, new + updated)
    except Exception as e:
        logger.warning("DB save failed ({}). Results are still in the CSV.", e)


def main():
    parser = argparse.ArgumentParser(description="Workday brute-force discovery")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=40)
    parser.add_argument("--output", default="workday_discovered.csv")
    parser.add_argument("--no-db", action="store_true")
    parser.add_argument("--names-file", default=None,
                        help="Plain text file with one company name per line")
    args = parser.parse_args()

    # Load company names — priority: file > DB > built-in list
    names = None

    if args.names_file:
        path = Path(args.names_file)
        names = [l.strip() for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        if args.limit:
            names = names[:args.limit]
        logger.info("Loaded {} company names from {}", len(names), path)

    if names is None and not args.no_db:
        names = _load_from_db(args.limit)

    if names is None:
        names = COMPANY_NAMES
        if args.limit:
            names = names[:args.limit]
        logger.info("Using built-in list: {} companies", len(names))

    # Run discovery
    from scrapers.workday.scraper.discover import discover_companies
    logger.info("Starting discovery with concurrency={}...", args.concurrency)
    found = asyncio.run(discover_companies(names, concurrency=args.concurrency))

    if not found:
        logger.warning("No Workday boards found. Check internet connectivity.")
        return

    # Print results table
    logger.info("")
    logger.info("{:<35} {:<4}  {:<25} {:>8}",
                "COMPANY", "WD#", "CAREER SITE", "JOBS")
    logger.info("-" * 80)
    for company_name, tenant, wd_num, career_site, job_count in sorted(found, key=lambda x: -x[4]):
        logger.info("{:<35} wd{:<2}  {:<25} {:>8,}",
                    company_name[:35], wd_num, career_site[:25], job_count)

    # Save to CSV
    out = Path(args.output)
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["company_name", "tenant", "wd_num", "career_site", "job_count", "board_url"])
        for company_name, tenant, wd_num, career_site, job_count in sorted(found, key=lambda x: -x[4]):
            url = f"https://{tenant}.wd{wd_num}.myworkdayjobs.com/en-US/{career_site}"
            writer.writerow([company_name, tenant, wd_num, career_site, job_count, url])
    logger.info("CSV saved → {}", out.resolve())

    # Save to DB
    _save_to_db(found)


if __name__ == "__main__":
    main()
