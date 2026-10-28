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