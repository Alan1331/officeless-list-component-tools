
# Component Listing Tool

A small Streamlit utility to list components from the low-code platform and export them as CSV files.

## What it does

- Connects to your studio/gateway API endpoints using a Bearer token.
- Fetches components for:
	- Single Experience Manager (forms)
	- Multiple Experience Manager (multi-form setups)
	- Data Managers (by table group)
	- Visual Programming (automations)
- Filters results by updated_at (client-side) when start/end dates are provided.
- Exports the results as CSV files and offers a ZIP download.

## Prerequisites

- Python 3.8+
- Install dependencies from `requirements.txt`:

```powershell
pip install -r requirements.txt
```

## Configuration

Copy `.env.example` to `.env` and update values as needed. Important variables:

- `BASE_URL`: base URL of the studio (default: `https://studio.jojonomic.com/`).
- Endpoint variables (usually no need to change):
	- `SINGLE_EXP_MANAGER_ENDPOINT`
	- `MULTIPLE_EXP_MANAGER_ENDPOINT`
	- `TABLEGROUP_ENDPOINT`
	- `DATA_MANAGER_ENDPOINT`
	- `VISUAL_PROGRAMMING_ENDPOINT`
- Limit settings (tweak to reduce fetch size and improve performance):
	- `SINGLE_EXP_MANAGER_LIMIT`
	- `MULTIPLE_EXP_MANAGER_LIMIT`
	- `TABLEGROUP_LIMIT`
	- `DATA_MANAGER_LIMIT`
	- `VISUAL_PROGRAMMING_LIMIT`

Example `.env` snippet:

```
BASE_URL = https://studio.jojonomic.com/
SINGLE_EXP_MANAGER_ENDPOINT = v1/nocode/studio/form/fetch
MULTIPLE_EXP_MANAGER_ENDPOINT = v1/nocode/studio/multiple-form-ui/setup/fetch
SINGLE_EXP_MANAGER_LIMIT = 10000
MULTIPLE_EXP_MANAGER_LIMIT = 1000
```

## Running the app

Start the Streamlit UI (PowerShell example):

```powershell
streamlit run app.py
```

Open the local address Streamlit prints (usually `http://localhost:8501`).

## Using the UI

Fill the form fields:

- Base URL: API base (auto-sanitized).
- Auth Token: full `Bearer ...` token.
- Company ID: numeric company identifier.
- Limits: number inputs to control how many records are fetched for each component type.
- Start / End Date: optional filters; when set, results returned by the API are filtered client-side by `updated_at`.

After submitting, the app fetches components and shows progress messages. When finished you can:

- Download a ZIP containing the CSV files for each component type.
- See counts for each category on the page.

CSV files are prepared with these columns: `id, name, created_at, updated_at` and are included in `component_lists.zip` when you click the download button.

## Output

The application does not automatically persist files to disk; it generates CSVs in-memory and offers a ZIP download. If you want file copies in a local `output/` folder, you can modify `app.py` to write DataFrames to disk using `df.to_csv("output/<name>.csv", index=False)`.

## Performance tips (why your page may feel laggy)

- Network/API latency: fetching thousands of records can take time. Lower the per-resource limits to speed up runs.
- Multiple sequential requests: the app requests endpoints sequentially. Increase concurrency (advanced) or reduce limits.
- Large responses: avoid converting or rendering huge DataFrames in the page. The app currently converts timestamps and constructs full DataFrames before zipping.
- Use caching: add `@st.cache_data` (Streamlit 1.18+) around functions that fetch or process data that doesn't change often.
- Pagination chunk size: `fetch_multiple_exp_manager` fetches pages in chunks—reduce the chunk size or limit pages to fetch fewer records.

## Troubleshooting

- "Error fetching ...": check the `Base URL`, token, and endpoints in `.env`. Ensure your token has correct permissions.
- Authentication: make sure the token string you paste includes the `Bearer ` prefix if required by your API.
- Timeouts: the app uses a 30s requests timeout. If your network is slow, consider increasing the timeout in `ComponentLister._make_request`.

## Notes & Next steps

- The tool currently performs `updated_at` filtering client-side because some endpoints don't support ranged filters. This is intentional.
- You can extend the code to persist CSVs to disk, parallelize fetches, or add retries/backoff for flaky networks.

## License

This repository contains example tooling — adapt it to your environment. No license file is provided here.
