import threading
import copy

class AppState:
    """
    Centralized, thread-safe state store for the application (SSOT).
    Prevents Race Conditions and dict-changed-during-iteration crashes.
    """
    def __init__(self, config=None):
        self._lock = threading.Lock()
        
        config = config or {}
        self._source_files = config.get("source_files", {})
        self._output_path = config.get("output_path", "")
        self._rules = config.get("rules", "")
        self._advanced_options = config.get("advanced_options", {})
        self._output_selection = config.get("output_selection", {})
        self._blacklist = set(config.get("blacklist", []))
        self._logseq_exclude_keys = config.get("logseq_exclude_keys", [])
        self._window_geometry = config.get("window_geometry", "")
        
        self._active_outputs = {}
        
    def get_source_files(self):
        with self._lock:
            return copy.deepcopy(self._source_files)
            
    def update_source_file(self, path, data):
        with self._lock:
            self._source_files[path] = data
            
    def remove_source_file(self, path):
        with self._lock:
            if path in self._source_files:
                del self._source_files[path]
                
    def get_output_path(self):
        with self._lock:
            return self._output_path
            
    def set_output_path(self, path):
        with self._lock:
            self._output_path = path
            
    def get_rules(self):
        with self._lock:
            rules_data = self._rules
            
            # Migration 1: If string rules exist, convert
            if isinstance(rules_data, str):
                m_lines = []
                m_content = []
                for line in rules_data.split("\n"):
                    line = line.strip()
                    if line:
                        if r"\(\(" in line or "^" not in line:
                            m_content.append({"match": line, "replace": ""})
                        else:
                            m_lines.append({"match": line, "replace": ""})
                rules_data = {"line_rules": m_lines, "content_rules": m_content}
                self._rules = rules_data
                
            # Migration 2: If it's a list (from earlier iteration), roll it into line_rules
            elif isinstance(rules_data, list):
                rules_data = {"line_rules": rules_data, "content_rules": []}
                self._rules = rules_data
                
            # Migration 3: Ensure dict has required keys and clean legacy strings
            if isinstance(rules_data, dict):
                def _clean_rules(rule_list):
                    cleaned = []
                    for r in rule_list:
                        m = r.get("match", "").strip()
                        repl = r.get("replace", "")
                        if repl == "__KVT_DROP__":
                            repl = ""
                            
                        if not m or m.startswith(";") or (m.startswith("[") and m.endswith("]")):
                            continue
                            
                        # Strip legacy user prefixes like "替换内容_1 = "
                        if " = " in m:
                            prefix, value = m.split(" = ", 1)
                            if "排除" in prefix or "替换" in prefix:
                                m = value.strip()
                            
                        cleaned.append({"match": m, "replace": repl})
                    return cleaned

                rules_data["line_rules"] = _clean_rules(rules_data.get("line_rules", []))
                rules_data["content_rules"] = _clean_rules(rules_data.get("content_rules", []))
                self._rules = rules_data
                
            return rules_data
            
    def set_rules(self, rules_dict):
        with self._lock:
            self._rules = rules_dict
            
    def get_advanced_options(self):
        with self._lock:
            return copy.deepcopy(self._advanced_options)
            
    def update_advanced_options(self, options):
        with self._lock:
            self._advanced_options.update(options)

    def get_logseq_exclude_keys(self):
        with self._lock:
            return copy.deepcopy(self._logseq_exclude_keys)
            
    def set_logseq_exclude_keys(self, keys_list):
        with self._lock:
            self._logseq_exclude_keys = keys_list

    def get_output_selection(self):
        with self._lock:
            return copy.deepcopy(self._output_selection)

    def set_output_selection(self, basename, is_checked):
        with self._lock:
            self._output_selection[basename] = is_checked

    def get_blacklist(self):
        with self._lock:
            return copy.deepcopy(self._blacklist)
            
    def add_to_blacklist(self, basename):
        with self._lock:
            self._blacklist.add(basename)
            
    def remove_from_blacklist(self, basename):
        with self._lock:
            self._blacklist.discard(basename)

    def get_window_geometry(self):
        with self._lock:
            return self._window_geometry
            
    def set_window_geometry(self, geometry_str):
        with self._lock:
            self._window_geometry = geometry_str

    def get_active_outputs(self):
        with self._lock:
            return copy.deepcopy(self._active_outputs)
            
    def set_active_outputs(self, outputs):
        with self._lock:
            self._active_outputs = outputs
            
    def add_active_output(self, path, source):
        with self._lock:
            self._active_outputs[path] = source
            
    def clear_active_outputs(self):
        with self._lock:
            self._active_outputs.clear()
            
    def get_all_data(self):
        with self._lock:
            return {
                "source_files": copy.deepcopy(self._source_files),
                "output_path": self._output_path,
                "rules": copy.deepcopy(self._rules),
                "advanced_options": copy.deepcopy(self._advanced_options),
                "logseq_exclude_keys": list(self._logseq_exclude_keys),
                "output_selection": copy.deepcopy(self._output_selection),
                "blacklist": list(self._blacklist),
                "window_geometry": self._window_geometry
            }
