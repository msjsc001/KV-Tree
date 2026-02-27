import threading
import copy

# 程序预置的 Logseq 系统属性排除键（精确匹配 + 前缀匹配用 * 结尾标记）
DEFAULT_LOGSEQ_EXCLUDE_KEYS = [
    # —— 精确匹配 ——
    # Logseq 核心系统属性
    "file", "file-path", "file-name", "id", "ls-type", "title",
    "alias", "aliases", "type", "Registry",
    # UI/渲染控制属性
    "collapsed", "background-color", "heading", "icon", "public", "direction",
    # 模板系统
    "template", "template-including-parent", "filters",
    # 时间戳
    "created-at", "updated-at", "logseq.order-list-type",
    # 任务状态关键词
    "todo", "doing", "done", "later", "now", "wait",
    # 闪卡系统
    "deck",
    # —— 前缀匹配（以 * 结尾表示匹配所有以此开头的键）——
    "card-*", "hl-*", "query-*", "col-*",
    "excalidraw-*", ".lsp-*", ".v-*"
]

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
        # 加载用户已有的排除键，并自动补全默认值（用户删除的不会被强制恢复）
        loaded_keys = config.get("logseq_exclude_keys", None)
        if loaded_keys is None or len(loaded_keys) == 0:
            self._logseq_exclude_keys = list(DEFAULT_LOGSEQ_EXCLUDE_KEYS)
        else:
            # 将用户未曾见过的新默认值自动合并进去
            user_deleted = set(config.get("_logseq_seen_defaults", []))
            merged = list(loaded_keys)
            for default_key in DEFAULT_LOGSEQ_EXCLUDE_KEYS:
                if default_key not in merged and default_key not in user_deleted:
                    merged.append(default_key)
            self._logseq_exclude_keys = merged
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
                "_logseq_seen_defaults": list(DEFAULT_LOGSEQ_EXCLUDE_KEYS),
                "output_selection": copy.deepcopy(self._output_selection),
                "blacklist": list(self._blacklist),
                "window_geometry": self._window_geometry
            }
