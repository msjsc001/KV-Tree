import queue
import threading
import os
import stat
import time
from src.logic.ast_parser import AstParser
from src.logic.logseq_parser import LogseqParser
from src.utils.file_utils import atomic_write

class TaskDispatcher:
    def __init__(self, app_state, cache_manager, ui_callbacks):
        self.state = app_state
        self.cache_manager = cache_manager
        self.ui_cb = ui_callbacks # dict: set_status, update_progress, update_lists, prompt_confirm, etc
        
        self.parser = AstParser()
        self.logseq_parser = None
        
        self.task_queue = queue.Queue()
        self.worker_thread = None
        self.dirty_files = set()
        self.last_dirty_time = 0
        self.debounce_seconds = 2.0
        self.running = True
        
    def start(self):
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        
    def stop(self):
        self.running = False
        self.task_queue.put(("exit",))
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join()
            
    def put_task(self, task):
        self.task_queue.put(task)
        
    def _worker_loop(self):
        while self.running:
            try:
                # Wait with timeout to allow checking for debounced actions
                task = self.task_queue.get(timeout=0.5)
                task_name = task[0]
                
                if task_name == "exit": 
                    break
                elif task_name == "initialize": 
                    self._execute_initialize()
                elif task_name == "scan_folder": 
                    self._execute_scan_folder(task[1])
                elif task_name == "process_file": 
                    # Add to dirty set instead of immediate processing
                    self.dirty_files.add((task[1], task[2])) # (event_type, path)
                    self.last_dirty_time = time.time()
                elif task_name == "regenerate_output": 
                    self._execute_regenerate_output(task[1])
                elif task_name == "full_rescan": 
                    self._execute_full_rescan()
                elif task_name == "clear_cache": 
                    self._execute_clear_cache()
                
                self.task_queue.task_done()
            except queue.Empty:
                # Check dirty files for debounce
                if self.dirty_files and (time.time() - self.last_dirty_time) >= self.debounce_seconds:
                    self._process_dirty_batch()
            except Exception as e:
                print(f"Worker thread error: {e}")
                
    def _process_dirty_batch(self):
        batch = list(self.dirty_files)
        self.dirty_files.clear()
        
        self.ui_cb['set_status'](f"后台批量处理 {len(batch)} 个变动...")
        dirty_outputs = set()
        
        for event_type, path in batch:
            old, new = self._update_cache_for_file(path, deleted=(event_type == 'deleted'))
            dirty_outputs.update(old.keys())
            dirty_outputs.update(new.keys())
            
        for out_path in dirty_outputs:
            self._update_single_output_file(out_path)
            
        self.cache_manager.save_cache()
        self.ui_cb['update_lists']()
        self.ui_cb['set_status'](f"批量更新完成。")
        
    def _execute_initialize(self):
        self.ui_cb['set_status']("启动检查：正在校验缓存和文件...")
        self.ui_cb['update_progress'](mode='determinate', val=0)
        
        all_source_files = self._get_all_source_files()
        dirty_outputs = set()
        cached_paths = self.cache_manager.get_all_cached_paths()
        total_files = len(all_source_files)
        
        for i, file_path in enumerate(all_source_files):
            self.ui_cb['set_status'](f"校验中({i+1}/{total_files}): {os.path.basename(file_path)}")
            self.ui_cb['update_progress'](val=(i+1)/total_files*100 if total_files > 0 else 0)
            
            if not os.path.exists(file_path): 
                continue
            
            cached_entry = self.cache_manager.get_entry(file_path)
            current_mtime = os.path.getmtime(file_path)
            if not cached_entry or cached_entry.get("mtime") != current_mtime:
                old, new = self._update_cache_for_file(file_path)
                dirty_outputs.update(old.keys()); dirty_outputs.update(new.keys())
        
        for file_path in cached_paths:
            if file_path not in all_source_files:
                old, _ = self._update_cache_for_file(file_path, deleted=True)
                dirty_outputs.update(old.keys())

        if dirty_outputs:
            total_outputs = len(dirty_outputs)
            for i, out_path in enumerate(dirty_outputs):
                self.ui_cb['set_status'](f"更新输出({i+1}/{total_outputs}): {os.path.basename(out_path)}")
                self.ui_cb['update_progress'](val=(i+1)/total_outputs*100)
                self._update_single_output_file(out_path)
        
        # update actve outputs state
        outputs_map = {}
        for src in self.cache_manager.get_all_cached_paths():
            for p in self.cache_manager.get_outputs_for_file(src):
                outputs_map[p] = "多元"
        self.state.set_active_outputs(outputs_map)
        
        self.cache_manager.save_cache()
        self.ui_cb['update_lists']()
        self.ui_cb['set_status']("准备就绪。")
        self.ui_cb['update_progress'](val=0)

    def _execute_scan_folder(self, folder_path):
        self.ui_cb['set_status'](f"正在后台扫描: {folder_path}...")
        self.ui_cb['update_progress'](mode='determinate', val=0)
        scanned_files = {}
        try: all_files = [os.path.join(r, f) for r, _, fs in os.walk(folder_path) for f in fs if f.endswith('.md')]
        except Exception as e: print(f"Error scanning folder: {e}"); all_files = []
        
        total_scan = len(all_files)
        for i, file_path in enumerate(all_files):
            self.ui_cb['set_status'](f"扫描中 ({i+1}/{total_scan}): {os.path.basename(file_path)}")
            self.ui_cb['update_progress'](val=(i+1)/total_scan*100)
            try: scanned_files[file_path] = os.path.getmtime(file_path)
            except OSError: continue
        
        self.ui_cb['update_progress'](val=0)
        # Notify UI to ask user
        self.ui_cb['folder_scanned'](folder_path, scanned_files)

    def _execute_regenerate_output(self, output_path):
        self.ui_cb['set_status'](f"后台更新: {os.path.basename(output_path)}...")
        self._update_single_output_file(output_path)
        self.ui_cb['update_lists']()
        self.ui_cb['set_status'](f"'{os.path.basename(output_path)}' 更新完成。")

    def _execute_full_rescan(self):
        self.ui_cb['set_status']("开始全量重建...")
        self.cache_manager.cache_data.clear()
        self.state.clear_active_outputs()
        self.ui_cb['update_lists']()
        self._execute_initialize()
        
    def _execute_clear_cache(self):
        self.ui_cb['set_status']("正在清除缓存...")
        try:
            if os.path.exists(self.cache_manager.cache_file):
                os.remove(self.cache_manager.cache_file)
            self.cache_manager.cache_data.clear()
            self.state.clear_active_outputs()
            self.ui_cb['update_lists']()
            self.ui_cb['set_status']("缓存已清除，正在强制重建...")
            self._execute_initialize()
        except Exception as e:
            self.ui_cb['show_error']("清除缓存失败", str(e))

    def _update_cache_for_file(self, path, deleted=False):
        old = self.cache_manager.get_outputs_for_file(path)
        new = {}
        if deleted: self.cache_manager.remove_entry(path)
        else:
            if not os.path.exists(path): return old, new
            new = self._parse_single_file(path)
            self.cache_manager.update_entry(path, os.path.getmtime(path), new)
        return old, new

    def _parse_single_file(self, file_path):
        outputs = {}
        try:
            with open(file_path, "r", encoding="utf-8") as f: content = f.read()
            res, _ = self.parser.parse(content, self.state.get_rules())
            output_path_base = self.state.get_output_path()
            
            for lib, entries in res.items(): outputs[os.path.join(output_path_base, lib)] = "\n".join(entries)
            
            adv_opts = self.state.get_advanced_options()
            if adv_opts.get("logseq_scan_keys") or adv_opts.get("logseq_scan_values"):
                if not self.logseq_parser: self.logseq_parser = LogseqParser(scan_keys=adv_opts.get("logseq_scan_keys", False), scan_values=adv_opts.get("logseq_scan_values", False))
                # update parser config
                self.logseq_parser.scan_keys = adv_opts.get("logseq_scan_keys", False)
                self.logseq_parser.scan_values = adv_opts.get("logseq_scan_values", False)
                logseq_res = self.logseq_parser.parse_file_content(content)
                if logseq_res:
                    out_path = os.path.join(output_path_base, "Logseq属性键值.md")
                    existing = set(outputs.get(out_path, "").splitlines()); existing.update(logseq_res)
                    outputs[out_path] = "\n".join(sorted(list(existing)))
        except Exception as e: print(f"Error parsing {file_path}: {e}")
        return outputs

    def _update_single_output_file(self, output_path):
        all_lines = set()
        for src in self.cache_manager.get_all_cached_paths():
            outputs = self.cache_manager.get_outputs_for_file(src)
            if output_path in outputs and outputs[output_path]: all_lines.update(outputs[output_path].splitlines())
        
        full_content = "\n".join(sorted(list(all_lines)))
        try:
            # Check if this output is enabled using AppState lock mechanism
            selection = self.state.get_output_selection()
            is_checked = selection.get(os.path.basename(output_path), True)
            
            if is_checked:
                # Issue 4 Risk Mitigation: Atomic file saving to prevent corruption
                atomic_write(output_path, full_content)
                self.state.add_active_output(output_path, "多元")
            else:
                if os.path.exists(output_path):
                    os.chmod(output_path, stat.S_IWRITE)
                    os.remove(output_path)
        except Exception as e: print(f"Error writing {output_path}: {e}")

    def _get_all_source_files(self):
        paths = []
        sources = self.state.get_source_files()
        for path, data in sources.items():
            if not data.get("enabled"): continue
            if data.get("type") == "folder": paths.extend(data.get("files", {}).keys())
            else: paths.append(path)
        return paths
