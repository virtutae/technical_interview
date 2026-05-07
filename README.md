# Dentstock Price Comparison Tool

Full-stack price comparison tool that identifies identical and similar products across two dental supplier catalogues, to support procurement benchmarking. Data is loaded from two CSVs.

## Approach and Architecture

The project has two parts:

- **Backend** (Python / FastAPI) reads the two CSV catalogues, runs a two-pass matching algorithm, and exposes results via a single `GET /comparisons` endpoint.
- **Frontend** (React / TypeScript / Vite) fetches the comparison data and renders a summary dashboard with a sortable, filterable table.

The matching runs once at server startup and is served from memory, so requests are instant. For a static dataset of this size there's no point introducing a database or a cache.

### Project Structure

```
backend/
  app/
    main.py          # FastAPI app, /comparisons endpoint
    matcher.py       # Normalisation + two-pass matching engine
  tests/
    test_matcher.py  # 28 unit/integration tests
  requirements.txt
frontend/
  src/
    App.tsx          # Main UI component
    main.tsx         # React entry point
    index.css        # Styles
  vite.config.ts     # Dev server + API proxy
data/
  novadent_catalogue.csv
  primecare_catalogue.csv
```

## Matching Strategy

The algorithm is biased toward precision. In procurement, a false positive damages credibility in supplier negotiations because you'd be comparing prices on products that aren't actually the same. A false negative just gives a slightly less complete view, which is much easier to live with. So when in doubt, the matcher does not match.

### Pass 1: Identical Matches

Products are matched on normalised `manufacturer_code`. Normalisation handles real-world catalogue messiness:

1. Uppercase and trim
2. Replace letter O with zero in segments containing digits, to handle typos like `ND-SE-1OO` vs `ND-SE-100`
3. Strip leading zeros from numeric segments, so `050` matches `50`
4. Join segments without hyphens, so `DS-PTU-25-F1-3` matches `DS-PTU-25-F13`
5. Strip trailing single-letter suffixes, so `A2X` matches `A2`
6. Removes whitespaces at the start/end of a string for example a search for `A` would fetch the same results as `   A` or `A   `

### Pass 2: Similar Matches

For products not matched in Pass 1:

1. Candidates must be in the same category. Different categories never match, even with high name similarity.
2. `rapidfuzz.fuzz.token_set_ratio` computes a fuzzy similarity score on normalised descriptions. It splits both strings into tokens, ignores word order and duplicates, and scores overlap. So "Latex Gloves 100" and "100 Latex Gloves" score very high, which is useful when suppliers describe the same product in different word orders.
3. A size guardrail extracts size signals from each description (clothing sizes XS/M/L, fractional sizes like 5/6, ratios like 1:100000, percentages, mm lengths). If both products have sizes and they differ, the pair is rejected. This stops the matcher from linking Gracey curettes 5/6 with 7/8, or Articaine 1:100000 with 1:200000.
4. Threshold: score >= 85.

Each product matches at most once. Pass 2 only runs on products left over from Pass 1.

## Frontend Display and Search

All 200 products (100 per CSV) are rendered on the page. Search is token-based: the query is split into words and all of them must appear in the product's supplier ref, product description, or manufacturer code. Word order doesn't matter, so "ProTaper Universal 25mm" matches "ProTaper Universal Files 25mm Assorted F1-F3".

When a search hits a product that's been matched (identical or similar), its counterpart from the other supplier is automatically pulled into the results. So searching "ProTaper Universal 25mm" shows both the NovaDent and PrimeCare versions.

I chose those three search fields because they're the most identifying. Supplier or brand on their own return too many results to be useful. 


## Assumptions and Trade-offs

- **Static data.** Catalogues are loaded from CSV at startup. No database, no uploads, no scraping.
- **One-to-one matching.** Each product matches at most one counterpart. In reality a product in a catalogue might map to several variants from different other catalogues.
- **Greedy matching in Pass 2.** Similar matches are assigned greedily (first A product gets its best B match). An optimal assignment algorithm would be better but it works fine for this dataset.
- **Threshold of 85.** Worked well enough on the sample data. In production I'd tune this maybe per category or make it easily configurable.
- **Size guardrail is conservative.** If sizes can't be extracted from both descriptions, the match is allowed through. This means some false positives might slip through, but it avoids rejecting valid matches just because the extraction was incomplete. 
- **Client-side filtering.** Fine for 200 products, would need to move server-side at scale (see above). 
- **UI tiles** I have added some UI tiles to display some statistics from the 200 row dataset at a quick glance. For a production environment, these components would need to be changed to dynamically render content. Further discussion/feedback would be needed to understand what is actually useful. 

## Limitations

- No NLP or embeddings. Fuzzy string matching works for near-identical descriptions but can't catch semantically similar products described very differently.
- No pack-size normalisation. "box/100" vs "100 units" are treated as display strings, not compared structurally.
- No VAT-aware pricing. Price differences are computed on `unit_price_gbp` directly. Products with different VAT rates aren't adjusted to a common basis.
- No pagination. The full result set is returned in one response.
- Docker config provided but not tested locally. I didn't have Docker installed on the build machine.

## Future Work

Things I'd prioritise next:

- **Data ingestion.** Replace static CSVs with scheduled ingestion. Use official feeds (CSV, EDI, API) where suppliers offer them and/or fall back to scraping (Playwright or Scrapy) for the rest.
- **Server-side search and pagination.** Paginated endpoint, backend search (Postgres full-text or something like Meilisearch), and a Find button instead of live filtering.
- **Per-category thresholds and a review queue.** A single threshold of 85 is a compromise. Different categories have different description styles. I'd tune per category and route uncertain matches (score 80-90) to a human review queue.
- **Embeddings.** Sentence embeddings would catch semantic matches that token overlap misses (an example is "evacuation tips" vs "suction tips"). 

## How to Run locally 

### Prerequisites

- Python 3.12+ (tested on 3.14)
- Node.js 18+

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

API at http://localhost:8000. Swagger UI at http://localhost:8000/docs.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend at http://localhost:5173. It proxies `/comparisons` requests to the backend.

### Tests

```bash
cd backend
source .venv/bin/activate
pytest tests/ -v
```

### Docker Compose (not tested locally)

```bash
docker-compose up --build
```

Should start the backend on port 8000 and the frontend on port 5173.

## Out of Scope

Not implemented:

- Authentication and authorisation
- Database persistence
- Scraping infrastructure (if necessary)
- Testing (VRT - backstopJS)
- Embedding-based matching
- CI/CD pipeline
- Monitoring and alerting (Grafana)
- Pagination 
- An explicit Search button - with tens of thousands of products the current approach would be very costly and slow 
