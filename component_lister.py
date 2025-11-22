import os
import json
import requests
from urllib.parse import urljoin
import streamlit as st


def require_env(name: str) -> str:
    """Return the value of environment variable `name` or raise a RuntimeError with guidance.

    Endpoints are considered confidential and must be provided via the application's .env file.
    """
    val = os.getenv(name)
    if not val:
        raise RuntimeError(
            f"Required environment variable '{name}' is not set.\n"
            "Please add it to your .env file (do not commit .env to version control)."
        )
    return val


class ComponentLister:
    def __init__(self, base_url: str, email: str, password: str):
        """
        Initialize ComponentLister by logging in (to obtain a token) and fetching company_id.

        Raises RuntimeError on unrecoverable errors so caller can handle UI feedback.
        """
        self.base_url = self._prepare_base_url(base_url)
        self.session = requests.Session()

        # --- Login / obtain token ---
        login_endpoint = require_env("LOGIN_ENDPOINT")
        login_url = urljoin(self.base_url, login_endpoint)
        login_body = {"email": email, "password": password}

        try:
            resp = self.session.post(login_url, json=login_body, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            raise RuntimeError(f"Login request failed: {e}") from e

        try:
            login_json = resp.json()
        except ValueError as e:
            raise RuntimeError("Login response is not valid JSON") from e

        # Accept common token locations
        token = None
        if isinstance(login_json, dict):
            token = login_json.get("token")
            if not token and "data" in login_json and isinstance(login_json["data"], dict):
                token = login_json["data"].get("token") or login_json["data"].get("access_token")
            if not token:
                token = login_json.get("access_token")
        if not token:
            raise RuntimeError("Login succeeded but token was not found in the response")

        # Normalize token to include Bearer prefix if missing
        if not token.lower().startswith("bearer"):
            token = f"Bearer {token}"

        # Set default headers for subsequent requests
        self.headers = {
            "accept": "application/json, text/plain, */*",
            "authorization": token,
        }
        self.session.headers.update(self.headers)

        # --- Fetch company_id ---
        apps_endpoint = require_env("APPLICATION_PAGES_ENDPOINT")
        apps_url = urljoin(self.base_url, apps_endpoint)
        apps_params = {"page": 1, "limit": 1, "column": "updated_at", "sort": "desc"}

        try:
            apps_resp = self.session.get(apps_url, params=apps_params, timeout=30)
            apps_resp.raise_for_status()
        except requests.RequestException as e:
            raise RuntimeError(f"Failed to fetch application pages to determine company_id: {e}") from e

        try:
            apps_json = apps_resp.json()
        except ValueError as e:
            raise RuntimeError("Applications response is not valid JSON") from e

        # Extract company_id from common locations
        company_id = None
        if isinstance(apps_json, dict):
            data = apps_json.get("data") or apps_json.get("items") or apps_json.get("result")
            if isinstance(data, list) and len(data) > 0:
                first = data[0]
                if isinstance(first, dict):
                    company_id = first.get("company_id") or first.get("companyId") or first.get("company")
            # Some APIs return company_id at top level
            if not company_id:
                company_id = apps_json.get("company_id") or apps_json.get("companyId")

        if not company_id:
            raise RuntimeError("Unable to determine company_id from applications response")

        self.company_id = company_id

    def _prepare_base_url(self, url):
        url = url.rstrip("/")
        url = url.replace("studio", "gateway")
        return url + "/"

    def _build_filter(self):
        return {"company_id": self.company_id}

    def _make_request(self, endpoint, method="GET", params=None, json_data=None):
        url = urljoin(self.base_url, endpoint)
        try:
            if method == "GET":
                response = self.session.get(url, params=params, timeout=30)
            elif method == "POST":
                response = self.session.post(url, params=params, json=json_data, timeout=30)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            response.raise_for_status()
        except requests.HTTPError as e:
            # Raise errors to be handled by the UI layer
            raise RuntimeError(f"HTTP error fetching {endpoint}: {e} (status {getattr(e.response, 'status_code', 'N/A')})") from e
        except requests.RequestException as e:
            raise RuntimeError(f"Network error fetching {endpoint}: {e}") from e
        try:
            return response.json()
        except ValueError as e:
            raise RuntimeError(f"Invalid JSON response from {endpoint}") from e

    def fetch_single_exp_manager(self, limit):
        params = {
            "limit": limit,
            "page": 1,
            "sort": json.dumps({"updated_at": -1}),
            "filter": json.dumps(self._build_filter()),
        }
        endpoint = require_env("SINGLE_EXP_MANAGER_ENDPOINT")
        resp = self._make_request(endpoint, "GET", params=params)
        return resp.get("data", [])

    def fetch_multiple_exp_manager(self, limit):
        chunk_size = 10
        pages = limit // chunk_size + (1 if limit % chunk_size != 0 else 0)
        data = []
        endpoint = require_env("MULTIPLE_EXP_MANAGER_ENDPOINT")
        for page in range(1, pages + 1):
            params = {
                "limit": chunk_size,
                "page": page,
                "sort": json.dumps({"updated_at": -1}),
                "filter": json.dumps(self._build_filter()),
            }
            resp = self._make_request(endpoint, "GET", params=params)
            data.extend(resp.get("data", []))
        return data

    def fetch_tablegroups(self, limit):
        endpoint = require_env("TABLEGROUP_ENDPOINT")
        json_data = {
            "limit": limit,
            "page": 1,
            "sort": json.dumps({"updated_at": -1}),
            "search": "",
        }
        resp = self._make_request(endpoint, "POST", json_data=json_data)
        return resp.get("data", [])

    def fetch_data_manager_by_tablegroup(self, tablegroup_id, limit):
        endpoint = require_env("DATA_MANAGER_ENDPOINT")
        json_data = {"tablegroup_id": tablegroup_id, "search": ""}
        resp = self._make_request(endpoint, "POST", json_data=json_data)
        return resp.get("data", [])

    def fetch_all_data_managers(self, limit):
        tablegroups = self.fetch_tablegroups(limit)
        all_data_managers = []
        for tg in tablegroups:
            tg_id = tg.get("id")
            tg_name = tg.get("name")
            st.write(f"Fetching data managers for table group: {tg_name}")
            data_managers = self.fetch_data_manager_by_tablegroup(tg_id, limit)
            all_data_managers.extend(data_managers)
        return all_data_managers

    def fetch_visual_programming(self, limit):
        params = {
            "limit": limit,
            "page": 1,
            "sort": json.dumps({"updated_at": -1}),
            "filter": json.dumps(self._build_filter()),
        }
        endpoint = require_env("VISUAL_PROGRAMMING_ENDPOINT")
        resp = self._make_request(endpoint, "GET", params=params)
        return resp.get("data", [])
