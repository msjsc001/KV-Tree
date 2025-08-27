import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import re
import os
import stat
import time
import threading
import sys
import queue
from PIL import Image
import pystray

try:
    import winreg
except ImportError:
    winreg = None

from app_logic.ast_parser import AstParser
from app_logic.logseq_parser import LogseqParser
from app_logic.config_manager import ConfigManager
from app_logic.file_monitor import FileMonitor
from app_logic.cache_manager import CacheManager

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class RulesWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent); self.title("自定义排除规则"); self.geometry("500x400"); self.transient(parent); self.grab_set()
        self.rules_text = tk.Text(self, wrap="word", font=("", 10)); self.rules_text.pack(expand=True, fill="both", padx=10, pady=5)
        button_frame = ttk.Frame(self); button_frame.pack(pady=5)
        ttk.Button(button_frame, text="保存", command=self.save_and_close).pack(side="left", padx=5)
        ttk.Button(button_frame, text="取消", command=self.destroy).pack(side="left", padx=5)
        self.saved_rules = None
    def show(self, initial_rules):
        self.rules_text.insert("1.0", initial_rules); self.wait_window(); return self.saved_rules
    def save_and_close(self):
        self.saved_rules = self.rules_text.get("1.0", "end-1c"); self.destroy()

class AdvancedOptionsWindow(tk.Toplevel):
    def __init__(self, parent, app_instance, options):
        super().__init__(parent)
        self.title("高级选项"); self.geometry("400x300"); self.transient(parent); self.grab_set()
        self.app = app_instance # Store app instance
        self.options = options
        self.scan_keys_var = tk.BooleanVar(value=options.get("logseq_scan_keys", False))
        self.scan_values_var = tk.BooleanVar(value=options.get("logseq_scan_values", False))
        self.run_on_startup_var = tk.BooleanVar(value=options.get("run_on_startup", False))
        self.minimize_to_tray_var = tk.BooleanVar(value=options.get("minimize_to_tray", True))
        notebook = ttk.Notebook(self); notebook.pack(padx=10, pady=10, fill="both", expand=True)
        common_frame = ttk.Frame(notebook); notebook.add(common_frame, text="常用")
        common_lf = ttk.LabelFrame(common_frame, text="常规设置", padding="10"); common_lf.pack(padx=10, pady=10, fill="x")
        ttk.Checkbutton(common_lf, text="系统启动时启动", variable=self.run_on_startup_var).pack(anchor="w", pady=2)
        ttk.Checkbutton(common_lf, text="最小化时在托盘 (默认勾选)", variable=self.minimize_to_tray_var).pack(anchor="w", pady=2)
        scan_frame = ttk.Frame(notebook); notebook.add(scan_frame, text="扫描")
        logseq_lf = ttk.LabelFrame(scan_frame, text="Logseq md属性扫描", padding="10"); logseq_lf.pack(padx=10, pady=10, fill="x")
        ttk.Checkbutton(logseq_lf, text="页头属性键录入为词条", variable=self.scan_keys_var).pack(anchor="w", pady=2)
        ttk.Checkbutton(logseq_lf, text="页头属性值录入为词条-带双方括号[[]]的", variable=self.scan_values_var).pack(anchor="w", pady=2)
        button_frame = ttk.Frame(self); button_frame.pack(pady=10)
        ttk.Button(button_frame, text="保存", command=self.save_and_close).pack(side="left", padx=5)
        ttk.Button(button_frame, text="取消", command=self.destroy).pack(side="left", padx=5)
        self.saved_options = None
    def save_and_close(self):
        self.saved_options = {"logseq_scan_keys": self.scan_keys_var.get(), "logseq_scan_values": self.scan_values_var.get(), "run_on_startup": self.run_on_startup_var.get(), "minimize_to_tray": self.minimize_to_tray_var.get()}; self.destroy()
    def show(self):
        self.wait_window(); return self.saved_options

class KvTreeApp(tk.Tk):
    VERSION = "0.8"

    def __init__(self):
        super().__init__()
        self.title(f"KVTree - {self.VERSION} (Polished)")
        self.geometry("800x600")

        self.parser = AstParser()
        self.logseq_parser = None
        self.config_manager = ConfigManager()
        self.cache_manager = CacheManager("parsing_cache.json")
        
        config = self.config_manager.load_config()
        self.source_files = config["source_files"]
        self.output_path = config["output_path"]
        self.rules = config["rules"]
        self.advanced_options = config["advanced_options"]
        self.output_selection = config["output_selection"]
        
        self.active_outputs = {}
        self.task_queue = queue.Queue()
        self.worker_thread = None

        self.auto_generate = tk.BooleanVar(value=True)
        self.file_monitor = FileMonitor(self)
        self.tray_icon = None
        
        style = ttk.Style(self); style.theme_use('clam')
        
        self.build_ui()
        self.load_state_to_ui()

        self.setup_tray_icon()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.bind("<Unmap>", self.on_minimize)

        self.start_worker_thread()
        self.task_queue.put(("initialize",))

        if self.auto_generate.get():
            self.toggle_mon()

    def on_g_tree_click(self, event):
        if self.g_tree.identify_region(event.x, event.y) != "cell": return
        column_id = self.g_tree.identify_column(event.x)
        if column_id != "#1": return
        item_id = self.g_tree.identify_row(event.y)
        if not item_id: return
        
        basename = os.path.basename(item_id)
        is_checked = self.output_selection.get(basename, True)
        self.output_selection[basename] = not is_checked
        
        # 无论勾选还是取消，都提交一个后台更新任务
        self.task_queue.put(("regenerate_output", item_id))
        self.update_generated_list()

    def build_ui(self):
        top_frame = ttk.Frame(self); top_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(5,0))
        ttk.Label(top_frame, text=f"Version: {self.VERSION}").pack(side=tk.LEFT)
        main_frame = ttk.Frame(self, padding="10"); main_frame.pack(fill=tk.BOTH, expand=True)
        s_frame = ttk.LabelFrame(main_frame, text="源文件", padding="10"); s_frame.pack(fill=tk.X, pady=5)
        self.s_tree = ttk.Treeview(s_frame, columns=("path", "status"), show="headings"); self.s_tree.heading("path", text="路径"); self.s_tree.heading("status", text="状态")
        self.s_tree.column("status", width=80, anchor='c'); self.s_tree.pack(fill=tk.X, expand=True)
        sf_btns = ttk.Frame(s_frame); sf_btns.pack(fill=tk.X, pady=5)
        ttk.Button(sf_btns, text="添加文件", command=self.add_files).pack(side=tk.LEFT, padx=5)
        ttk.Button(sf_btns, text="添加文件夹", command=self.add_folder).pack(side=tk.LEFT, padx=5)
        ttk.Button(sf_btns, text="启/禁", command=self.toggle_s).pack(side=tk.LEFT, padx=5)
        ttk.Button(sf_btns, text="移除", command=self.remove_s).pack(side=tk.LEFT, padx=5)
        right_btn_frame = ttk.Frame(sf_btns); right_btn_frame.pack(side=tk.RIGHT)
        ttk.Button(right_btn_frame, text="高级选项", command=self.edit_advanced_options).pack(side=tk.LEFT, padx=5)
        ttk.Button(right_btn_frame, text="自定义排除规则", command=self.edit_rules).pack(side=tk.LEFT, padx=5)
        o_frame = ttk.LabelFrame(main_frame, text="输出", padding="10"); o_frame.pack(fill=tk.X, pady=5)
        self.o_path_var = tk.StringVar(value=f"至: {self.output_path}"); ttk.Label(o_frame, textvariable=self.o_path_var).pack(side=tk.LEFT, padx=5)
        ttk.Button(o_frame, text="选择", command=self.select_o).pack(side=tk.LEFT, padx=5)
        a_frame = ttk.Frame(o_frame); a_frame.pack(side=tk.RIGHT, padx=10)
        ttk.Checkbutton(a_frame, text="自动", variable=self.auto_generate, command=self.toggle_mon).pack(side=tk.LEFT)
        ttk.Button(a_frame, text="!! 生成 !!", command=self.confirm_and_queue_rescan).pack(side=tk.LEFT, padx=5)
        g_frame = ttk.LabelFrame(main_frame, text="结果", padding="10"); g_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self.g_tree = ttk.Treeview(g_frame, columns=("output", "name", "source", "path"), show="headings")
        self.g_tree.heading("output", text="输出"); self.g_tree.heading("name", text="词库"); self.g_tree.heading("source", text="源条目"); self.g_tree.heading("path", text="完整路径")
        self.g_tree.column("output", width=40, anchor='c'); self.g_tree.column("source", width=200); self.g_tree.pack(fill=tk.BOTH, expand=True)
        self.g_tree.bind("<Button-1>", self.on_g_tree_click)
        self.progress_var = tk.DoubleVar(); self.progress_bar = ttk.Progressbar(self, variable=self.progress_var, maximum=100); self.progress_bar.pack(fill=tk.X, padx=10, pady=(0, 5))
        self.status_var = tk.StringVar(value="就绪"); ttk.Label(self, textvariable=self.status_var, relief=tk.SUNKEN).pack(side=tk.BOTTOM, fill=tk.X)

    def load_state_to_ui(self):
        self.o_path_var.set(f"至: {self.output_path}"); self.update_source_list(); self.update_generated_list()

    def edit_rules(self):
        new_rules = RulesWindow(self).show(self.rules);
        if new_rules is not None: self.rules = new_rules; self.set_status("排除规则已更新。")

    def edit_advanced_options(self):
        # Pass the app instance to the window
        new_options = AdvancedOptionsWindow(self, self, self.advanced_options).show()
        if new_options is not None:
            startup_changed = self.advanced_options.get("run_on_startup") != new_options.get("run_on_startup")
            self.advanced_options.update(new_options)
            if startup_changed: self.set_startup(new_options.get("run_on_startup"))
            self.set_status("高级选项已更新。")

    def on_closing(self, from_tray=False):
        if from_tray and self.advanced_options.get("minimize_to_tray", True): self.hide_to_tray(); return
        if self.tray_icon: self.tray_icon.stop()
        self.file_monitor.stop()
        self.task_queue.put(("exit",))
        if self.worker_thread and self.worker_thread.is_alive(): self.worker_thread.join()
        app_data = {"source_files": self.source_files, "output_path": self.output_path, "rules": self.rules, "advanced_options": self.advanced_options, "output_selection": self.output_selection}
        self.config_manager.save_config(app_data)
        self.cache_manager.save_cache()
        self.destroy()

    def update_generated_list(self):
        self.g_tree.delete(*self.g_tree.get_children())
        for f_path, source_path in sorted(self.active_outputs.items()):
            basename = os.path.basename(f_path)
            if basename not in self.output_selection: self.output_selection[basename] = True
            is_checked = self.output_selection.get(basename, True)
            check_char = "☑" if is_checked else "☐"
            display_source = source_path if len(source_path) < 50 else "..." + source_path[-47:]
            if display_source == "多元": display_source = "由多个源文件合成"
            self.g_tree.insert("", "end", iid=f_path, values=(check_char, basename, display_source, f_path))

    def update_source_list(self):
        self.s_tree.delete(*self.s_tree.get_children())
        for p, d in self.source_files.items():
            display_text = f"[{d.get('type', 'file').upper()}] {p}"
            self.s_tree.insert("", "end", iid=p, values=(display_text, "启用" if d.get("enabled") else "禁用"))

    def add_files(self):
        files = filedialog.askopenfilenames(title="选择一个或多个.md文件", filetypes=(("Markdown", "*.md"), ("All files", "*.*")))
        if not files: return
        for f in files:
            f_path = os.path.normpath(f)
            if f_path not in self.source_files: self.source_files[f_path] = {"enabled": True, "mtime": 0, "type": "file"}
        self.update_source_list(); self.set_status(f"已添加 {len(files)} 个文件。"); self.task_queue.put(("initialize",))

    def toggle_s(self):
        s = self.s_tree.focus();
        if s: self.source_files[s]["enabled"] = not self.source_files[s].get("enabled", False); self.update_source_list(); self.task_queue.put(("initialize",))

    def remove_s(self):
        selected_id = self.s_tree.focus()
        if not selected_id: return
        
        is_folder = self.source_files.get(selected_id, {}).get("type") == "folder"
        
        if messagebox.askyesno("确认移除", f"确定要移除 '{selected_id}' 吗？"):
            del self.source_files[selected_id]
            self.update_source_list()
            
            if is_folder:
                choice = messagebox.askquestion("清理选项", "您移除了一个文件夹，请选择清理方式：\n\n- 按“是”：快速清除全部缓存并重建 (推荐)。\n- 按“否”：在后台慢速清理此文件夹相关的词条。\n- 按“取消”：不执行任何清理。", type=messagebox.YESNOCANCEL)
                if choice == 'yes':
                    self.clear_cache_and_rebuild()
                elif choice == 'no':
                    self.task_queue.put(("initialize",)) # A full re-initialize is the safest way to clean up
                else: # cancel
                    self.set_status("已移除源，但未进行清理。建议手动重建缓存。")
            else: # 如果是单个文件，直接后台清理
                self.task_queue.put(("process_file", "deleted", selected_id))

            self.set_status(f"'{os.path.basename(selected_id)}' 已移除。")

    def select_o(self):
        p = filedialog.askdirectory();
        if p: self.output_path = p; self.o_path_var.set(f"至: {self.output_path}"); self.task_queue.put(("full_rescan",))

    def toggle_mon(self):
        if self.auto_generate.get():
            paths_to_watch = [path for path, data in self.source_files.items() if data.get("enabled")]
            if paths_to_watch: self.file_monitor.start(paths_to_watch)
            else: self.set_status("监控开启，但无启用的源可供监视。")
        else: self.file_monitor.stop()

    def set_status(self, msg): self.status_var.set(msg); self.update_idletasks()

    def set_startup(self, enable):
        if not winreg: messagebox.showwarning("功能受限", "此功能仅在Windows系统上受支持。"); return
        app_name = "KVTreeApp"; app_path = f'"{sys.executable}" "{os.path.abspath(__file__)}"' if 'python' in sys.executable.lower() else f'"{os.path.abspath(sys.executable)}"'
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as key:
                if enable: winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, app_path); self.set_status("已设置开机自启。")
                else:
                    try: winreg.DeleteValue(key, app_name); self.set_status("已取消开机自启。")
                    except FileNotFoundError: pass
        except Exception as e: messagebox.showerror("注册表操作失败", f"无法修改启动项: {e}")

    def setup_tray_icon(self):
        try: image = Image.open(resource_path("icon.ico"))
        except Exception as e: self.after(100, lambda: messagebox.showerror("图标错误", f"图标文件'icon.ico'加载失败: {e}")); return
        menu = (pystray.MenuItem("显示/隐藏", self.toggle_window, default=True), pystray.Menu.SEPARATOR, pystray.MenuItem("退出", self.on_closing_from_tray))
        self.tray_icon = pystray.Icon("kv_tree_app", image, f"KVTree {self.VERSION}", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def on_closing_from_tray(self): self.on_closing(from_tray=True)

    def toggle_window(self):
        if self.state() == "normal": self.withdraw()
        else: self.deiconify(); self.lift(); self.focus_force()

    def hide_to_tray(self):
        if self.advanced_options.get("minimize_to_tray", True): self.withdraw()
        else: self.on_closing()

    def on_minimize(self, event):
        if self.state() == 'iconic' and self.advanced_options.get("minimize_to_tray", True): self.after(10, self.withdraw)

    def queue_process_file(self, event_type, path): self.task_queue.put(("process_file", event_type, path))

    def add_folder(self):
        folder_path = filedialog.askdirectory(title="选择要扫描的文件夹")
        if folder_path: folder_path = os.path.normpath(folder_path)
        if folder_path in self.source_files: messagebox.showinfo("提示", "该文件夹已在源列表中。"); return
        self.task_queue.put(("scan_folder", folder_path))

    def start_worker_thread(self):
        self.worker_thread = threading.Thread(target=self.worker_main_loop, daemon=True); self.worker_thread.start()

    def worker_main_loop(self):
        while True:
            try:
                task = self.task_queue.get()
                task_name = task[0]
                if task_name == "exit": break
                elif task_name == "initialize": self._execute_initialize()
                elif task_name == "scan_folder": self._execute_scan_folder(task[1])
                elif task_name == "process_file": self._execute_process_file(task[1], task[2])
                elif task_name == "regenerate_output": self._execute_regenerate_output(task[1])
                elif task_name == "full_rescan": self._execute_full_rescan()
                elif task_name == "clear_cache": self._execute_clear_cache()
            except Exception as e: print(f"Worker thread error: {e}")
            finally: self.task_queue.task_done()
    
    def confirm_and_queue_rescan(self):
        if messagebox.askyesno("确认全量扫描", "这将重新扫描所有源文件并重建缓存。\n此操作可能需要较长时间，但期间UI可正常使用。\n确定要继续吗？"):
            self.task_queue.put(("full_rescan",))

    def clear_cache_and_rebuild(self):
        if messagebox.askyesno("确认清除缓存", "这将删除缓存文件并强制从头开始重建所有词库。\n确定吗？"):
            self.task_queue.put(("clear_cache",))

    def _execute_initialize(self):
        self.after(0, lambda: self.set_status("启动检查：正在校验缓存和文件...")); self.after(0, lambda: self.progress_bar.config(mode='determinate'))
        all_source_files = self._get_all_source_files(); dirty_outputs = set()
        cached_paths = self.cache_manager.get_all_cached_paths()
        total_files = len(all_source_files)
        
        for i, file_path in enumerate(all_source_files):
            self.after(0, lambda i=i, t=total_files, p=file_path: (self.set_status(f"校验中({i+1}/{t}): {os.path.basename(p)}"), self.progress_var.set((i+1)/t*100 if t > 0 else 0)))
            if not os.path.exists(file_path): continue
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
                self.after(0,lambda i=i,t=total_outputs, p=out_path: (self.set_status(f"更新输出({i+1}/{t}): {os.path.basename(p)}"), self.progress_var.set((i+1)/t*100 if t > 0 else 0)))
                self._update_single_output_file(out_path)
        
        self.active_outputs = {p: "多元" for src in self.cache_manager.get_all_cached_paths() for p in self.cache_manager.get_outputs_for_file(src)}
        self.cache_manager.save_cache()
        self.after(0, self.update_generated_list)
        self.after(0, lambda: (self.set_status("准备就绪。"), self.progress_var.set(0)))

    def _execute_scan_folder(self, folder_path):
        self.after(0, lambda: self.set_status(f"正在后台扫描: {folder_path}...")); self.after(0, lambda: self.progress_bar.config(mode='determinate'))
        scanned_files = {}
        try: all_files = [os.path.join(r, f) for r, _, fs in os.walk(folder_path) for f in fs if f.endswith('.md')]
        except Exception as e: print(f"Error scanning folder: {e}"); all_files = []
        
        total_scan = len(all_files)
        for i, file_path in enumerate(all_files):
            self.after(0, lambda i=i, t=total_scan, p=file_path: (self.set_status(f"扫描中 ({i+1}/{t}): {os.path.basename(p)}"), self.progress_var.set((i+1)/t*100 if t > 0 else 0)))
            try: scanned_files[file_path] = os.path.getmtime(file_path)
            except OSError: continue
        
        self.after(0, lambda: self.progress_var.set(0))
        self.after(0, lambda: self._show_scan_results_and_add(folder_path, scanned_files))

    def _execute_process_file(self, event_type, path):
        self.after(0, lambda: self.set_status(f"后台处理 {os.path.basename(path)}..."))
        old, new = self._update_cache_for_file(path, deleted=(event_type == 'deleted'))
        dirty = set(old.keys()) | set(new.keys())
        for out_path in dirty: self._update_single_output_file(out_path)
        self.cache_manager.save_cache()
        self.after(0, lambda: self.set_status(f"'{os.path.basename(path)}' 更新完成。"))

    def _execute_regenerate_output(self, output_path):
        self.after(0, lambda: self.set_status(f"后台更新: {os.path.basename(output_path)}..."))
        self._update_single_output_file(output_path)
        self.after(0, lambda: self.set_status(f"'{os.path.basename(output_path)}' 更新完成。"))

    def _execute_full_rescan(self):
        self.after(0, lambda: self.set_status("开始全量重建..."))
        self.cache_manager.cache_data.clear()
        self.active_outputs.clear()
        self.after(0, self.update_generated_list)
        self.task_queue.put(("initialize",))
    
    def _execute_clear_cache(self):
        self.after(0, lambda: self.set_status("正在清除缓存..."))
        try:
            if os.path.exists(self.cache_manager.cache_file):
                os.remove(self.cache_manager.cache_file)
            self.cache_manager.cache_data.clear()
            self.active_outputs.clear()
            self.after(0, self.update_generated_list)
            self.task_queue.put(("initialize",))
            self.after(0, lambda: self.set_status("缓存已清除，正在强制重建..."))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("错误", f"清除缓存失败: {e}"))

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
            res, _ = self.parser.parse(content, self.rules)
            for lib, entries in res.items(): outputs[os.path.join(self.output_path, lib)] = "\n".join(entries)
            if self.advanced_options.get("logseq_scan_keys") or self.advanced_options.get("logseq_scan_values"):
                if not self.logseq_parser: self.logseq_parser = LogseqParser(scan_keys=self.advanced_options.get("logseq_scan_keys", False), scan_values=self.advanced_options.get("logseq_scan_values", False))
                logseq_res = self.logseq_parser.parse_file_content(content)
                if logseq_res:
                    out_path = os.path.join(self.output_path, "Logseq属性键值.md")
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
            is_checked = self.output_selection.get(os.path.basename(output_path), True)
            if is_checked:
                if os.path.exists(output_path): os.chmod(output_path, stat.S_IWRITE)
                with open(output_path, "w", encoding="utf-8") as f: f.write(full_content)
                os.chmod(output_path, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
                if output_path not in self.active_outputs: self.after(0, lambda p=output_path: self.active_outputs.update({p: "多元"}))
            else:
                if os.path.exists(output_path):
                    os.chmod(output_path, stat.S_IWRITE)
                    os.remove(output_path)
                # 不再从 active_outputs 中移除
        except Exception as e: print(f"Error writing {output_path}: {e}")
        self.after(0, self.update_generated_list)
        
    def _get_all_source_files(self):
        paths = []
        for path, data in self.source_files.items():
            if not data.get("enabled"): continue
            if data.get("type") == "folder": paths.extend(data.get("files", {}).keys())
            else: paths.append(path)
        return paths
        
    def _show_scan_results_and_add(self, folder_path, scanned_files):
        """(UI线程) 显示扫描结果并确认是否添加。"""
        file_count = len(scanned_files)
        if file_count == 0:
            messagebox.showinfo("扫描完成", f"在 '{os.path.basename(folder_path)}' 中没有找到.md文件。"); self.set_status("就绪"); return
        
        msg = f"文件夹 '{os.path.basename(folder_path)}' 扫描完成。\n\n发现 {file_count} 个.md文件。\n\n是否要将其添加到源列表？"
        if messagebox.askyesno("确认添加", msg):
            self.source_files[folder_path] = {"enabled": True, "type": "folder", "files": scanned_files, "mtime": os.path.getmtime(folder_path)}
            self.update_source_list()
            self.task_queue.put(("initialize",))
            self.set_status(f"已添加文件夹: {folder_path}, 正在后台更新...")
        else:
            self.set_status("操作已取消。")

if __name__ == "__main__":
    app = KvTreeApp()
    app.mainloop()
