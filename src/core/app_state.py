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
            return self._rules
            
    def set_rules(self, rules):
        with self._lock:
            self._rules = rules
            
    def get_advanced_options(self):
        with self._lock:
            return copy.deepcopy(self._advanced_options)
            
    def update_advanced_options(self, options):
        with self._lock:
            self._advanced_options.update(options)

    def get_output_selection(self):
        with self._lock:
            return copy.deepcopy(self._output_selection)

    def set_output_selection(self, basename, is_checked):
        with self._lock:
            self._output_selection[basename] = is_checked

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
            
    def get_serializable_config(self):
        with self._lock:
            return {
                "source_files": copy.deepcopy(self._source_files),
                "output_path": self._output_path,
                "rules": self._rules,
                "advanced_options": copy.deepcopy(self._advanced_options),
                "output_selection": copy.deepcopy(self._output_selection)
            }
