import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import sys
import webbrowser

from src.ui.tray_icon import AppTrayIcon
from src.ui.components import ToolTip

try:
    import winreg
except ImportError:
    winreg = None

class KvTreeAppUI(tk.Tk):
    VERSION = "1.0.0"

    def __init__(self, app_state, task_dispatcher, file_monitor):
        super().__init__()
        self.app_state = app_state
        self.dispatcher = task_dispatcher
        self.file_monitor = file_monitor
        
        # Setup UI callbacks
        self.dispatcher.ui_cb = {
            'set_status': self.set_status,
            'update_progress': self.update_progress,
            'update_lists': self.update_lists,
            'folder_scanned': self._show_scan_results_and_add,
            'show_error': self.show_error
        }
        self.file_monitor.ui_cb = self.dispatcher.ui_cb

        self.title(f"KVTree - v{self.VERSION} (Official)")
        self.geometry("950x750")
        self.minsize(800, 600)  # Prevent user from making it too small
        
        icon_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), "..", "..", "icon.ico")
        if os.path.exists(icon_path):
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

        opts = self.app_state.get_advanced_options()
        self.auto_generate = tk.BooleanVar(value=opts.get("auto_generate", True))
        
        self.tray_icon = AppTrayIcon(self, self.VERSION)
        
        style = ttk.Style(self)
        try:
            style.theme_use('vista')
        except tk.TclError:
            style.theme_use('clam')
        
        # Modern UI Polish
        default_font = ("Microsoft YaHei UI", 10)
        bold_font = ("Microsoft YaHei UI", 10, "bold")
        
        style.configure(".", font=default_font)
        style.configure("TLabel", font=default_font)
        style.configure("TButton", font=default_font, padding=6)
        style.configure("TCheckbutton", font=default_font)
        style.configure("TLabelframe.Label", font=bold_font, foreground="#0078D4")
        
        style.configure("TNotebook.Tab", font=default_font, padding=[15, 6])
        
        style.configure("Treeview", font=default_font, rowheight=30, borderwidth=0)
        style.configure("Treeview.Heading", font=bold_font, background="#F3F2F1", foreground="#201F1E", borderwidth=1, lightcolor="#F3F2F1", darkcolor="#F3F2F1")
        style.map("Treeview", background=[('selected', '#CBE8F6')], foreground=[('selected', '#000000')])
        
        self.build_ui()
        self.load_state_to_ui()

        self.tray_icon.setup()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.bind("<Unmap>", self.on_minimize)

        # Start workers
        self.dispatcher.start()
        self.dispatcher.put_task(("initialize",))

        if self.auto_generate.get():
            self.file_monitor.start()

    def build_ui(self):
        # PACK BOTTOM BAR FIRST SO IT NEVER COLLAPSES!
        bottom_frame = ttk.Frame(self)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(bottom_frame, textvariable=self.status_var, relief=tk.SUNKEN).pack(side=tk.BOTTOM, fill=tk.X)
        
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(bottom_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(5, 5))

        # Main Notebook structure for Tabs
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.tab_home = ttk.Frame(self.notebook, padding="10")
        self.tab_settings = ttk.Frame(self.notebook, padding="10")
        
        self.notebook.add(self.tab_home, text=" 🏠 词库转换控制台 ")
        self.notebook.add(self.tab_settings, text=" ⚙️ 偏好与高级设置 ")
        
        self._build_home_tab()
        self._build_settings_tab()

    def _build_home_tab(self):
        # Source Files
        s_frame = ttk.LabelFrame(self.tab_home, text=" 第一步：导入需要构建词库的 Markdown 笔记源 ", padding="15")
        s_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        self.s_tree = ttk.Treeview(s_frame, columns=("path", "status"), show="headings", height=3)
        self.s_tree.heading("path", text="目标路径 (支持单独文件或整个库文件夹)", anchor='w')
        self.s_tree.heading("status", text="监控状态", anchor='w')
        self.s_tree.column("status", width=80, anchor='c')
        self.s_tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        sf_btns = ttk.Frame(s_frame)
        sf_btns.pack(fill=tk.X, pady=5, side=tk.BOTTOM)
        btn_add_f = ttk.Button(sf_btns, text="添加文件", command=self.add_files)
        btn_add_f.pack(side=tk.LEFT, padx=5)
        ToolTip(btn_add_f, "支持多选，直接将指定的单个或多个 .md 笔记文件加入监控列表")
        
        btn_add_d = ttk.Button(sf_btns, text="添加文件夹", command=self.add_folder)
        btn_add_d.pack(side=tk.LEFT, padx=5)
        ToolTip(btn_add_d, "推荐！一键导入整个目录（如 Obsidian/Logseq 库目录），程序会自动扫描目录下的所有 .md 文件")
        
        btn_toggle = ttk.Button(sf_btns, text="启/禁", command=self.toggle_s)
        btn_toggle.pack(side=tk.LEFT, padx=5)
        ToolTip(btn_toggle, "暂时停止或恢复对选中文件的监控与词库生成功能")
        
        btn_rm = ttk.Button(sf_btns, text="移除", command=self.remove_s)
        btn_rm.pack(side=tk.LEFT, padx=5)
        ToolTip(btn_rm, "将选中项从列表中彻底移除，停止为其生成独立词库")

        # Output Space (Table)
        o_frame = ttk.LabelFrame(self.tab_home, text=" 第二步：设置转换后 QuickKV 词库 (.md) 的保存位置 ", padding="15")
        o_frame.pack(fill=tk.X, pady=10)
        
        self.o_tree = ttk.Treeview(o_frame, columns=("path",), show="headings", height=1)
        self.o_tree.heading("path", text="当前设定的导出目录与更新机制", anchor='w')
        self.o_tree.pack(fill=tk.X, expand=True, pady=(0, 10))
        
        o_btn_frame = ttk.Frame(o_frame)
        o_btn_frame.pack(fill=tk.X)
        btn_out = ttk.Button(o_btn_frame, text="📁 更改导出目录...", command=self.select_o)
        btn_out.pack(side=tk.LEFT)
        ToolTip(btn_out, "设置转换后的词库文件最终要保存在哪里（建议直接选为 QuickKV 的自动载入词库目录）")
        
        btn_rescan = ttk.Button(o_btn_frame, text="🚀 立即全量扫描并重建词库", command=self.confirm_and_queue_rescan)
        btn_rescan.pack(side=tk.RIGHT, padx=5)
        ToolTip(btn_rescan, "强制全盘重新读取一遍所有笔记文档，并覆写生成最新的词库。建议在调整排除规则或更改目录后手动点一次")
        
        cb_auto = ttk.Checkbutton(o_btn_frame, text="后台自动更新 (修改源笔记时自动导出)", variable=self.auto_generate, command=self.toggle_mon)
        cb_auto.pack(side=tk.RIGHT, padx=10)
        ToolTip(cb_auto, "打勾后，您只需在笔记软件里正常修改内容并按下 Ctrl+S 保存，KVT 会在几秒钟内自动帮您无感更新词库数据")
        
        # Results View
        g_frame = ttk.LabelFrame(self.tab_home, text=" 最终生成的 QuickKV 词库状态预览 ", padding="15")
        g_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        self.g_tree = ttk.Treeview(g_frame, columns=("output", "name", "source", "path", "action"), show="headings", height=6)
        self.g_tree.heading("output", text="是否导出？", anchor='w')
        self.g_tree.heading("name", text="生成的词库名", anchor='w')
        self.g_tree.heading("source", text="词库数据来源", anchor='w')
        self.g_tree.heading("path", text="已生成文件的真实路径", anchor='w')
        self.g_tree.heading("action", text="操作", anchor='c')
        self.g_tree.column("output", width=80, anchor='c')
        self.g_tree.column("action", width=80, anchor='c')
        self.g_tree.column("source", width=200)
        self.g_tree.pack(fill=tk.BOTH, expand=True)
        self.g_tree.bind("<Button-1>", self.on_g_tree_click)
        
    def _build_settings_tab(self):
        opts = self.app_state.get_advanced_options()
        rules = self.app_state.get_rules()

        # Split into two columns
        left_col = ttk.Frame(self.tab_settings)
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        right_col = ttk.Frame(self.tab_settings)
        right_col.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10, 0))

        # Left: Rules
        rules_lf = ttk.LabelFrame(left_col, text=" 🔧 自定义排除过滤规则 (高级正则表达式) ", padding="15")
        rules_lf.pack(fill=tk.BOTH, expand=True)
        
        info_lbl = ttk.Label(rules_lf, text="可以在下方编写正则，使转换器在提取文本时跳过那些你不想要的干扰行：", foreground="gray")
        info_lbl.pack(anchor="w", pady=(0, 10))
        
        self.rules_text = tk.Text(rules_lf, wrap="word", font=("Consolas", 10))
        self.rules_text.pack(fill=tk.BOTH, expand=True)
        self.rules_text.insert("1.0", rules)

        # Right: Advanced Options
        common_lf = ttk.LabelFrame(right_col, text=" ⚙️ 常规偏好 ", padding="15")
        common_lf.pack(fill=tk.X, pady=(0, 15))
        
        self.run_on_startup_var = tk.BooleanVar(value=opts.get("run_on_startup", False))
        ttk.Checkbutton(common_lf, text="系统启动时自启", variable=self.run_on_startup_var).pack(anchor="w", pady=5)
        
        self.minimize_to_tray_var = tk.BooleanVar(value=opts.get("minimize_to_tray", True))
        ttk.Checkbutton(common_lf, text="关闭窗口时最小化到系统托盘", variable=self.minimize_to_tray_var).pack(anchor="w", pady=5)

        logseq_lf = ttk.LabelFrame(right_col, text=" 📄 Logseq md属性扫描 ", padding="15")
        logseq_lf.pack(fill=tk.X, pady=(0, 15))
        
        self.scan_keys_var = tk.BooleanVar(value=opts.get("logseq_scan_keys", False))
        ttk.Checkbutton(logseq_lf, text="页内属性键录入为词条", variable=self.scan_keys_var).pack(anchor="w", pady=5)
        
        self.scan_values_var = tk.BooleanVar(value=opts.get("logseq_scan_values", False))
        ttk.Checkbutton(logseq_lf, text="页内属性值录入为词条 (带[[]]的)", variable=self.scan_values_var).pack(anchor="w", pady=5)

        danger_lf = ttk.LabelFrame(right_col, text=" ⚠️ 危险操作区 ", padding="15")
        danger_lf.pack(fill=tk.X, pady=(0, 15))
        
        self.clear_config_var = tk.BooleanVar(value=True)
        self.clear_cache_var = tk.BooleanVar(value=True)
        self.clear_output_var = tk.BooleanVar(value=False)
        
        ttk.Checkbutton(danger_lf, text="清除设置与规则记录 (恢复出厂状态)", variable=self.clear_config_var).pack(anchor="w", pady=2)
        ttk.Checkbutton(danger_lf, text="清除词库解析缓存 (解决由于缓存导致的树形刷新异常)", variable=self.clear_cache_var).pack(anchor="w", pady=2)
        ttk.Checkbutton(danger_lf, text="删除已导出的词库文件 (清空当前输出目录下所有 KVT 词库)", variable=self.clear_output_var).pack(anchor="w", pady=2)
        
        btn_clear = ttk.Button(danger_lf, text="🗑️ 确认清除所选项", command=self.clear_personal_data)
        btn_clear.pack(anchor="w", pady=(10, 0))
        ToolTip(btn_clear, "一键抹除勾选的 KVT 数据。您的源笔记文件【绝对安全】，绝不受影响。")

        btn_frame = ttk.Frame(right_col)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=10)
        
        # Link label for github help
        github_lbl = ttk.Label(btn_frame, text="❓ 帮助与更新 (GitHub)", foreground="#0078D4", cursor="hand2")
        github_lbl.pack(side=tk.LEFT)
        github_lbl.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/msjsc001/KV-Tree"))
        
        ttk.Button(btn_frame, text="✅ 保存所有设置", command=self.save_settings_from_tab).pack(side=tk.RIGHT)

    def save_settings_from_tab(self):
        new_rules = self.rules_text.get("1.0", "end-1c")
        self.app_state.set_rules(new_rules)
        
        opts = self.app_state.get_advanced_options()
        startup_changed = opts.get("run_on_startup") != self.run_on_startup_var.get()
        
        new_opts = {
            "logseq_scan_keys": self.scan_keys_var.get(),
            "logseq_scan_values": self.scan_values_var.get(),
            "run_on_startup": self.run_on_startup_var.get(),
            "minimize_to_tray": self.minimize_to_tray_var.get(),
            "auto_generate": self.auto_generate.get()
        }
        self.app_state.update_advanced_options(new_opts)
        
        if startup_changed:
            self.set_startup(new_opts.get("run_on_startup"))
        self.set_status("设置已全部保存。")
        messagebox.showinfo("成功", "设置已成功保存！")

    def clear_personal_data(self):
        msg = "这将清除您勾选的个人数据，重置软件。\n\n• 您的源 .md 笔记文件【绝不】受影响。\n• 清除后软件将立即退出，需要您手动重新打开。\n\n确认清除吗？"
        if messagebox.askyesno("⚠️ 危险操作确认", msg, icon='warning'):
            self.app_state.skip_save = True
            data_dir = os.path.abspath("用户数据")
            config_path = os.path.join(data_dir, "kv_tree_config.json")
            cache_path = os.path.join(data_dir, "parsing_cache.json")
            
            try:
                if self.clear_config_var.get() and os.path.exists(config_path):
                    os.remove(config_path)
                if self.clear_cache_var.get() and os.path.exists(cache_path):
                    os.remove(cache_path)
                if self.clear_output_var.get():
                    import stat
                    for f in self.app_state.get_active_outputs().keys():
                        if os.path.exists(f):
                            try:
                                os.chmod(f, stat.S_IWRITE)
                                os.remove(f)
                            except Exception: pass
            except Exception as e:
                messagebox.showerror("清除失败", f"清除失败: {e}\n\n请手动删除对应文件。")
            else:
                messagebox.showinfo("清除成功", "所选数据已被清除！\n程序即将退出，请手动重新运行。")
            
            self.tray_icon.stop()
            self.file_monitor.stop()
            self.dispatcher.stop()
            self.destroy()

    def load_state_to_ui(self):
        self.update_o_table()
        self.update_lists()

    def update_o_table(self):
        self.o_tree.delete(*self.o_tree.get_children())
        self.o_tree.insert("", "end", values=(self.app_state.get_output_path(),))

    def update_lists(self):
        self.update_source_list()
        self.update_generated_list()
        
    def update_progress(self, val=None, mode=None):
        if mode:
            self.progress_bar.config(mode=mode)
        if val is not None:
            self.progress_var.set(val)
            
    def set_status(self, msg):
        self.status_var.set(msg)
        self.update_idletasks()
        
    def show_error(self, title, msg):
        messagebox.showerror(title, msg)

    def on_g_tree_click(self, event):
        if self.g_tree.identify_region(event.x, event.y) != "cell": return
        column_id = self.g_tree.identify_column(event.x)
        if column_id not in ("#1", "#5"): return
        item_id = self.g_tree.identify_row(event.y)
        if not item_id: return
        
        if column_id == "#1":
            basename = os.path.basename(item_id)
            current_selection = self.app_state.get_output_selection()
            is_checked = current_selection.get(basename, True)
            self.app_state.set_output_selection(basename, not is_checked)
            
            self.dispatcher.put_task(("regenerate_output", item_id))
            self.update_generated_list()
        elif column_id == "#5":
            if os.path.exists(item_id):
                os.startfile(item_id)
            else:
                self.show_error("提示", "该词库文件尚未生成或已被删除。")

    def on_closing(self, from_tray=False):
        opts = self.app_state.get_advanced_options()
        if from_tray and opts.get("minimize_to_tray", True): 
            self.hide_to_tray()
            return
            
        self.tray_icon.stop()
        self.file_monitor.stop()
        self.dispatcher.stop()
        self.destroy()

    def update_generated_list(self):
        self.g_tree.delete(*self.g_tree.get_children())
        active_outputs = self.app_state.get_active_outputs()
        output_selection = self.app_state.get_output_selection()
        
        for f_path, source_path in sorted(active_outputs.items()):
            basename = os.path.basename(f_path)
            if basename not in output_selection: 
                self.app_state.set_output_selection(basename, True)
            
            is_checked = self.app_state.get_output_selection().get(basename, True)
            check_char = "☑" if is_checked else "☐"
            display_source = source_path if len(source_path) < 50 else "..." + source_path[-47:]
            if display_source == "多元": display_source = "由多个源文件合成"
            self.g_tree.insert("", "end", iid=f_path, values=(check_char, basename, display_source, f_path, "👁️ 打开"))

    def update_source_list(self):
        self.s_tree.delete(*self.s_tree.get_children())
        sources = self.app_state.get_source_files()
        for p, d in sources.items():
            display_text = f"[{d.get('type', 'file').upper()}] {p}"
            self.s_tree.insert("", "end", iid=p, values=(display_text, "启用" if d.get("enabled") else "禁用"))

    def add_files(self):
        files = filedialog.askopenfilenames(title="选择.md文件", filetypes=(("Markdown", "*.md"), ("All files", "*.*")))
        if not files: return
        sources = self.app_state.get_source_files()
        for f in files:
            f_path = os.path.normpath(f)
            if f_path not in sources: 
                self.app_state.update_source_file(f_path, {"enabled": True, "mtime": 0, "type": "file"})
        self.update_source_list()
        self.set_status(f"已添加 {len(files)} 个文件。")
        self.dispatcher.put_task(("initialize",))

    def add_folder(self):
        folder_path = filedialog.askdirectory(title="选择文件夹")
        if folder_path: folder_path = os.path.normpath(folder_path)
        if folder_path in self.app_state.get_source_files(): 
            messagebox.showinfo("提示", "该文件夹已在源列表中。")
            return
        self.dispatcher.put_task(("scan_folder", folder_path))

    def toggle_s(self):
        s = self.s_tree.focus()
        if s: 
            sources = self.app_state.get_source_files()
            data = sources[s]
            data["enabled"] = not data.get("enabled", False)
            self.app_state.update_source_file(s, data)
            self.update_source_list()
            self.dispatcher.put_task(("initialize",))

    def remove_s(self):
        selected_id = self.s_tree.focus()
        if not selected_id: return
        sources = self.app_state.get_source_files()
        is_folder = sources.get(selected_id, {}).get("type") == "folder"
        
        if messagebox.askyesno("确认移除", f"确定要移除 '{selected_id}' 吗？"):
            self.app_state.remove_source_file(selected_id)
            self.update_source_list()
            if is_folder:
                choice = messagebox.askquestion("清理选项", "您移除了文件夹，清理全量缓存吗？\n(是：推荐 / 否：缓释)", type=messagebox.YESNOCANCEL)
                if choice == 'yes': self.dispatcher.put_task(("clear_cache",))
                elif choice == 'no': self.dispatcher.put_task(("initialize",)) 
            else:
                self.dispatcher.put_task(("process_file", "deleted", selected_id))
            self.set_status(f"'{os.path.basename(selected_id)}' 已移除。")

    def _show_scan_results_and_add(self, folder_path, scanned_files):
        file_count = len(scanned_files)
        if file_count == 0:
            messagebox.showinfo("扫完", f"'{os.path.basename(folder_path)}' 中无.md。")
            return
        if messagebox.askyesno("确认", f"发现 {file_count} 个.md文件，确认添加到源列表？"):
            self.app_state.update_source_file(folder_path, {"enabled": True, "type": "folder", "files": scanned_files, "mtime": os.path.getmtime(folder_path)})
            self.update_source_list()
            self.dispatcher.put_task(("initialize",))
            self.set_status(f"已添加文件夹: {folder_path}...")

    def select_o(self):
        p = filedialog.askdirectory()
        if p: 
            self.app_state.set_output_path(p)
            self.update_o_table()
            self.dispatcher.put_task(("full_rescan",))

    def toggle_mon(self):
        is_auto = self.auto_generate.get()
        opts = self.app_state.get_advanced_options()
        opts["auto_generate"] = is_auto
        self.app_state.update_advanced_options(opts)
        
        if is_auto: self.file_monitor.start()
        else: self.file_monitor.stop()

    def confirm_and_queue_rescan(self):
        if messagebox.askyesno("重建确认", "将全量重构词库，期间后台运行，确认执行吗？"):
            self.dispatcher.put_task(("full_rescan",))

    def set_startup(self, enable):
        if not winreg: return
        app_name = "KVTreeApp"
        app_path = f'"{sys.executable}" "{os.path.abspath(__file__)}"' if 'python' in sys.executable.lower() else f'"{os.path.abspath(sys.executable)}"'
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as key:
                if enable: winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, app_path)
                else:
                    try: winreg.DeleteValue(key, app_name)
                    except FileNotFoundError: pass
        except Exception: pass

    def on_minimize(self, event):
        opts = self.app_state.get_advanced_options()
        if self.state() == 'iconic' and opts.get("minimize_to_tray", True): 
            self.after(10, self.withdraw)

    def hide_to_tray(self):
        opts = self.app_state.get_advanced_options()
        if opts.get("minimize_to_tray", True): self.withdraw()
        else: self.on_closing()
