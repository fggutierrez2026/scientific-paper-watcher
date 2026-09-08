# External API access matrix

This document is the implementation gate for external scholarly and patent
sources. Revalidate the linked official documentation before implementing an
adapter: access terms, quotas, and available fields can change independently of
Scientific Paper Watcher.

## Status values

- **ready**: public access or credentials can currently be obtained through a
  documented registration flow.
- **credentials-required**: live use requires credentials, approval, or a
  subscription; development may continue against sanitized fixtures.
- **blocked**: the search capability is unavailable under the access granted to
  the project. A blocked source stays disabled and is never replaced by scraping.

Statuses describe access readiness, not adapter implementation status.

## Scholarly APIs

| Source | Endpoint and owner | Registration and access | License and quota | Pagination and time filters | Relevant fields | Status |
|---|---|---|---|---|---|---|
| [Semantic Scholar Academic Graph](https://api.semanticscholar.org/api-docs) | api.semanticscholar.org/graph/v1; Allen Institute for AI | An API key is optional for shared access and recommended for dedicated throughput. Send it only in the x-api-key header. | Follow the API license and rate limit assigned to the key; handle HTTP 429 and Retry-After. | Relevance search uses offset/limit; bulk search offers token pagination and more query syntax. Date support varies by endpoint. | Paper ID, DOI, PMID, arXiv ID, title, abstract, authors, venue, dates, citations, topics, OA PDF | **ready** |
| [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/) | api.crossref.org/works; Crossref | Public API. Supply a contact email through mailto and an identifiable User-Agent; Metadata Plus is optional. | Follow Crossref metadata guidance. Use the polite pool, cache responses, and respect backoff headers rather than assuming a fixed quota. | Use cursor pagination and the appropriate from-date/until-date filters for created, indexed, deposited, or updated windows. | DOI, title, authors, deposited abstract, dates, type, publisher, references, licenses, resource links | **ready** |
| [CORE API](https://core.ac.uk/services/api) | CORE API v3; The Open University | Register for an API key and send it as documented by CORE. | Quota and rights depend on granted access. Confirm metadata/full-text reuse and redistribution before enabling downloads. | Works search is paginated. Confirm current date filters; otherwise apply a documented local filter without advancing incomplete checkpoints. | CORE ID, DOI, repository, title, authors, abstract, dates, download/full-text links when permitted | **credentials-required** |
| [Unpaywall API](https://unpaywall.org/products/api) | api.unpaywall.org/v2; OurResearch | Every request requires a valid contact email. DOI lookup is primary; title search stays optional. | Cache DOI responses and follow Unpaywall reuse and service terms. | DOI lookup has no collection pagination. Revalidate title-search pagination and update fields before use. | DOI, OA status, genre, journal, license, version, host type, best OA location and PDF URL | **ready** |
| [The Lens API](https://docs.api.lens.org/) | api.lens.org; Cambia/The Lens | Request access and use the issued bearer token. Approval, renewal, or an organizational plan may be required. | Comply with granted export limits, attribution, and redistribution conditions. Do not enable until authorization is recorded. | Search is POST-based with result sizing and cursor/scroll behavior. Scholarly and patent endpoints differ. | Scholarly IDs, DOI/PMID, bibliographic metadata, citations, patent-citation links, patent and family data | **credentials-required** |

Unpaywall is an enrichment source by default: it must not create a new paper
solely because a DOI lookup succeeded.

## Patent APIs

| Source | Endpoint and owner | Registration and access | License and quota | Pagination and time filters | Relevant fields | Status |
|---|---|---|---|---|---|---|
| [USPTO PatentsView PatentSearch](https://search.patentsview.org/docs/docs/Search%20API/SearchAPIReference/) | PatentsView Search API; USPTO | An API key is required in X-Api-Key. Confirm key issuance and grants/pre-grants availability; also evaluate the USPTO Open Data Portal transition. | Current documentation specifies 45 requests per minute. Revalidate before release. | Use the API query, field, sort, pagination, and date-comparison syntax. Treat server result caps as truncation. | Publication/patent and application numbers, title, abstract/claims where available, inventors, assignees, dates, CPC/IPC, citations | **credentials-required** |
| [EPO Open Patent Services](https://www.epo.org/en/searching-for-patents/data/web-services/ops) | OPS REST/XML; European Patent Office | Register an application and obtain an OAuth consumer key and secret. Cache access tokens only in memory or an approved secret store. | The service has consumption controls and fair-use limits. Read current headers and terms instead of hard-coding quota assumptions. | Published-data search uses CQL and range parameters. Family and legal endpoints are separate capabilities. | Bibliographic data, abstracts, priorities, applicants, inventors, CPC/IPC, INPADOC family, authorized legal data | **credentials-required** |
| [WIPO PATENTSCOPE data services](https://www.wipo.int/en/web/patentscope/data/index) | PCT products and SOAP services; WIPO | Access is conditional. Obtain written confirmation that the contract permits record search, not only document download. | Products can carry fees and redistribution restrictions. Record the applicable contract before coding live requests. | SOAP operations and coverage depend on the granted service. Do not assume the interactive website's search exists in the API. | PCT publication/application numbers, languages, priorities, parties, classifications, abstracts and authorized documents | **credentials-required** until search access is confirmed; otherwise **blocked** |
| [The Lens Patent API](https://docs.api.lens.org/) | Patent endpoint within The Lens API; Cambia/The Lens | Uses the approved Lens token and patent entitlement. | The same plan-specific quotas, attribution, export, and redistribution restrictions apply. | POST search with selected fields and cursor/scroll; handle expiry and empty HTTP 204 responses. | Jurisdiction, publication/application numbers, family, parties, dates, CPC/IPC, patent and scholarly citations | **credentials-required** |

## Environment variables

Copy .env.example to .env and keep .env untracked. Empty values mean not
configured.

| Variable | Purpose | Sensitive |
|---|---|---|
| PAPER_SOURCES | Comma-separated enabled paper sources | No |
| PATENT_SOURCES | Comma-separated enabled patent sources | No |
| SEMANTIC_SCHOLAR_API_KEY | Optional Semantic Scholar key | Yes |
| CROSSREF_EMAIL | Crossref polite-pool contact | Private contact |
| CORE_API_KEY | CORE API key | Yes |
| UNPAYWALL_EMAIL | Required Unpaywall contact | Private contact |
| LENS_API_TOKEN | Lens bearer token shared by authorized scholarly/patent adapters | Yes |
| USPTO_API_KEY | PatentsView/USPTO key | Yes |
| EPO_CONSUMER_KEY | OPS OAuth consumer key | Yes |
| EPO_CONSUMER_SECRET | OPS OAuth consumer secret | Yes |
| WIPO_USERNAME | Contract-provided WIPO web-service identity | Yes |
| WIPO_PASSWORD | Contract-provided WIPO web-service secret | Yes |

The WIPO names are the project's internal configuration contract; map them to
the authentication mechanism specified in the access agreement.

## Source-selection policy

PAPER_SOURCES accepts this comma-separated set:

    pubmed,arxiv,biorxiv,medrxiv,openalex,semantic_scholar,crossref,core,unpaywall,lens

Its default is the currently implemented discovery set:

    pubmed,arxiv,biorxiv,medrxiv

PATENT_SOURCES accepts:

    uspto,epo,wipo,lens

It is empty by default until patent adapters are implemented. Hyphens normalize
to underscores, duplicate names are ignored, and unknown names fail fast.

Code activating an adapter must call
validate_source_access(config, source, kind). This gate:

1. rejects sources not selected for that document kind;
2. checks credentials only for a selected source;
3. identifies missing variable names and links to official registration help;
4. never includes credential values in an exception.

Public and optional-auth sources do not fail when their optional key is absent.
A missing credential for one restricted source is a source-level configuration
failure; orchestration work in phase 2.3 will isolate it from other sources.

## Secret-handling rules

- Never put credentials in URLs, commands, fixtures, logs, reports, or errors.
- Credential and private-contact fields are excluded from Config representations.
- Use synthetic values in tests and inspect staged changes before each commit.
- Do not commit .env; only blank placeholders belong in .env.example.
- Redact authorization headers and sensitive query parameters before logging HTTP.
