import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import re
from collections import defaultdict
import os
import json
import stat
import time
import threading
from ast_parser import AstParser # 导入新的解析器

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

class KvTreeApp(tk.Tk):
    VERSION = "v0.2"
    DEFAULT_RULES = """
[排除规则]
; 每行一个正则表达式，匹配到的整行内容都将被忽略
排除行_1 = ^\s*id::.*
排除行_2 = ^\s*collapsed::.*

[替换规则]
; 将匹配到的内容替换为空
替换内容_1 = \(\(.*?\)\)
""".strip()

    def __init__(self):
        super().__init__(); self.title(f"KVTree - {self.VERSION}"); self.geometry("800x600"); self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.parser = AstParser(); self.config_file = "kv_tree_config.json"; self.source_files = {}; self.output_path = os.getcwd(); self.rules = self.DEFAULT_RULES
        self.generated_files = {} # {gen_path: source_entry_path}
        self.auto_generate = tk.BooleanVar(value=False); self.monitoring_thread = None; self.stop_monitoring = threading.Event()
        style = ttk.Style(self); style.theme_use('clam')
        
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
        ttk.Button(sf_btns, text="自定义排除规则", command=self.edit_rules).pack(side=tk.RIGHT, padx=5)
        o_frame = ttk.LabelFrame(main_frame, text="输出", padding="10"); o_frame.pack(fill=tk.X, pady=5)
        self.o_path_var = tk.StringVar(value=f"至: {self.output_path}")
        ttk.Label(o_frame, textvariable=self.o_path_var).pack(side=tk.LEFT, padx=5)
        ttk.Button(o_frame, text="选择", command=self.select_o).pack(side=tk.LEFT, padx=5)
        a_frame = ttk.Frame(o_frame); a_frame.pack(side=tk.RIGHT, padx=10)
        ttk.Checkbutton(a_frame, text="自动", variable=self.auto_generate, command=self.toggle_mon).pack(side=tk.LEFT)
        ttk.Button(a_frame, text="!! 生成 !!", command=lambda: self.proc_all()).pack(side=tk.LEFT, padx=5)
        g_frame = ttk.LabelFrame(main_frame, text="结果", padding="10"); g_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self.g_tree = ttk.Treeview(g_frame, columns=("name", "source", "path"), show="headings")
        self.g_tree.heading("name", text="词库")
        self.g_tree.heading("source", text="源条目")
        self.g_tree.heading("path", text="完整路径")
        self.g_tree.column("source", width=200)
        self.g_tree.pack(fill=tk.BOTH, expand=True)
        
        # --- Progress Bar and Status ---
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(self, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, padx=10, pady=(0, 5))
        self.status_var = tk.StringVar(value="就绪"); ttk.Label(self, textvariable=self.status_var, relief=tk.SUNKEN).pack(side=tk.BOTTOM, fill=tk.X)
        self.load_config()
    def edit_rules(self):
        rules_window = RulesWindow(self)
        new_rules = rules_window.show(self.rules)
        if new_rules is not None: self.rules = new_rules; self.set_status("排除规则已更新。")
    def get_all_files_to_process(self):
        """收集所有启用的源文件，将文件夹展开。"""
        files_to_process = {} # {file_path: source_entry_path}
        for path, data in self.source_files.items():
            if not data.get("enabled") or not os.path.exists(path):
                continue
            
            if data.get("type") == "folder":
                # 对于文件夹，添加其包含的所有文件
                for f_path in data.get("files", {}):
                    if os.path.exists(f_path):
                        files_to_process[f_path] = path
            else:
                # 对于单个文件
                files_to_process[path] = path
        return files_to_process

    def proc_all(self, from_monitor=False):
        if not from_monitor:
            self.set_status("开始生成...")
            self.progress_var.set(0)

        all_files = self.get_all_files_to_process()
        total_files = len(all_files)
        current_generated_files = {} # {gen_path: source_entry_path}
        conflicts = 0
        processed_count = 0
        
        # 1. 解析所有文件并收集结果
        for file_path, source_entry_path in all_files.items():
            try:
                with open(file_path, "r", encoding="utf-8") as f: content = f.read()
                res, conf = self.parser.parse(content, self.rules)
                conflicts += len(conf)

                for lib, entries in res.items():
                    out_path = os.path.join(self.output_path, lib)
                    current_generated_files[out_path] = source_entry_path
                    if os.path.exists(out_path): os.chmod(out_path, stat.S_IWRITE)
                    with open(out_path, "w", encoding="utf-8") as f: f.write("\n".join(entries))
                    os.chmod(out_path, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
            
            except Exception as e:
                error_msg = f"处理 {os.path.basename(file_path)} 时出错: {e}"
                if not from_monitor: messagebox.showerror("处理错误", error_msg)
                self.set_status(error_msg)
                
            processed_count += 1
            if not from_monitor and total_files > 0:
                progress = (processed_count / total_files) * 100
                self.progress_var.set(progress)
                self.set_status(f"正在处理: {os.path.basename(file_path)} ({processed_count}/{total_files})")
                self.update_idletasks() # 强制更新UI

        # 2. 清理不再需要的旧文件
        old_gen_paths = set(self.generated_files.keys())
        new_gen_paths = set(current_generated_files.keys())
        files_to_delete = old_gen_paths - new_gen_paths
        
        for f_path in files_to_delete:
            try:
                if os.path.exists(f_path):
                    os.chmod(f_path, stat.S_IWRITE)
                    os.remove(f_path)
            except Exception as e:
                if not from_monitor: messagebox.showerror("删除失败", f"删除旧词库失败 {f_path}: {e}")

        # 3. 更新UI和状态
        self.generated_files = current_generated_files
        self.update_generated_list()
        
        msg = f"完成！共处理 {processed_count} 个文件。" + (f" 发现 {conflicts} 冲突。" if conflicts else "")
        if not from_monitor:
            self.set_status(msg)
            if total_files > 0:
              self.progress_var.set(100)
        return True

    def update_generated_list(self):
        """更新UI中的生成文件列表，并显示其来源。"""
        self.g_tree.delete(*self.g_tree.get_children())
        for f_path, source_path in sorted(self.generated_files.items()):
            display_source = source_path
            # 如果源路径太长，截断它以便显示
            if len(source_path) > 50:
                display_source = "..." + source_path[-47:]
            self.g_tree.insert("", "end", values=(os.path.basename(f_path), display_source, f_path))

    def save_config(self):
        config = {
            "source_files": self.source_files,
            "output_path": self.output_path,
            "rules": self.rules,
            "generated_files": self.generated_files
        }
        with open(self.config_file, "w", encoding="utf-8") as f: json.dump(config, f, indent=4)
    def load_config(self):
        try:
            with open(self.config_file, "r", encoding="utf-8") as f: config = json.load(f)
            # 加载并升级旧配置
            loaded_sources = config.get("source_files", {})
            for path, data in loaded_sources.items():
                if "type" not in data: 
                    data["type"] = "file"
                if data["type"] == "folder" and "files" not in data:
                    data["files"] = {} # 为旧的文件夹条目添加files字典
            self.source_files = loaded_sources
            
            self.output_path = config.get("output_path", os.getcwd())
            loaded_gen_files = config.get("generated_files", {})
            # 兼容性处理：如果旧配置是列表，则转换为字典
            if isinstance(loaded_gen_files, list):
                self.generated_files = {path: "N/A" for path in loaded_gen_files}
            else:
                self.generated_files = loaded_gen_files
            
            # 加载规则，如果为空则使用默认规则
            self.rules = config.get("rules", self.DEFAULT_RULES)
            if not self.rules.strip():
                self.rules = self.DEFAULT_RULES
            
            self.o_path_var.set(f"至: {self.output_path}");
            self.update_source_list()
            self.update_generated_list()
        except (FileNotFoundError, json.JSONDecodeError):
            # 如果配置文件不存在或无效，确保使用默认规则
            self.rules = self.DEFAULT_RULES
    def update_source_list(self):
        self.s_tree.delete(*self.s_tree.get_children())
        for p, d in self.source_files.items():
            item_type = d.get("type", "file") # 默认为 file 以兼容旧配置
            display_text = f"[{item_type.upper()}] {p}"
            self.s_tree.insert("", "end", iid=p, values=(display_text, "启用" if d.get("enabled") else "禁用"))
    def add_files(self):
        """添加单个或多个.md文件。"""
        files = filedialog.askopenfilenames(title="选择一个或多个.md文件", filetypes=(("Markdown", "*.md"), ("All files", "*.*")))
        if not files: return
        
        for f in files:
            # 标准化路径，并确保使用正斜杠
            f_path = os.path.normpath(f)
            if f_path not in self.source_files:
                self.source_files[f_path] = {"enabled": True, "mtime": 0, "type": "file"}
        
        self.update_source_list()
        self.set_status(f"已添加 {len(files)} 个文件。")

    def add_folder(self):
        """添加一个文件夹，并启动后台预扫描。"""
        folder_path = filedialog.askdirectory(title="选择要扫描的文件夹")
        if not folder_path:
            return

        folder_path = os.path.normpath(folder_path)
        if folder_path in self.source_files:
            messagebox.showinfo("提示", "该文件夹已在源列表中。")
            return

        self.set_status(f"正在预扫描文件夹: {folder_path}...")
        self.progress_bar.start()
        
        # 使用后台线程进行扫描，避免UI冻结
        thread = threading.Thread(target=self.scan_folder_worker, args=(folder_path,), daemon=True)
        thread.start()

    def scan_folder_worker(self, folder_path):
        """在后台线程中扫描文件夹以查找.md文件。"""
        file_count = 0
        total_size = 0
        scanned_files = {} # {path: mtime}

        try:
            for root, _, files in os.walk(folder_path):
                for file in files:
                    if file.endswith('.md'):
                        file_path = os.path.normpath(os.path.join(root, file))
                        file_count += 1
                        try:
                            file_size = os.path.getsize(file_path)
                            total_size += file_size
                            scanned_files[file_path] = os.path.getmtime(file_path)
                        except OSError:
                            continue # 忽略无法访问的文件
        except Exception as e:
            # 在主线程中显示错误
            self.after(0, lambda: messagebox.showerror("扫描错误", f"扫描文件夹时发生错误: {e}"))
            return
        finally:
            # 确保在主线程中停止进度条并更新UI
            self.after(0, self.progress_bar.stop)
            self.after(0, self.show_scan_results, folder_path, file_count, total_size, scanned_files)

    def show_scan_results(self, folder_path, file_count, total_size, scanned_files):
        """在主线程中显示扫描结果并请求用户确认。"""
        if file_count == 0:
            messagebox.showinfo("扫描完成", f"在 '{os.path.basename(folder_path)}' 中没有找到.md文件。")
            self.set_status("就绪")
            return

        size_mb = total_size / (1024 * 1024)
        msg = f"""
文件夹 '{os.path.basename(folder_path)}' 扫描完成。

发现 {file_count} 个 .md 文件
总大小: {size_mb:.2f} MB

是否要将其添加到源列表？
        """.strip()

        if messagebox.askyesno("确认添加", msg):
            self.source_files[folder_path] = {
                "enabled": True, 
                "type": "folder",
                "files": scanned_files, # 存储扫描到的文件及其mtime
                "mtime": os.path.getmtime(folder_path) # 存储文件夹本身的mtime
            }
            self.update_source_list()
            self.set_status(f"已添加文件夹: {folder_path}")
        else:
            self.set_status("操作已取消。")
    def toggle_s(self):
        s = self.s_tree.focus()
        if s: self.source_files[s]["enabled"] = not self.source_files[s].get("enabled", False); self.update_source_list()
    def remove_s(self):
        selected_id = self.s_tree.focus()
        if not selected_id:
            return

        if messagebox.askyesno("确认移除", f"确定要移除 '{selected_id}' 吗？\n\n注意：如果这是一个文件夹，所有由它生成的词库文件也将被删除。"):
            
            # 1. 识别并准备删除相关的生成文件
            files_to_delete = []
            if self.source_files[selected_id].get("type") == "folder":
                # 遍历所有生成的词库，看它们的来源是否是当前要删除的文件夹
                for gen_path, source_path in list(self.generated_files.items()):
                    if source_path == selected_id:
                        files_to_delete.append(gen_path)
            
            # 2. 从磁盘和记录中删除这些文件
            for f_path in files_to_delete:
                try:
                    if os.path.exists(f_path):
                        os.chmod(f_path, stat.S_IWRITE)
                        os.remove(f_path)
                    
                    # 从 generated_files 字典中移除
                    if f_path in self.generated_files:
                        del self.generated_files[f_path]

                except Exception as e:
                    messagebox.showerror("删除失败", f"删除生成的词库 {f_path} 失败: {e}")

            # 3. 从源列表中删除条目
            del self.source_files[selected_id]
            
            # 4. 更新UI
            self.update_source_list()
            self.update_generated_list()
            self.set_status(f"'{os.path.basename(selected_id)}' 已被移除。")
    def select_o(self):
        p = filedialog.askdirectory(); self.output_path = p if p else self.output_path; self.o_path_var.set(f"至: {self.output_path}")
    def rescan_folder_if_needed(self, folder_path, data):
        """
        重新扫描文件夹，如果文件列表或mtime有变则更新，并返回是否有变化。
        """
        try:
            current_mtime = os.path.getmtime(folder_path)
            # 检查文件夹本身的mtime，这可以捕获顶层的文件/夹增删
            if data.get("mtime", 0) != current_mtime:
                self.set_status(f"检测到文件夹 {os.path.basename(folder_path)} 结构变化，重新扫描...")
                new_files_data = {}
                for root, _, files in os.walk(folder_path):
                    for file in files:
                        if file.endswith('.md'):
                            f_path = os.path.normpath(os.path.join(root, file))
                            try:
                                new_files_data[f_path] = os.path.getmtime(f_path)
                            except OSError:
                                continue
                data["files"] = new_files_data
                data["mtime"] = current_mtime
                return True

            # 检查文件夹内现有文件的mtime
            for f_path, mtime in data.get("files", {}).items():
                if os.path.exists(f_path):
                    if os.path.getmtime(f_path) != mtime:
                        self.set_status(f"检测到 {os.path.basename(f_path)} 内容变化...")
                        # 只需返回True，proc_all会处理所有文件的重新生成
                        return True
        except OSError:
            return False # 文件夹或文件可能已被删除
        return False

    def file_monitor_worker(self):
        while not self.stop_monitoring.is_set():
            changed = False
            # 创建一个副本以安全地迭代，因为我们可能会在循环中修改字典
            source_items = list(self.source_files.items())

            for path, data in source_items:
                if not data.get("enabled") or not os.path.exists(path):
                    continue
                
                try:
                    item_type = data.get("type", "file")
                    if item_type == "file":
                        mtime = os.path.getmtime(path)
                        if data.get("mtime", 0) != mtime:
                            self.set_status(f"检测到 {os.path.basename(path)} 更改...")
                            data["mtime"] = mtime
                            changed = True
                    elif item_type == "folder":
                        if self.rescan_folder_if_needed(path, data):
                            changed = True

                except OSError:
                    # 文件或文件夹可能在检查期间被删除
                    continue
            
            if changed:
                self.set_status("检测到更改，正在重新生成...")
                self.proc_all(from_monitor=True)
                self.set_status("自动生成完成。")

            time.sleep(3)
    def toggle_mon(self):
        if self.auto_generate.get(): self.stop_monitoring.clear(); self.monitoring_thread = threading.Thread(target=self.file_monitor_worker, daemon=True); self.monitoring_thread.start(); self.set_status("监控已开启。")
        else: self.stop_monitoring.set(); self.monitoring_thread = None; self.set_status("监控已关闭。")
    def set_status(self, msg): self.status_var.set(msg); self.update_idletasks()
    def on_closing(self): self.stop_monitoring.set(); self.save_config(); self.destroy()

def run_tests(app_instance):
    """
    自动化测试函数，用于验证 AstParser 是否符合预期。
    """
    test_file_path = '测试内容.txt'
    print("="*20 + " 开始自动化测试 " + "="*20)
    
    try:
        with open(test_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"错误: 测试文件 '{test_file_path}' 未找到。")
        return

    # 解析测试文件
    test_cases = re.split(r'--- 测试案例: (.*?) ---', content)[1:]
    parser = app_instance.parser
    
    total_tests = len(test_cases) // 2
    passed_tests = 0

    for i in range(0, len(test_cases), 2):
        case_name = test_cases[i].strip()
        body = test_cases[i+1]
        
        source_match = re.search(r'--- 源文件 ---\n(.*?)\n--- 预期输出 ---', body, re.DOTALL)
        expected_match = re.search(r'--- 预期输出 ---\n(.*?)$', body, re.DOTALL)
        
        if not (source_match and expected_match):
            print(f"\n--- 测试 [{case_name}]: 格式错误，跳过 ---")
            continue

        source_text = source_match.group(1).strip()
        expected_raw = expected_match.group(1).strip()
        
        # 检查是否有特殊的规则定义
        rules_text = ""
        if "排除规则" in case_name:
             rules_text = """
[排除规则]
排除行_1 = ^\s*id::.*
排除行_2 = ^\s*collapsed::.*
[替换规则]
替换内容_1 = \(\(.*?\)\)
"""
        # 解析预期的文件名和内容
        expected_filename_match = re.search(r'文件名: (.*?)\n', expected_raw)
        if not expected_filename_match:
            print(f"\n--- 测试 [{case_name}]: 预期输出中未找到文件名，跳过 ---")
            continue
            
        expected_filename = expected_filename_match.group(1).strip()
        # 标准化预期输出，将 Tab 替换为 4 个空格，与解析器输入保持一致
        expected_content_lines = expected_raw[expected_filename_match.end():].strip().split('\n')
        expected_content = [line.replace('\t', '    ') for line in expected_content_lines]
        
        # 使用解析器处理
        actual_results, _ = parser.parse(source_text, rules_text)
        
        # 获取实际输出
        actual_content = actual_results.get(expected_filename, [])
        
        # 规范化输出以便比较（去除空行和首尾空格）
        actual_content_clean = [line.rstrip() for line in actual_content if line.strip()]
        expected_content_clean = [line.rstrip() for line in expected_content if line.strip()]

        print(f"\n--- 正在测试: [{case_name}] ---")
        
        # 无论成功与否，都打印输出以便比对
        print("--- 预期输出 ---")
        print('\n'.join(expected_content))
        print("\n--- 实际输出 ---")
        print('\n'.join(actual_content))

        if actual_content_clean == expected_content_clean:
            print("\n✅ PASSED")
            passed_tests += 1
        else:
            print("\n❌ FAILED")
        
        print("-" * 20)

    print("\n" + "="*20 + " 测试总结 " + "="*20)
    print(f"总共测试: {total_tests} | 通过: {passed_tests} | 失败: {total_tests - passed_tests}")
    print("="*50)

if __name__ == "__main__":
    app = KvTreeApp()
    # 在UI主循环开始前，运行测试
    run_tests(app)
    app.mainloop()