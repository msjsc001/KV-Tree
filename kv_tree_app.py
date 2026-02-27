import sys
import os
import shutil
import ctypes

# Ensure we can import from src
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.core.app_state import AppState
from src.core.task_dispatcher import TaskDispatcher
from src.logic.file_monitor import FileMonitor
from src.logic.cache_manager import CacheManager
from src.logic.config_manager import ConfigManager
from src.ui.main_window import KvTreeAppUI

def main():
    if sys.platform == "win32":
        try:
            myappid = f"msjsc001.kvtreeapp.kvt.1.2.0"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass

    # [Data Centralization] Ensure User Data folder exists
    data_dir = os.path.abspath("用户数据")
    os.makedirs(data_dir, exist_ok=True)
    
    # Migrate old files if they exist in root
    old_config = os.path.abspath("kv_tree_config.json")
    old_cache = os.path.abspath("parsing_cache.json")
    
    config_path = os.path.join(data_dir, "kv_tree_config.json")
    cache_path = os.path.join(data_dir, "parsing_cache.json")
    
    if os.path.exists(old_config) and not os.path.exists(config_path):
        try: shutil.move(old_config, config_path)
        except Exception as e: print(f"Failed to move config: {e}")
        
    if os.path.exists(old_cache) and not os.path.exists(cache_path):
        try: shutil.move(old_cache, cache_path)
        except Exception as e: print(f"Failed to move cache: {e}")
    
    # Initialize Managers
    config_manager = ConfigManager(config_path)
    cache_manager = CacheManager(cache_path)
    
    # Load Config into memory
    config_data = config_manager.load_config()
    
    # Setup App State (SSOT)
    app_state = AppState(config_data)
    
    # Setup Dispatcher (Logic Thread)
    task_dispatcher = TaskDispatcher(app_state, cache_manager, ui_callbacks={})
    
    # Setup File Monitor
    file_monitor = FileMonitor(task_dispatcher, app_state, ui_callbacks={})
    
    # Setup UI (Main Thread)
    app_ui = KvTreeAppUI(app_state, task_dispatcher, file_monitor)
    
    # Inject save logic to allow immediate persistence of states
    app_ui.trigger_save_cb = lambda: config_manager.save_config(app_state.get_all_data()) if not getattr(app_state, "skip_save", False) else None
    
    # Run UI
    try:
        app_ui.mainloop()
    finally:
        # Save final configs upon exiting the mainloop.
        # This guarantees data safety and decoupling
        if not getattr(app_state, "skip_save", False):
            final_config = app_state.get_all_data()
            config_manager.save_config(final_config)
            cache_manager.save_cache()

if __name__ == "__main__":
    main()
