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
from component_lister import ComponentLister

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
