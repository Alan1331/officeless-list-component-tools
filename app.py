import os
import io
import zipfile
import streamlit as st
import pandas as pd
import requests
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from urllib.parse import urljoin
from dotenv import load_dotenv

# Load default limits from .env
load_dotenv()
DEFAULT_SINGLE_EXP_MANAGER_LIMIT = int(os.getenv("SINGLE_EXP_MANAGER_LIMIT", 10000))
DEFAULT_MULTIPLE_EXP_MANAGER_LIMIT = int(os.getenv("MULTIPLE_EXP_MANAGER_LIMIT", 10000))
DEFAULT_DATA_MANAGER_LIMIT = int(os.getenv("DATA_MANAGER_LIMIT", 10000))
DEFAULT_VISUAL_PROGRAMMING_LIMIT = int(os.getenv("VISUAL_PROGRAMMING_LIMIT", 10000))


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

# Utility for timestamp conversion
INDO_TZ = datetime.now().astimezone().tzinfo

def convert_timestamp(ts):
    if not ts:
        return ""
    try:
        v = float(ts)
        if v > 1e12:
            v = v / 1000.0
        dt = datetime.fromtimestamp(v)
        return dt.strftime("%d-%m-%Y %H:%M:%S")
    except Exception:
        return ""

def filter_by_updated_at(items, start, end):
    if not start and not end:
        return items
    def to_seconds(ts):
        if ts is None:
            return None
        try:
            v = float(ts)
        except Exception:
            return None
        if v > 1e12:
            v = v / 1000.0
        return v
    start_s = to_seconds(start)
    end_s = to_seconds(end)
    filtered = []
    for it in items:
        ut = to_seconds(it.get("updated_at"))
        if ut is None:
            continue
        if start_s is not None and ut < start_s:
            continue
        if end_s is not None and ut > end_s:
            continue
        filtered.append(it)
    return filtered

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
            try:
                return response.json()
            except ValueError:
                st.error(f"Invalid JSON response from {endpoint}")
                return {"data": []}
        except requests.HTTPError as e:
            st.error(f"HTTP error fetching {endpoint}: {e} (status {getattr(e.response, 'status_code', 'N/A')})")
        except requests.RequestException as e:
            st.error(f"Network error fetching {endpoint}: {e}")
        except Exception as e:
            st.error(f"Unexpected error fetching {endpoint}: {e}")
        return {"data": []}

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

# Streamlit UI
st.title("Component Listing Tool")

with st.form("config_form"):
    base_url = st.text_input("Base URL", "https://studio.jojonomic.com/", placeholder="e.g., https://studio.jojonomic.com/")
    email = st.text_input("Email", placeholder="user@example.com")
    password = st.text_input("Password", type="password")
    single_limit = st.number_input("Single Exp. Manager Limit", min_value=1, value=DEFAULT_SINGLE_EXP_MANAGER_LIMIT)
    multiple_limit = st.number_input("Multiple Exp. Manager Limit", min_value=1, value=DEFAULT_MULTIPLE_EXP_MANAGER_LIMIT)
    data_limit = st.number_input("Data Manager Limit", min_value=1, value=DEFAULT_DATA_MANAGER_LIMIT)
    vp_limit = st.number_input("Visual Programming Limit", min_value=1, value=DEFAULT_VISUAL_PROGRAMMING_LIMIT)
    start_date = st.date_input("Start Date", value=None)
    end_date = st.date_input("End Date", value=None)
    submitted = st.form_submit_button("List Components")

if submitted:
    # Validate required fields
    if not base_url or not email or not password:
        st.error("Base URL, Email, and Password are required.")
    else:
        lister = ComponentLister(base_url.strip(), email.strip(), password)
        # Extract & convert date to timestamp
        if start_date is None:
            start_ts = 0
        else:
            start_ts = int(datetime.combine(start_date, datetime.min.time()).timestamp())

        if end_date is None:
            end_date = datetime.now().date()

        end_ts = int(datetime.combine(end_date, datetime.max.time()).timestamp())

        # Fetch components
        with st.spinner("Fetching Single Exp. Manager components..."):
            single_exp = lister.fetch_single_exp_manager(single_limit)
            single_exp = filter_by_updated_at(single_exp, start_ts, end_ts)
        st.success(f"Fetched {len(single_exp)} Single Exp. Manager components.")
        with st.spinner("Fetching Multiple Exp. Manager components..."):
            multiple_exp = lister.fetch_multiple_exp_manager(multiple_limit)
            multiple_exp = filter_by_updated_at(multiple_exp, start_ts, end_ts)
        st.success(f"Fetched {len(multiple_exp)} Multiple Exp. Manager components.")
        with st.spinner("Fetching Data Manager components..."):
            data_managers = lister.fetch_all_data_managers(data_limit)
            data_managers = filter_by_updated_at(data_managers, start_ts, end_ts)
        st.success(f"Fetched {len(data_managers)} Data Manager components.")
        with st.spinner("Fetching Visual Programming components..."):
            vp_exp = lister.fetch_visual_programming(vp_limit)
            vp_exp = filter_by_updated_at(vp_exp, start_ts, end_ts)
        st.success(f"Fetched {len(vp_exp)} Visual Programming components.")
        # Prepare CSVs
        def to_df(data):
            return pd.DataFrame([{k: convert_timestamp(v) if k in ("created_at", "updated_at") else v for k, v in item.items()} for item in data])[['id','name','created_at','updated_at']] if data else pd.DataFrame(columns=['id','name','created_at','updated_at'])
        files = {
            "single-exp-manager-list.csv": to_df(single_exp),
            "multiple-exp-manager-list.csv": to_df(multiple_exp),
            "dm-list.csv": to_df(data_managers),
            "vp-list.csv": to_df(vp_exp),
        }
        # Show download button for ZIP
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            for fname, df in files.items():
                zf.writestr(fname, df.to_csv(index=False))
        st.download_button(
            label="Download All CSVs as ZIP",
            data=zip_buffer.getvalue(),
            file_name="component_lists.zip",
            mime="application/zip"
        )
