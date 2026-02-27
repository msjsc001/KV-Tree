import queue
import threading
import os
import stat
import time
import concurrent.futures
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
        
        rules = self.state.get_rules()
        adv_opts = self.state.get_advanced_options()
        output_path_base = self.state.get_output_path()
        logseq_exclude_keys = self.state.get_logseq_exclude_keys()
        
        for event_type, path in batch:
            old, new = self._update_cache_for_file(path, deleted=(event_type == 'deleted'),
                                                    rules=rules, adv_opts=adv_opts,
                                                    output_path_base=output_path_base,
                                                    logseq_exclude_keys=logseq_exclude_keys)
            dirty_outputs.update(old.keys())
            dirty_outputs.update(new.keys())
            
        for out_path in dirty_outputs:
            self._update_single_output_file(out_path)
            
        self.cache_manager.save_cache()
        self.ui_cb['update_lists']()
        self.ui_cb['set_status'](f"批量更新完成。")
        
    def _execute_initialize(self):
        self.ui_cb['set_status']("极速启动：正在多线程校验缓存和解析文件...")
        self.ui_cb['update_progress'](mode='determinate', val=0)
        
        # 检查输出路径是否与缓存中的路径一致，如果不一致则强制重建
        current_output = self.state.get_output_path()
        cached_paths_list = self.cache_manager.get_all_cached_paths()
        if cached_paths_list:
            # 检查第一个缓存条目的输出路径是否包含当前 output_path
            sample_outputs = self.cache_manager.get_outputs_for_file(cached_paths_list[0])
            if sample_outputs:
                sample_key = next(iter(sample_outputs))
                # 如果当前输出路径为空或者缓存中的路径前缀不匹配，强制清除所有缓存的 mtime 以触发重建
                if (not current_output or current_output == os.getcwd()) or \
                   (current_output and not sample_key.startswith(current_output)):
                    for cp in cached_paths_list:
                        entry = self.cache_manager.get_entry(cp)
                        if entry:
                            entry['mtime'] = 0  # 强制使 mtime 失效，触发重新解析
                            self.cache_manager.update_entry(cp, 0, entry.get('outputs', {}))
        
        all_source_files = self._get_all_source_files()
        dirty_outputs = set()
        cached_paths = self.cache_manager.get_all_cached_paths()
        total_files = len(all_source_files)
        
        files_to_update = []
        
        # 1. Quick initial sync and filter
        for i, file_path in enumerate(all_source_files):
            if i % 100 == 0:
                self.ui_cb['set_status'](f"对比文件时间戳 ({i}/{total_files})...")
                self.ui_cb['update_progress'](val=(i/total_files*50) if total_files > 0 else 0)
            
            if not os.path.exists(file_path): 
                continue
            
            cached_entry = self.cache_manager.get_entry(file_path)
            current_mtime = os.path.getmtime(file_path)
            if not cached_entry or cached_entry.get("mtime") != current_mtime:
                files_to_update.append(file_path)
                
        # 2. Parallel Processing
        if files_to_update:
            total_updates = len(files_to_update)
            self.ui_cb['set_status'](f"启用多核并发引擎解析 {total_updates} 个变动文件...")
            
            rules = self.state.get_rules()
            adv_opts = self.state.get_advanced_options()
            output_path_base = self.state.get_output_path()
            logseq_exclude_keys = self.state.get_logseq_exclude_keys()

            completed = 0
            with concurrent.futures.ThreadPoolExecutor() as executor:
                # Map paths to future logic manually to handle cache manager locking
                tasks = [
                    executor.submit(
                        self._parse_single_file_stateless,
                        path, rules, adv_opts, output_path_base, logseq_exclude_keys
                    ) for path in files_to_update
                ]
                
                for future in concurrent.futures.as_completed(tasks):
                    path = files_to_update[tasks.index(future)] # Get original path from task list
                    try:
                        new_data = future.result()
                        # Synchronous cache update
                        old = self.cache_manager.get_outputs_for_file(path)
                        self.cache_manager.update_entry(path, os.path.getmtime(path), new_data)
                        dirty_outputs.update(old.keys())
                        dirty_outputs.update(new_data.keys())
                    except Exception as exc:
                        print(f'{path} generated an exception: {exc}')
                    
                    completed += 1
                    if completed % 50 == 0 or completed == total_updates:
                        self.ui_cb['set_status'](f"深度多核解析中 ({completed}/{total_updates})...")
                        self.ui_cb['update_progress'](val=50 + (completed/total_updates*40))
        
        self.ui_cb['set_status']("正在清理失效缓存...")
        for file_path in cached_paths:
            if file_path not in all_source_files:
                old = self.cache_manager.get_outputs_for_file(file_path)
                self.cache_manager.remove_entry(file_path)
                dirty_outputs.update(old.keys())

        if dirty_outputs:
            total_outputs = len(dirty_outputs)
            for i, out_path in enumerate(dirty_outputs):
                self.ui_cb['set_status'](f"更新输出({i+1}/{total_outputs}): {os.path.basename(out_path)}")
                self.ui_cb['update_progress'](val=(i+1)/total_outputs*100)
                self._update_single_output_file(out_path)
        
        # update active outputs state — 根据当前 output_path 过滤
        outputs_map = {}
        current_out = self.state.get_output_path()
        virtual_prefix = "<仅缓存,未设输出目录>"
        for src in self.cache_manager.get_all_cached_paths():
            for p in self.cache_manager.get_outputs_for_file(src):
                basename = os.path.basename(p)
                if not current_out or current_out == os.getcwd():
                    # 输出路径未设置，使用虚拟前缀展示
                    outputs_map[os.path.join(virtual_prefix, basename)] = "多元"
                elif p.startswith(current_out):
                    outputs_map[p] = "多元"
                else:
                    # 路径与当前输出不匹配，用当前路径重建显示
                    outputs_map[os.path.join(current_out, basename)] = "多元"
        self.state.set_active_outputs(outputs_map)
        
        self.cache_manager.save_cache()
        self.ui_cb['update_lists']()
        self.ui_cb['set_status']("准备就绪。")
        self.ui_cb['update_progress'](val=0)

    def _execute_scan_folder(self, folder_path):
        self.ui_cb['set_status'](f"正在后台扫描: {folder_path}...")
        self.ui_cb['update_progress'](mode='determinate', val=0)
        
        def _fast_scan_md_with_mtime(path):
            results = {}
            try:
                with os.scandir(path) as it:
                    for entry in it:
                        if entry.is_file() and entry.name.endswith('.md'):
                            try:
                                results[entry.path] = entry.stat().st_mtime
                            except OSError: pass
                        elif entry.is_dir():
                            results.update(_fast_scan_md_with_mtime(entry.path))
            except Exception: pass
            return results
            
        self.ui_cb['set_status'](f"正在建立极速索引: {folder_path}...")
        scanned_files = _fast_scan_md_with_mtime(folder_path)
        
        total_scan = len(scanned_files)
        # Dummy progress update since we already got all mtimes cleanly
        if total_scan > 0:
            self.ui_cb['update_progress'](val=100)
        else:
            self.ui_cb['update_progress'](val=0)
        
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

    def _update_cache_for_file(self, path, deleted=False, rules=None, adv_opts=None, output_path_base=None, logseq_exclude_keys=None):
        old = self.cache_manager.get_outputs_for_file(path)
        new = {}
        if deleted: self.cache_manager.remove_entry(path)
        else:
            if not os.path.exists(path): return old, new
            
            # If rules/options are not provided, fetch them from state (for non-batch updates)
            if rules is None: rules = self.state.get_rules()
            if adv_opts is None: adv_opts = self.state.get_advanced_options()
            if output_path_base is None: output_path_base = self.state.get_output_path()
            if logseq_exclude_keys is None: logseq_exclude_keys = self.state.get_logseq_exclude_keys()

            new = self._parse_single_file_stateless(path, rules, adv_opts, output_path_base, logseq_exclude_keys)
            self.cache_manager.update_entry(path, os.path.getmtime(path), new)
        return old, new

    @staticmethod
    def _parse_single_file_stateless(file_path: str, rules: list, adv_opts: dict, output_path_base: str, logseq_exclude_keys: set) -> dict:
        """
        Pure function for parsing a single file. Safe to run in a thread pool.
        """
        outputs = {}
        try:
            with open(file_path, "r", encoding="utf-8") as f: content = f.read()
            # Instantiate fresh parsers to avoid thread state corruption
            parser = AstParser()
            res, _ = parser.parse(content, rules=rules)
            
            for lib, entries in res.items(): outputs[os.path.join(output_path_base, lib)] = "\n".join(entries)
            
            if adv_opts.get("logseq_scan_keys") or adv_opts.get("logseq_scan_values") or adv_opts.get("logseq_scan_pure_values"):
                logseq_parser = LogseqParser(
                    scan_keys=adv_opts.get("logseq_scan_keys", False),
                    scan_values=adv_opts.get("logseq_scan_values", False),
                    scan_pure_values=adv_opts.get("logseq_scan_pure_values", False),
                    exclude_keys=logseq_exclude_keys
                )
                logseq_res = logseq_parser.parse_file_content(content)
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
            basename = os.path.basename(output_path)
            
            # Skip export if the output path is not set (empty or fallback CWD)
            base_dest = self.state.get_output_path()
            if not base_dest or base_dest == os.getcwd():
                self.state.add_active_output(os.path.join("<仅缓存,未设输出目录>", basename), "多元")
                return
                
            # Check the blacklist first! If blacklisted, block everything.
            blacklist = self.state.get_blacklist()
            if basename in blacklist:
                if os.path.exists(output_path):
                    try:
                        os.chmod(output_path, stat.S_IWRITE)
                        os.remove(output_path)
                    except Exception: pass
                # Still add it to active outputs so it shows up in UI (to be un-blacklisted later if needed)
                self.state.add_active_output(output_path, "多元")
                return

            # Check if this output is enabled using AppState lock mechanism
            selection = self.state.get_output_selection()
            is_checked = selection.get(basename, False)
            
            if is_checked:
                # Issue 4 Risk Mitigation: Atomic file saving to prevent corruption
                atomic_write(output_path, full_content)
                self.state.add_active_output(output_path, "多元")
            else:
                if os.path.exists(output_path):
                    try:
                        os.chmod(output_path, stat.S_IWRITE)
                        os.remove(output_path)
                    except Exception: pass
        except Exception as e: print(f"Error writing {output_path}: {e}")

    def _get_all_source_files(self):
        paths = []
        sources = self.state.get_source_files()
        for path, data in sources.items():
            if not data.get("enabled"): continue
            if data.get("type") == "folder": paths.extend(data.get("files", {}).keys())
            else: paths.append(path)
        return paths
