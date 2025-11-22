class DependencyAnalyst:
    # define prefix
    DM_PREFIX = "dm^"
    SINGLE_EXP_PREFIX = "single_exp^"
    MULTI_EXP_PREFIX = "multi_exp^"
    API_PREFIX = "api^"
    FUNCTION_PREFIX = "func^"
    JOB_PREFIX = "job^"
    DJOB_PREFIX = "djob^"

    def __init__(self, full_dm_data, full_single_exp_data, full_multi_exp_data, full_vp_data):
        """
        Initialize DependencyAnalyst by indexing full data (unfiltered) of each component to identify missing dependencies.

        Each component will have index with prefix based on its type:
        - Data Manager: dm^{id}
        - Single Exp. Manager: single_exp^{id}
        - Multiple Exp. Manager: multi_exp^{id}
        - API VP: api^{endpoint}
        - Function VP: func^{name}
        - Job VP: job^{name}
        - Dedicated Job VP: djob^{name}
        """
        # indexing components based on type for searching efficiency
        self.indexed_component_list = {}
        for dm in full_dm_data:
            key = self.DM_PREFIX + str(dm["id"])
            self.indexed_component_list[key] = dm
        for single_exp in full_single_exp_data:
            key = self.SINGLE_EXP_PREFIX + str(single_exp["id"])
            self.indexed_component_list[key] = single_exp
        for multi_exp in full_multi_exp_data:
            key = self.MULTI_EXP_PREFIX + str(multi_exp["id"])
            self.indexed_component_list[key] = multi_exp
        for vp in full_vp_data:
            # Defensive trigger parsing. Skip API triggers as targets (per design decision).
            trigger = vp.get("trigger") or {}
            ttype = trigger.get("type")
            key = None
            if ttype == "function":
                name = (trigger.get("function") or {}).get("name")
                if name:
                    key = self.FUNCTION_PREFIX + str(name)
            elif ttype == "job":
                name = (trigger.get("job") or {}).get("name")
                if name:
                    key = self.JOB_PREFIX + str(name)
            elif ttype == "dedicated_job":
                name = (trigger.get("dedicated_job") or {}).get("name")
                if name:
                    key = self.DJOB_PREFIX + str(name)
            # Note: we intentionally do NOT index API triggers (api_v2) as searchable targets.
            if key is not None:
                self.indexed_component_list[key] = vp

        # define array to store missing dependencies
        self.missing_dependencies = []

    def analyze_vp_dependencies(self, vp_data):
        for vp in vp_data:
            vp_dependencies = []
            vp_missing_dependencies = []
            vp_actions = vp.get("actions") or []
            for action in vp_actions:
                search_key = None
                a_type = action.get("type")
                # Functions and jobs (including dedicated jobs)
                if a_type == "function":
                    name = (action.get("function") or {}).get("name")
                    if name:
                        search_key = self.FUNCTION_PREFIX + str(name)
                elif a_type == "job":
                    name = (action.get("job") or {}).get("name")
                    if name:
                        search_key = self.JOB_PREFIX + str(name)
                elif a_type == "dedicated_job":
                    name = (action.get("dedicated_job") or {}).get("name")
                    if name:
                        search_key = self.DJOB_PREFIX + str(name)
                # Data manager related actions that reference a form_data_id
                elif a_type in ("find_record", "find_records", "create_record", "create_records", "update_record", "delete_record"):
                    fid = action.get("form_data_id")
                    if fid is not None:
                        search_key = self.DM_PREFIX + str(fid)
                # NOTE: per instruction, do NOT try to resolve API endpoints as target dependencies
                # (skip action types that call APIs)
                if search_key is not None:
                    search_component = self.indexed_component_list.get(search_key)
                    vp_dependencies.append(search_key)
                    if search_component is None:
                        vp_missing_dependencies.append(search_key)

            # storing dependency list
            self.missing_dependencies.append({
                "component_id": vp.get("id"),
                "component_name": vp.get("name"),
                "missing_dependencies": vp_missing_dependencies,
            })
            vp["vp_dependencies"] = vp_dependencies
            vp["vp_missing_dependencies"] = vp_missing_dependencies
        
        return vp_data
    
    def get_missing_dependencies(self):
        return self.missing_dependencies