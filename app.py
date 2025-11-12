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
    def __init__(self, base_url, token, company_id):
        self.base_url = self._prepare_base_url(base_url)
        self.headers = {
            "accept": "application/json, text/plain, */*",
            "authorization": token,
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
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
            return response.json()
        except Exception as e:
            st.error(f"Error fetching {endpoint}: {e}")
            return {"data": []}
    def fetch_single_exp_manager(self, limit):
        params = {
            "limit": limit,
            "page": 1,
            "sort": json.dumps({"updated_at": -1}),
            "filter": json.dumps(self._build_filter()),
        }
        resp = self._make_request(os.getenv("SINGLE_EXP_MANAGER_ENDPOINT", "v1/nocode/studio/form/fetch"), "GET", params=params)
        return resp.get("data", [])
    def fetch_multiple_exp_manager(self, limit):
        chunk_size = 10
        pages = limit // chunk_size + (1 if limit % chunk_size != 0 else 0)
        data = []
        endpoint = os.getenv("MULTIPLE_EXP_MANAGER_ENDPOINT", "v1/nocode/studio/multiple-form-ui/setup/fetch")
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
        endpoint = os.getenv("TABLEGROUP_ENDPOINT", "v1/nocode/data/tablegroup/fetch")
        json_data = {
            "limit": limit,
            "page": 1,
            "sort": json.dumps({"updated_at": -1}),
            "search": "",
        }
        resp = self._make_request(endpoint, "POST", json_data=json_data)
        return resp.get("data", [])
    def fetch_data_manager_by_tablegroup(self, tablegroup_id, limit):
        endpoint = os.getenv("DATA_MANAGER_ENDPOINT", "v1/nocode/data/fetch-by-table-groupID")
        json_data = {
            "tablegroup_id": tablegroup_id,
            "search": "",
        }
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
        endpoint = os.getenv("VISUAL_PROGRAMMING_ENDPOINT", "v1/nocode/studio/automation/fetch")
        resp = self._make_request(endpoint, "GET", params=params)
        return resp.get("data", [])

# Streamlit UI
st.title("Component Listing Tool")

with st.form("config_form"):
    base_url = st.text_input("Base URL", "https://studio.jojonomic.com/", placeholder="e.g., https://studio.jojonomic.com/")
    token = st.text_area("Auth Token", placeholder="Bearer ...")
    company_id = st.text_input("Company ID", placeholder="e.g., 27134")
    single_limit = st.number_input("Single Exp. Manager Limit", min_value=1, value=DEFAULT_SINGLE_EXP_MANAGER_LIMIT)
    multiple_limit = st.number_input("Multiple Exp. Manager Limit", min_value=1, value=DEFAULT_MULTIPLE_EXP_MANAGER_LIMIT)
    data_limit = st.number_input("Data Manager Limit", min_value=1, value=DEFAULT_DATA_MANAGER_LIMIT)
    vp_limit = st.number_input("Visual Programming Limit", min_value=1, value=DEFAULT_VISUAL_PROGRAMMING_LIMIT)
    start_date = st.date_input("Start Date", value=None)
    end_date = st.date_input("End Date", value=None)
    submitted = st.form_submit_button("List Components")

if submitted:
    # Validate required fields
    if not base_url or not token or not company_id:
        st.error("Base URL, Token, and Company ID are required.")
    else:
        safe_token = "".join(token.splitlines()).strip()
        lister = ComponentLister(base_url.strip(), safe_token, int(str(company_id).strip()))
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
