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
    VERSION = "v0.1"
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
        self.generated_files = set() # 用于追踪生成的词库文件
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
        ttk.Button(sf_btns, text="添加", command=self.add_s).pack(side=tk.LEFT, padx=5)
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
        self.g_tree.heading("name", text="词库"); self.g_tree.heading("source", text="来源"); self.g_tree.heading("path", text="路径")
        self.g_tree.pack(fill=tk.BOTH, expand=True)
        self.status_var = tk.StringVar(value="就绪"); ttk.Label(self, textvariable=self.status_var, relief=tk.SUNKEN).pack(side=tk.BOTTOM, fill=tk.X)
        self.load_config()
    def edit_rules(self):
        rules_window = RulesWindow(self)
        new_rules = rules_window.show(self.rules)
        if new_rules is not None: self.rules = new_rules; self.set_status("排除规则已更新。")
    def proc_all(self, from_monitor=False):
        if not from_monitor: self.set_status("生成中...")
        
        current_generated_files = set()
        conflicts = 0
        
        # 1. 解析所有启用的源文件并收集结果
        for p, d in self.source_files.items():
            if not d.get("enabled") or not os.path.exists(p): continue
            with open(p, "r", encoding="utf-8") as f: content = f.read()
            res, conf = self.parser.parse(content, self.rules); conflicts += len(conf)
            for lib, entries in res.items():
                out_path = os.path.join(self.output_path, lib)
                current_generated_files.add(out_path)
                try:
                    if os.path.exists(out_path): os.chmod(out_path, stat.S_IWRITE)
                    with open(out_path, "w", encoding="utf-8") as f: f.write("\n".join(entries))
                    os.chmod(out_path, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
                except Exception as e:
                    if not from_monitor: messagebox.showerror("错误", f"写入失败 {out_path}: {e}")

        # 2. 清理不再需要的旧文件
        files_to_delete = self.generated_files - current_generated_files
        for f_path in files_to_delete:
            try:
                if os.path.exists(f_path):
                    os.chmod(f_path, stat.S_IWRITE)
                    os.remove(f_path)
                    self.set_status(f"已删除旧词库: {os.path.basename(f_path)}")
            except Exception as e:
                if not from_monitor: messagebox.showerror("错误", f"删除失败 {f_path}: {e}")

        # 3. 更新UI和状态
        self.generated_files = current_generated_files
        self.update_generated_list()
        
        msg = f"完成！" + (f"发现 {conflicts} 冲突。" if conflicts else "")
        if not from_monitor: self.set_status(msg)
        return True
    def update_generated_list(self):
        """更新UI中的生成文件列表。"""
        self.g_tree.delete(*self.g_tree.get_children())
        # 简单的实现，只显示当前生成的文件。可以扩展为显示来源。
        for f_path in sorted(list(self.generated_files)):
            self.g_tree.insert("", "end", values=(os.path.basename(f_path), "N/A", f_path))

    def save_config(self):
        config = {
            "source_files": self.source_files,
            "output_path": self.output_path,
            "rules": self.rules,
            "generated_files": list(self.generated_files) # 保存为列表
        }
        with open(self.config_file, "w", encoding="utf-8") as f: json.dump(config, f, indent=4)

    def load_config(self):
        try:
            with open(self.config_file, "r", encoding="utf-8") as f: config = json.load(f)
            self.source_files = config.get("source_files", {});
            self.output_path = config.get("output_path", os.getcwd())
            self.generated_files = set(config.get("generated_files", [])) # 加载为集合
            
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
        for p, d in self.source_files.items(): self.s_tree.insert("", "end", iid=p, values=(p, "启用" if d.get("enabled") else "禁用"))
    def add_s(self):
        p = filedialog.askopenfilenames(title="选择", filetypes=(("MD", "*.md"),("All", "*.*")))
        if p: [self.source_files.update({fp: {"enabled": True, "mtime": 0}}) for fp in p]; self.update_source_list()
    def toggle_s(self):
        s = self.s_tree.focus()
        if s: self.source_files[s]["enabled"] = not self.source_files[s].get("enabled", False); self.update_source_list()
    def remove_s(self):
        s = self.s_tree.focus()
        if s and messagebox.askyesno("确认", f"移除 {s}?"): del self.source_files[s]; self.update_source_list()
    def select_o(self):
        p = filedialog.askdirectory(); self.output_path = p if p else self.output_path; self.o_path_var.set(f"至: {self.output_path}")
    def file_monitor_worker(self):
        while not self.stop_monitoring.is_set():
            changed = False
            for p, d in self.source_files.items():
                if d.get("enabled") and os.path.exists(p):
                    try:
                        mtime = os.path.getmtime(p)
                        if d.get("mtime", 0) != mtime:
                            self.set_status(f"检测到 {os.path.basename(p)} 更改...")
                            if self.proc_all(True): d["mtime"] = mtime
                            changed = True
                    except OSError: continue
            if changed: self.set_status("自动生成完成。")
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