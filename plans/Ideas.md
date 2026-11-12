# Tech Trend Spotter System Ideas 

A system that scans and identifies for trends in software and technology and then shows them and provides business potential ideas for a software consultancy. 

E.g. Exploits in languages that have just been identified 

Essentially this would function as a tool in the same way quants and analysists identify investment
opportunities. Weird example: There is less rain in vietnam and therefore the price of a bean goes up and you need to go long on the company stock. 


## Functionality Ideas
- Scan websites and platforms like youtube (for titles and descriptions)
- Collectors on a schedule: Hacker News API, Reddit, Mastodon/infosec.exchange, GitHub Security Advisories, CISA KEV, NVD/OSV, and RSS from vendor and security blogs.
- Identify when something is a relevant trend (there needs to be matching criteria)
- Categorise the trend into dedicated sub-categories (each mapped to their own criteria and other things that then map to how to solve the issue)
- Formulate topics, discussion points etc for articles that the company can write in blog posts (essentially powering our social media and marketing)
- Display on dashboard which will allow for deeper diving on topics (linking to more available details on relevant technology and applications)


## Frontend Styling and Design Ideas
See graphic inspiration for the aesthetic that the frontend must have 

- Cyber/futuristic style 
- Graphical network linking trends and topics that connect or lead to each other 


## Open Questions 
- How will the system scan places? Are API keys needed or some kind of subscription (want to avoid costs like that)
- Can email alerts be set up for high-level things 
- How will categorisation be done (this still needs to be worked out)
- Is there any space for probability or making use of graphical models 


## Database 
- Use Postgresql database
- For local testing, can spin up one in a docker container and work off that. 
- Could use a docker container for local development (instead of an environment)


## Hosting and deployment
- Be able to run locally and deploy on railway


## Ideation and Commericial opportunity Pipeline

One of the major components should be identifying business opportunities including
- Potential clients/partnerships
- Solution and service opportunities
- Marketing opportunities

### Pipeline plan

```
collect → store → enrich → detect trends/categorise → match opportunities → dashboard / alerts
```

| Stage | What it does | Status |
|---|---|---|
| Collect | Pull raw items from configured sources into the standard schema | Initial version done (RSS, Hacker News) |
| Store | Persist items in Postgres, de-duplicated by `item_id`, so trends can be tracked over time | Not started |
| Enrich | Extract entities from each item: companies/vendors, products, technologies, CVE IDs | Not started |
| Detect & categorise | Spot growing topics (volume/engagement over time) and map them to sub-categories | Not started |
| Match opportunities | Compare trends against a services catalogue and produce Opportunity records | Not started |
| Present | Dashboard drill-down, and possibly email alerts for high-priority opportunities | Not started |

### Opportunity types and what they need

| Type | Signal | Key inputs |
|---|---|---|
| Potential clients/partnerships | Companies, vendors or products affected by, or involved in, a trend | Entity extraction; structured advisory sources (CISA KEV names the vendor and product; GitHub Advisories name affected packages and ecosystems) |
| Solution/service opportunities | A trend that matches something the consultancy can deliver | Services catalogue: a config file (like `sources.yaml`) listing offered services, the technologies behind them, and the problems they solve |
| Marketing opportunities | A trend worth writing about (blog posts, social media) | Trend summary plus an LLM step to draft topics and discussion points |

### Opportunity record (draft)
- `type`: client_partnership | service | marketing
- `title`, `summary`, `reasoning`: why this is an opportunity
- `evidence_item_ids`: the collected items it was based on, so every suggestion can be checked back to its sources
- `confidence`: how strong the signal is
- `related_entities`: companies, technologies or CVEs
- `created_at`

### Decisions and to-dos
- [ ] Add an `Advisory` item type to the collection schema (CVE ID, vendor, product, severity, ecosystem), alongside `WebArticle` and `SocialPost`. Do this **before** the storage schema is built.
- [ ] Collectors for CISA KEV, GitHub Security Advisories and OSV/NVD. These are the strongest sources for finding potential clients.
- [ ] Define the services catalogue format and fill it with the consultancy's offerings.
- [ ] Decide on the enrichment approach: LLM (Ollama, already in requirements), rules/keywords, or a mix.
- [ ] Look for clients at the level of companies only, never individuals. Keep stripping personal data, as already happens with HN usernames.
- [ ] Treat collected text as untrusted when passing it to the LLM: keep it clearly separated from instructions, as a guard against prompt injection. 