import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import re
import os
import stat
import time
import threading
import sys
# 托盘和图标相关
from PIL import Image
import pystray
# Windows注册表相关
try:
    import winreg
except ImportError:
    winreg = None # 在非Windows系统上提供一个占位符

from app_logic.ast_parser import AstParser
from app_logic.logseq_parser import LogseqParser
from app_logic.config_manager import ConfigManager
from app_logic.file_monitor import FileMonitor

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# ==============================================================================
# UI & 主应用
# ==============================================================================
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
    def __init__(self, parent, options):
        super().__init__(parent)
        self.title("高级选项")
        self.geometry("400x300")
        self.transient(parent)
        self.grab_set()

        self.options = options
        # 初始化所有选项的 tk.BooleanVar
        self.scan_keys_var = tk.BooleanVar(value=options.get("logseq_scan_keys", False))
        self.scan_values_var = tk.BooleanVar(value=options.get("logseq_scan_values", False))
        self.run_on_startup_var = tk.BooleanVar(value=options.get("run_on_startup", False))
        self.minimize_to_tray_var = tk.BooleanVar(value=options.get("minimize_to_tray", True))
        
        # 创建 Notebook (选项卡)
        notebook = ttk.Notebook(self)
        notebook.pack(padx=10, pady=10, fill="both", expand=True)

        # -- “常用” 选项卡 --
        common_frame = ttk.Frame(notebook)
        notebook.add(common_frame, text="常用")
        
        common_lf = ttk.LabelFrame(common_frame, text="常规设置", padding="10")
        common_lf.pack(padx=10, pady=10, fill="x")
        
        ttk.Checkbutton(common_lf, text="系统启动时启动", variable=self.run_on_startup_var).pack(anchor="w", pady=2)
        ttk.Checkbutton(common_lf, text="最小化时在托盘 (默认勾选)", variable=self.minimize_to_tray_var).pack(anchor="w", pady=2)

        # -- “扫描” 选项卡 --
        scan_frame = ttk.Frame(notebook)
        notebook.add(scan_frame, text="扫描")
        
        logseq_lf = ttk.LabelFrame(scan_frame, text="Logseq md属性扫描", padding="10")
        logseq_lf.pack(padx=10, pady=10, fill="x")
        
        ttk.Checkbutton(logseq_lf, text="页头属性键录入为词条", variable=self.scan_keys_var).pack(anchor="w", pady=2)
        ttk.Checkbutton(logseq_lf, text="页头属性值录入为词条-带双方括号[[]]的", variable=self.scan_values_var).pack(anchor="w", pady=2)

        # -- 保存/取消按钮 --
        button_frame = ttk.Frame(self)
        button_frame.pack(pady=10)
        ttk.Button(button_frame, text="保存", command=self.save_and_close).pack(side="left", padx=5)
        ttk.Button(button_frame, text="取消", command=self.destroy).pack(side="left", padx=5)

        self.saved_options = None

    def save_and_close(self):
        self.saved_options = {
            "logseq_scan_keys": self.scan_keys_var.get(),
            "logseq_scan_values": self.scan_values_var.get(),
            "run_on_startup": self.run_on_startup_var.get(),
            "minimize_to_tray": self.minimize_to_tray_var.get()
        }
        self.destroy()

    def show(self):
        self.wait_window()
        return self.saved_options

class KvTreeApp(tk.Tk):
    VERSION = "v0.5"

    def __init__(self):
        super().__init__()
        self.title(f"KVTree - {self.VERSION}")
        self.geometry("800x600")

        self.parser = AstParser()
        self.config_manager = ConfigManager()
        
        # 从ConfigManager加载配置并初始化应用状态
        config = self.config_manager.load_config()
        self.source_files = config["source_files"]
        self.output_path = config["output_path"]
        self.rules = config["rules"]
        self.generated_files = config["generated_files"]
        self.advanced_options = config["advanced_options"]
        self.output_selection = config["output_selection"] # 新增: 加载输出选择
        self.logseq_generated_data = {} # {source_file: [entry1, entry2]}

        self.auto_generate = tk.BooleanVar(value=True) # 默认开启自动模式
        self.stop_monitoring = threading.Event()
        self.file_monitor = FileMonitor(self, self.stop_monitoring)
        self.monitoring_thread = None
        self.tray_icon = None
        
        style = ttk.Style(self); style.theme_use('clam')
        
        self.build_ui()
        self.load_state_to_ui()

        # 初始化系统集成功能
        self.setup_tray_icon()
        self.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        self.bind("<Unmap>", self.on_minimize)

        if self.auto_generate.get():
            self.toggle_mon() # 如果是默认开启，则启动监控
            # 增加启动时自动生成
            self.after(200, lambda: self.proc_all(from_monitor=True))


    def on_g_tree_click(self, event):
        region = self.g_tree.identify_region(event.x, event.y)
        if region != "cell": return
        
        column_id = self.g_tree.identify_column(event.x)
        if column_id == "#1": # 只响应第一列“输出”的点击
            item_id = self.g_tree.identify_row(event.y)
            if not item_id: return
            
            basename = os.path.basename(item_id)
            is_checked = self.output_selection.get(basename, True)
            new_checked_state = not is_checked
            self.output_selection[basename] = new_checked_state
            
            # 如果取消勾选，立即删除文件
            if not new_checked_state:
                try:
                    if os.path.exists(item_id):
                        os.chmod(item_id, stat.S_IWRITE)
                        os.remove(item_id)
                        self.set_status(f"已删除: {basename}")
                except Exception as e:
                    messagebox.showerror("删除失败", f"删除文件 {basename} 失败: {e}")
            else:
                # 如果重新勾选，立即触发生成
                self.proc_all(from_monitor=True)

            self.update_generated_list() # 刷新UI以显示新的勾选状态

    def build_ui(self):
        # --- Top Frame for Version ---
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
        
        # 将高级选项按钮放在右侧
        right_btn_frame = ttk.Frame(sf_btns)
        right_btn_frame.pack(side=tk.RIGHT)
        ttk.Button(right_btn_frame, text="高级选项", command=self.edit_advanced_options).pack(side=tk.LEFT, padx=5)
        ttk.Button(right_btn_frame, text="自定义排除规则", command=self.edit_rules).pack(side=tk.LEFT, padx=5)

        o_frame = ttk.LabelFrame(main_frame, text="输出", padding="10"); o_frame.pack(fill=tk.X, pady=5)
        self.o_path_var = tk.StringVar(value=f"至: {self.output_path}")
        ttk.Label(o_frame, textvariable=self.o_path_var).pack(side=tk.LEFT, padx=5)
        ttk.Button(o_frame, text="选择", command=self.select_o).pack(side=tk.LEFT, padx=5)
        
        a_frame = ttk.Frame(o_frame); a_frame.pack(side=tk.RIGHT, padx=10)
        ttk.Checkbutton(a_frame, text="自动", variable=self.auto_generate, command=self.toggle_mon).pack(side=tk.LEFT)
        ttk.Button(a_frame, text="!! 生成 !!", command=lambda: self.proc_all()).pack(side=tk.LEFT, padx=5)
        
        g_frame = ttk.LabelFrame(main_frame, text="结果", padding="10"); g_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self.g_tree = ttk.Treeview(g_frame, columns=("output", "name", "source", "path"), show="headings")
        self.g_tree.heading("output", text="输出"); self.g_tree.heading("name", text="词库"); self.g_tree.heading("source", text="源条目"); self.g_tree.heading("path", text="完整路径")
        self.g_tree.column("output", width=40, anchor='c'); self.g_tree.column("source", width=200); self.g_tree.pack(fill=tk.BOTH, expand=True)
        self.g_tree.bind("<Button-1>", self.on_g_tree_click)
        
        # --- Progress Bar and Status ---
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(self, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, padx=10, pady=(0, 5))
        self.status_var = tk.StringVar(value="就绪"); ttk.Label(self, textvariable=self.status_var, relief=tk.SUNKEN).pack(side=tk.BOTTOM, fill=tk.X)

    def load_state_to_ui(self):
        self.o_path_var.set(f"至: {self.output_path}")
        self.update_source_list()
        self.update_generated_list()

    def edit_rules(self):
        rules_window = RulesWindow(self)
        new_rules = rules_window.show(self.rules)
        if new_rules is not None: self.rules = new_rules; self.set_status("排除规则已更新。")

    def edit_advanced_options(self):
        options_window = AdvancedOptionsWindow(self, self.advanced_options)
        new_options = options_window.show()
        if new_options is not None:
            # 检查是否有变更，特别是关于系统集成的选项
            startup_changed = self.advanced_options.get("run_on_startup") != new_options.get("run_on_startup")
            
            self.advanced_options.update(new_options)
            
            if startup_changed:
                self.set_startup(new_options.get("run_on_startup"))

            self.set_status("高级选项已更新。")

    def on_closing(self, from_tray=False):
        """彻底关闭应用的最终处理方法"""
        if self.tray_icon: self.tray_icon.stop()
        self.stop_monitoring.set()
        
        app_data = {
            "source_files": self.source_files,
            "output_path": self.output_path,
            "rules": self.rules,
            "generated_files": self.generated_files,
            "advanced_options": self.advanced_options,
            "output_selection": self.output_selection
        }
        self.config_manager.save_config(app_data)
        self.destroy()

    def get_all_files_to_process(self):
        files_to_process = {}
        for path, data in self.source_files.items():
            if not data.get("enabled") or not os.path.exists(path):
                continue
            if data.get("type") == "folder":
                for f_path in data.get("files", {}):
                    if os.path.exists(f_path): files_to_process[f_path] = path
            else:
                files_to_process[path] = path
        return files_to_process

    def proc_all(self, from_monitor=False):
        if not from_monitor: self.set_status("开始生成..."); self.progress_var.set(0)
        
        previous_gen_paths = set(self.generated_files.keys())
        all_files = self.get_all_files_to_process()
        total_files = len(all_files)
        current_generated_files = {}
        conflicts = 0
        processed_count = 0
        
        # --- Logseq扫描相关初始化 ---
        logseq_scan_enabled = self.advanced_options.get("logseq_scan_keys") or self.advanced_options.get("logseq_scan_values")
        self.logseq_generated_data.clear() # 每次重新生成时清空
        
        if logseq_scan_enabled:
            self.logseq_parser = LogseqParser(
                scan_keys=self.advanced_options.get("logseq_scan_keys", False),
                scan_values=self.advanced_options.get("logseq_scan_values", False)
            )

        for file_path, source_entry_path in all_files.items():
            try:
                with open(file_path, "r", encoding="utf-8") as f: content = f.read()
                
                # --- 原有解析逻辑 ---
                res, conf = self.parser.parse(content, self.rules)
                conflicts += len(conf)

                for lib, entries in res.items():
                    out_path = os.path.join(self.output_path, lib)
                    current_generated_files[out_path] = source_entry_path
                    # 检查是否勾选
                    if self.output_selection.get(os.path.basename(out_path), True):
                        if os.path.exists(out_path): os.chmod(out_path, stat.S_IWRITE)
                        with open(out_path, "w", encoding="utf-8") as f: f.write("\n".join(entries))
                        os.chmod(out_path, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)

                # --- 新的Logseq解析逻辑 ---
                if logseq_scan_enabled:
                    logseq_res = self.logseq_parser.parse_file_content(content)
                    if logseq_res:
                        self.logseq_generated_data[file_path] = logseq_res

            except Exception as e:
                error_msg = f"处理 {os.path.basename(file_path)} 时出错: {e}"
                if not from_monitor: messagebox.showerror("处理错误", error_msg)
                self.set_status(error_msg)
                
            processed_count += 1
            if not from_monitor and total_files > 0:
                progress = (processed_count / total_files) * 100
                self.progress_var.set(progress)
                self.set_status(f"正在处理: {os.path.basename(file_path)} ({processed_count}/{total_files})")
                self.update_idletasks()
        
        # --- 处理Logseq扫描结果 ---
        logseq_output_file = os.path.join(self.output_path, "Logseq属性键值.md")
        
        if logseq_scan_enabled and self.output_selection.get("Logseq属性键值.md", True):
            all_logseq_entries = set()
            for entries in self.logseq_generated_data.values():
                all_logseq_entries.update(entries)

            if all_logseq_entries:
                # 写入文件
                try:
                    if os.path.exists(logseq_output_file): os.chmod(logseq_output_file, stat.S_IWRITE)
                    with open(logseq_output_file, "w", encoding="utf-8") as f:
                        f.write("\n".join(sorted(list(all_logseq_entries))))
                    os.chmod(logseq_output_file, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
                    # 将其添加到生成文件列表中以便UI显示和清理
                    current_generated_files[logseq_output_file] = "Logseq Scan"
                except Exception as e:
                    messagebox.showerror("写入失败", f"写入Logseq词库失败: {e}")
        else:
            # 如果禁用了该功能，确保删除旧文件
            if os.path.exists(logseq_output_file):
                try:
                    os.chmod(logseq_output_file, stat.S_IWRITE)
                    os.remove(logseq_output_file)
                except Exception as e:
                    messagebox.showerror("删除失败", f"删除旧的Logseq词库失败: {e}")

        # --- 清理阶段 ---
        self.generated_files.update(current_generated_files)
        
        for f_path in previous_gen_paths - set(current_generated_files.keys()):
            if f_path in self.generated_files:
                del self.generated_files[f_path]
            basename = os.path.basename(f_path)
            if basename in self.output_selection:
                del self.output_selection[basename]
            try:
                if os.path.exists(f_path):
                    os.chmod(f_path, stat.S_IWRITE); os.remove(f_path)
            except Exception as e:
                if not from_monitor: messagebox.showerror("删除失败", f"删除旧词库失败 {f_path}: {e}")

        for f_path in self.generated_files.keys():
            basename = os.path.basename(f_path)
            if not self.output_selection.get(basename, True):
                try:
                    if os.path.exists(f_path):
                        os.chmod(f_path, stat.S_IWRITE); os.remove(f_path)
                except Exception as e:
                    if not from_monitor: messagebox.showerror("删除失败", f"删除未勾选文件失败: {f_path}: {e}")

        if not logseq_scan_enabled:
            logseq_output_file = os.path.join(self.output_path, "Logseq属性键值.md")
            if logseq_output_file in self.generated_files:
                del self.generated_files[logseq_output_file]
                if os.path.exists(logseq_output_file):
                    os.remove(logseq_output_file)

        self.update_generated_list()
        
        msg = f"完成！共处理 {processed_count} 个文件。" + (f" 发现 {conflicts} 冲突。" if conflicts else "")
        if not from_monitor:
            self.set_status(msg)
            if total_files > 0: self.progress_var.set(100)
        return True

    def update_generated_list(self):
        self.g_tree.delete(*self.g_tree.get_children())
        for f_path, source_path in sorted(self.generated_files.items()):
            basename = os.path.basename(f_path)
            
            if basename not in self.output_selection:
                self.output_selection[basename] = True
            
            is_checked = self.output_selection.get(basename, True)
            check_char = "☑" if is_checked else "☐"
            
            display_source = source_path
            if len(source_path) > 50: display_source = "..." + source_path[-47:]
            self.g_tree.insert("", "end", iid=f_path, values=(check_char, basename, display_source, f_path))


    def update_source_list(self):
        self.s_tree.delete(*self.s_tree.get_children())
        for p, d in self.source_files.items():
            item_type = d.get("type", "file")
            display_text = f"[{item_type.upper()}] {p}"
            self.s_tree.insert("", "end", iid=p, values=(display_text, "启用" if d.get("enabled") else "禁用"))

    def add_files(self):
        files = filedialog.askopenfilenames(title="选择一个或多个.md文件", filetypes=(("Markdown", "*.md"), ("All files", "*.*")))
        if not files: return
        for f in files:
            f_path = os.path.normpath(f)
            if f_path not in self.source_files:
                self.source_files[f_path] = {"enabled": True, "mtime": 0, "type": "file"}
        self.update_source_list(); self.set_status(f"已添加 {len(files)} 个文件。")

    def add_folder(self):
        folder_path = filedialog.askdirectory(title="选择要扫描的文件夹")
        if not folder_path: return
        folder_path = os.path.normpath(folder_path)
        if folder_path in self.source_files:
            messagebox.showinfo("提示", "该文件夹已在源列表中。"); return
        self.set_status(f"正在预扫描文件夹: {folder_path}..."); self.progress_bar.start()
        thread = threading.Thread(target=self.scan_folder_worker, args=(folder_path,), daemon=True)
        thread.start()

    def scan_folder_worker(self, folder_path):
        file_count, total_size, scanned_files = 0, 0, {}
        try:
            for root, _, files in os.walk(folder_path):
                for file in files:
                    if file.endswith('.md'):
                        file_path = os.path.normpath(os.path.join(root, file))
                        file_count += 1
                        try:
                            scanned_files[file_path] = os.path.getmtime(file_path)
                            total_size += os.path.getsize(file_path)
                        except OSError: continue
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("扫描错误", f"扫描文件夹时发生错误: {e}"))
            return
        finally:
            self.after(0, self.progress_bar.stop)
            self.after(0, self.show_scan_results, folder_path, file_count, total_size, scanned_files)

    def show_scan_results(self, folder_path, file_count, total_size, scanned_files):
        if file_count == 0:
            messagebox.showinfo("扫描完成", f"在 '{os.path.basename(folder_path)}' 中没有找到.md文件。")
            self.set_status("就绪"); return
        size_mb = total_size / (1024 * 1024)
        msg = f"文件夹 '{os.path.basename(folder_path)}' 扫描完成。\n\n发现 {file_count} 个 .md 文件\n总大小: {size_mb:.2f} MB\n\n是否要将其添加到源列表？"
        if messagebox.askyesno("确认添加", msg):
            self.source_files[folder_path] = {
                "enabled": True, "type": "folder", "files": scanned_files,
                "mtime": os.path.getmtime(folder_path)
            }
            self.update_source_list(); self.set_status(f"已添加文件夹: {folder_path}")
        else:
            self.set_status("操作已取消。")

    def toggle_s(self):
        s = self.s_tree.focus()
        if s: self.source_files[s]["enabled"] = not self.source_files[s].get("enabled", False); self.update_source_list()

    def remove_s(self):
        selected_id = self.s_tree.focus()
        if not selected_id: return
        if messagebox.askyesno("确认移除", f"确定要移除 '{selected_id}' 吗？\n\n注意：如果这是一个文件夹，所有由它生成的词库文件也将被删除。"):
            source_info = self.source_files.get(selected_id, {})
            files_in_source = source_info.get("files", {selected_id: 0}) 
            
            for f_path in files_in_source:
                if f_path in self.logseq_generated_data:
                    del self.logseq_generated_data[f_path]
            
            files_to_delete = []
            if source_info.get("type") == "folder":
                for gen_path, source_path in list(self.generated_files.items()):
                    if source_path == selected_id: files_to_delete.append(gen_path)
            
            for f_path in files_to_delete:
                try:
                    if os.path.exists(f_path):
                        os.chmod(f_path, stat.S_IWRITE); os.remove(f_path)
                    if f_path in self.generated_files: del self.generated_files[f_path]
                except Exception as e:
                    messagebox.showerror("删除失败", f"删除生成的词库 {f_path} 失败: {e}")

            del self.source_files[selected_id]
            self.proc_all(from_monitor=True) 
            self.update_source_list()
            self.update_generated_list()
            self.set_status(f"'{os.path.basename(selected_id)}' 已被移除。")

    def select_o(self):
        p = filedialog.askdirectory(); self.output_path = p if p else self.output_path; self.o_path_var.set(f"至: {self.output_path}")

    def toggle_mon(self):
        if self.auto_generate.get():
            self.stop_monitoring.clear()
            self.monitoring_thread = threading.Thread(target=self.file_monitor.file_monitor_worker, daemon=True)
            self.monitoring_thread.start()
            self.set_status("监控已开启。")
        else:
            self.stop_monitoring.set()
            self.monitoring_thread = None
            self.set_status("监控已关闭。")

    def set_status(self, msg):
        self.status_var.set(msg); self.update_idletasks()
        
    def run_tests(self):
        print("测试功能已被重构，请从独立的测试脚本运行。")

    def set_startup(self, enable):
        """设置或取消开机自启"""
        if not winreg:
            messagebox.showwarning("功能受限", "此功能仅在Windows系统上受支持。")
            return

        app_name = "KVTreeApp"
        app_path = os.path.abspath(sys.executable)
        
        if 'python.exe' in app_path.lower():
            script_path = os.path.abspath(__file__)
            app_path = f'"{sys.executable}" "{script_path}"'

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as key:
                if enable:
                    winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, app_path)
                    self.set_status("已设置开机自启。")
                else:
                    try:
                        winreg.DeleteValue(key, app_name)
                        self.set_status("已取消开机自启。")
                    except FileNotFoundError:
                        pass
        except PermissionError:
             messagebox.showerror("权限错误", "修改启动项失败，请尝试以管理员权限运行此程序。")
        except Exception as e:
            messagebox.showerror("注册表操作失败", f"无法修改启动项: {e}")

    # --- 托盘相关方法 ---
    def setup_tray_icon(self):
        """创建并配置系统托盘图标"""
        icon_path = resource_path("icon.ico")
        
        try:
            image = Image.open(icon_path)
        except Exception as e:
            self.after(100, lambda: messagebox.showerror("图标错误", f"图标文件 'icon.ico' 加载失败: {e}\n请确保它与程序或可执行文件位于同一目录，或在构建时已正确包含。"))
            return
        menu = (
            pystray.MenuItem("显示/隐藏", self.toggle_window, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", self.on_closing_from_tray)
        )
        self.tray_icon = pystray.Icon("kv_tree_app", image, f"KVTree {self.VERSION}", menu)
        
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def on_closing_from_tray(self):
        self.on_closing(from_tray=True)

    def toggle_window(self):
        """切换主窗口的显示和隐藏状态"""
        if self.state() == "normal":
            self.withdraw()
        else:
            self.deiconify()
            self.lift()
            self.focus_force()

    def hide_to_tray(self):
        """处理窗口关闭事件（X按钮）"""
        if self.advanced_options.get("minimize_to_tray", True):
            self.withdraw()
        else:
            self.on_closing()

    def on_minimize(self, event):
        """处理窗口最小化事件"""
        if self.state() == 'iconic' and self.advanced_options.get("minimize_to_tray", True):
            self.after(10, self.withdraw)

if __name__ == "__main__":
    app = KvTreeApp()
    app.mainloop()
