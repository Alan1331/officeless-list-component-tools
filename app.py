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
from dependency_analyst import DependencyAnalyst

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
    start_date = st.date_input("Start Date", value=None)
    end_date = st.date_input("End Date", value=None)
    submitted = st.form_submit_button("List Components")

if submitted:
    # Validate required fields
    if not base_url or not email or not password:
        st.error("Base URL, Email, and Password are required.")
    else:
        try:
            lister = ComponentLister(base_url.strip(), email.strip(), password)
        except Exception as e:
            st.error(f"Failed to initialize ComponentLister: {e}")
            st.stop()

        # Extract & convert date to timestamp
        if start_date is None:
            start_ts = 0
        else:
            start_ts = int(datetime.combine(start_date, datetime.min.time()).timestamp())

        if end_date is None:
            end_date = datetime.now().date()

        end_ts = int(datetime.combine(end_date, datetime.max.time()).timestamp())

        # Prepare full unfiltered data for dependency analysis
        full_single_exp = []
        full_multi_exp = []
        full_dm = []
        full_vp = []

        # Fetch components (wrapped to show errors cleanly)
        try:
            with st.spinner("Fetching Single Exp. Manager components..."):
                single_exp = lister.fetch_single_exp_manager(DEFAULT_SINGLE_EXP_MANAGER_LIMIT)
                full_single_exp = single_exp  # keep full data for dependency analysis
                single_exp = filter_by_updated_at(single_exp, start_ts, end_ts)
            st.success(f"Fetched {len(single_exp)} Single Exp. Manager components.")

            with st.spinner("Fetching Multiple Exp. Manager components..."):
                multiple_exp = lister.fetch_multiple_exp_manager(DEFAULT_MULTIPLE_EXP_MANAGER_LIMIT)
                full_multi_exp = multiple_exp  # keep full data for dependency analysis
                multiple_exp = filter_by_updated_at(multiple_exp, start_ts, end_ts)
            st.success(f"Fetched {len(multiple_exp)} Multiple Exp. Manager components.")

            with st.spinner("Fetching Data Manager components..."):
                data_managers = lister.fetch_all_data_managers(DEFAULT_DATA_MANAGER_LIMIT)
                full_dm = data_managers  # keep full data for dependency analysis
                data_managers = filter_by_updated_at(data_managers, start_ts, end_ts)
            st.success(f"Fetched {len(data_managers)} Data Manager components.")

            with st.spinner("Fetching Visual Programming components..."):
                vp_exp = lister.fetch_visual_programming(DEFAULT_VISUAL_PROGRAMMING_LIMIT)
                full_vp = vp_exp  # keep full data for dependency analysis
                vp_exp = filter_by_updated_at(vp_exp, start_ts, end_ts)
            st.success(f"Fetched {len(vp_exp)} Visual Programming components.")
        except Exception as e:
            st.error(f"Error while fetching components: {e}")
            st.stop()

        # Prepare CSVs
        def to_df(data):
            return pd.DataFrame([{k: convert_timestamp(v) if k in ("created_at", "updated_at") else v for k, v in item.items()} for item in data])[['id','name','created_at','updated_at']] if data else pd.DataFrame(columns=['id','name','created_at','updated_at'])
        # Enrich VP components with dependency analysis (uses unfiltered full lists as index)
        try:
            analyst = DependencyAnalyst(full_dm, full_single_exp, full_multi_exp, full_vp)
            enriched_vp = analyst.analyze_vp_dependencies(vp_exp)
        except Exception as e:
            # If dependency analysis fails, proceed without enrichment but show a warning
            st.warning(f"Dependency analysis failed: {e}")
            enriched_vp = vp_exp

        # Prepare CSV files; add Dependencies and Missing Dependencies columns for VPs
        vp_rows = []
        for v in enriched_vp:
            deps = v.get("vp_dependencies") or []
            missing = v.get("vp_missing_dependencies") or []
            vp_rows.append({
                "id": v.get("id"),
                "name": v.get("name"),
                "created_at": convert_timestamp(v.get("created_at")),
                "updated_at": convert_timestamp(v.get("updated_at")),
                "Dependencies": "\n".join(deps),
                "Missing Dependencies": "\n".join(missing),
            })

        files = {
            "single-exp-manager-list.csv": to_df(single_exp),
            "multiple-exp-manager-list.csv": to_df(multiple_exp),
            "dm-list.csv": to_df(data_managers),
            "vp-list.csv": pd.DataFrame(vp_rows),
            "missing-dependencies.csv": pd.DataFrame(analyst.get_missing_dependencies()),
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
