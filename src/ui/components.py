import tkinter as tk
from tkinter import ttk

class ToolTip(object):
    """
    Creates a ToolTip (hover-box) for any tkinter widget.
    """
    def __init__(self, widget, text='widget info'):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        self.id = None
        self.x = self.y = 0
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)

    def enter(self, event=None):
        self.schedule()

    def leave(self, event=None):
        self.unschedule()
        self.hidetip()

    def schedule(self):
        self.unschedule()
        self.id = self.widget.after(500, self.showtip)

    def unschedule(self):
        id_ = self.id
        self.id = None
        if id_:
            self.widget.after_cancel(id_)

    def showtip(self, event=None):
        self.unschedule()
        x, y, cx, cy = self.widget.bbox("insert") or (0,0,0,0)
        x = self.widget.winfo_rootx() + 25
        y = self.widget.winfo_rooty() + 20
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry("+%d+%d" % (x, y))
        label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                      background="#FFFFE0", relief=tk.SOLID, borderwidth=1,
                      font=("Microsoft YaHei UI", 9, "normal"))
        label.pack(ipadx=4, ipady=4)

    def hidetip(self):
        tw = self.tipwindow
        self.tipwindow = None
        if tw:
            tw.destroy()

class DynamicListWindow(tk.Toplevel):
    def __init__(self, parent, title, instruction, initial_items, placeholder="在这里输入匹配内容..."):
        super().__init__(parent)
        self.title(title)
        self.geometry("550x450")
        self._center_window(parent)
        self.transient(parent)
        self.grab_set()
        
        self.placeholder = placeholder
        self.rows = []
        
        # Header Info
        info_lbl = ttk.Label(self, text=instruction, foreground="gray", justify=tk.LEFT, wraplength=500)
        info_lbl.pack(anchor="w", padx=15, pady=(15, 5))
        
        # Scrollable Canvas
        frame = ttk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        
        self.canvas = tk.Canvas(frame)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Add Initial Items
        for item in initial_items:
            if item.strip():
                self.add_row(item.strip())
                
        # If empty, add one empty row so user sees how to type
        if not self.rows:
            self.add_row("")

        # Add Row Button
        btn_add = ttk.Button(self, text="➕ 添加新的一行", command=lambda: self.add_row(""))
        btn_add.pack(pady=5)
        
        # Footer Buttons
        button_frame = ttk.Frame(self)
        button_frame.pack(pady=10)
        ttk.Button(button_frame, text="✅ 保存", command=self.save_and_close).pack(side="left", padx=5)
        ttk.Button(button_frame, text="取消", command=self.destroy).pack(side="left", padx=5)
        
        self.saved_items = None
        
    def add_row(self, content=""):
        row_frame = ttk.Frame(self.scrollable_frame)
        row_frame.pack(fill=tk.X, pady=2, padx=5)
        
        entry_var = tk.StringVar(value=content)
        entry = ttk.Entry(row_frame, textvariable=entry_var, font=("Consolas", 10))
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        btn_rm = ttk.Button(row_frame, text="➖ 删除", width=6, command=lambda: self.remove_row(row_frame, entry_var))
        btn_rm.pack(side=tk.RIGHT)
        
        self.rows.append((row_frame, entry_var))
        
        # force canvas to update scroll
        self.update_idletasks()
        self.canvas.yview_moveto(1.0)
        
    def remove_row(self, frame, var):
        frame.pack_forget()
        frame.destroy()
        self.rows = [(f, v) for f, v in self.rows if v != var]
        
    def show(self):
        self.wait_window()
        return self.saved_items
        
    def save_and_close(self):
        items = []
        for _, var in self.rows:
            val = var.get().strip()
            if val:
                items.append(val)
        self.saved_items = items
        self.destroy()

    def _center_window(self, parent):
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

class DualRuleWindow(tk.Toplevel):
    def __init__(self, parent, rules_dict=None):
        super().__init__(parent)
        self.title("双元替换清洗引擎配置面板")
        self.geometry("750x650")
        self.transient(parent)
        self.grab_set()
        self._center_window(parent)
        
        self.result = None
        
        main_frame = ttk.Frame(self, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))

        canvas = tk.Canvas(content_frame, borderwidth=0, highlightthickness=0)
        v_scrollbar = ttk.Scrollbar(content_frame, orient="vertical", command=canvas.yview)
        
        self.scrollable_frame = ttk.Frame(canvas)
        self.scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(window_id, width=e.width))
        
        # Add mousewheel support for the entire pop-up
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        self.bind("<MouseWheel>", _on_mousewheel)
        
        window_id = canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=v_scrollbar.set)
        
        v_scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        
        self.line_rows = []
        self.content_rows = []

        if not rules_dict or not isinstance(rules_dict, dict):
            rules_dict = {"line_rules": [], "content_rules": []}

        # --- SECTION 1: Line Rules ---
        self._build_section(
            self.scrollable_frame, 
            "🔴 排除行 (匹配后整行剔除放弃入库，除非填写替换项重组整行)", 
            self.line_rows, 
            rules_dict.get("line_rules", [])
        )

        ttk.Separator(self.scrollable_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=20)

        # --- SECTION 2: Content Rules ---
        self._build_section(
            self.scrollable_frame, 
            "🟡 排除内容 (仅消除或替换行内匹配到的局部内容，不伤害该行其他字词)", 
            self.content_rows, 
            rules_dict.get("content_rules", [])
        )

        # Bottom Actions
        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        btn_save = ttk.Button(action_frame, text="✅ 保存配置", command=self.save_and_close)
        btn_save.pack(side=tk.RIGHT)
        
        btn_cancel = ttk.Button(action_frame, text="❌ 取消", command=self.destroy)
        btn_cancel.pack(side=tk.RIGHT, padx=10)

    def _build_section(self, parent_frame, title, row_list, initial_data):
        section_frame = ttk.Frame(parent_frame)
        section_frame.pack(fill=tk.X, pady=5)
        
        header_lbl = ttk.Label(section_frame, text=title, font=("Microsoft YaHei UI", 11, "bold"), foreground="#D83B01" if "🔴" in title else "#B8860B")
        header_lbl.pack(anchor="w", pady=(0, 10))
        
        col_frame = ttk.Frame(section_frame)
        col_frame.pack(fill=tk.X)
        ttk.Label(col_frame, text="欲匹配的内容 (正则或文本)").pack(side=tk.LEFT, expand=True, fill=tk.X)
        ttk.Label(col_frame, text="替换项 (没有则直接为空)").pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(10,0))
        ttk.Label(col_frame, text="操作", width=10).pack(side=tk.RIGHT)
        
        list_frame = ttk.Frame(section_frame)
        list_frame.pack(fill=tk.X, pady=5)
        
        if not initial_data:
            for _ in range(2):
                self._add_row_to(list_frame, row_list)
        else:
            for item in initial_data:
                self._add_row_to(list_frame, row_list, item.get("match", ""), item.get("replace", ""))
                
        btn_add = ttk.Button(section_frame, text="➕ 添加一行", command=lambda f=list_frame, r=row_list: self._add_row_to(f, r))
        btn_add.pack(anchor="w", pady=5)

    def _add_row_to(self, parent_frame, row_list, init_match="", init_replace=""):
        row_frame = ttk.Frame(parent_frame)
        row_frame.pack(fill=tk.X, pady=2)
        
        m_var = tk.StringVar(value=init_match)
        r_var = tk.StringVar(value=init_replace)
        
        e_m = ttk.Entry(row_frame, textvariable=m_var, font=("Consolas", 10))
        e_m.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        e_r = ttk.Entry(row_frame, textvariable=r_var, font=("Consolas", 10))
        e_r.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 5))
        
        btn_rm = ttk.Button(row_frame, text="➖ 删除", width=6)
        btn_rm.config(command=lambda f=row_frame, t=(m_var, r_var), l=row_list: self._remove_row(f, t, l))
        btn_rm.pack(side=tk.RIGHT)
        
        row_list.append((m_var, r_var))
        
    def _remove_row(self, frame, row_tuple, row_list):
        frame.destroy()
        if row_tuple in row_list:
            row_list.remove(row_tuple)
            
    def save_and_close(self):
        l_rules = [{"match": m.get().strip(), "replace": r.get()} for m, r in self.line_rows if m.get().strip()]
        c_rules = [{"match": m.get().strip(), "replace": r.get()} for m, r in self.content_rows if m.get().strip()]
                
        self.result = {"line_rules": l_rules, "content_rules": c_rules}
        self.destroy()
        
    def show(self):
        self.wait_window()
        return self.result

    def _center_window(self, parent):
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

class AdvancedOptionsWindow(tk.Toplevel):
    def __init__(self, parent, options):
        super().__init__(parent)
        self.title("高级选项")
        self.geometry("400x320")
        self._center_window(parent)
        self.transient(parent)
        self.grab_set()
        
        self.options = options
        self.scan_keys_var = tk.BooleanVar(value=options.get("logseq_scan_keys", False))
        self.scan_values_var = tk.BooleanVar(value=options.get("logseq_scan_values", False))
        self.scan_pure_values_var = tk.BooleanVar(value=options.get("logseq_scan_pure_values", False))
        self.run_on_startup_var = tk.BooleanVar(value=options.get("run_on_startup", False))
        self.minimize_to_tray_var = tk.BooleanVar(value=options.get("minimize_to_tray", True))
        
        notebook = ttk.Notebook(self)
        notebook.pack(padx=10, pady=10, fill="both", expand=True)
        
        common_frame = ttk.Frame(notebook)
        notebook.add(common_frame, text="常用")
        common_lf = ttk.LabelFrame(common_frame, text="常规设置", padding="10")
        common_lf.pack(padx=10, pady=10, fill="x")
        ttk.Checkbutton(common_lf, text="系统启动时启动", variable=self.run_on_startup_var).pack(anchor="w", pady=2)
        ttk.Checkbutton(common_lf, text="最小化时在托盘 (默认勾选)", variable=self.minimize_to_tray_var).pack(anchor="w", pady=2)
        
        scan_frame = ttk.Frame(notebook)
        notebook.add(scan_frame, text="扫描")
        logseq_lf = ttk.LabelFrame(scan_frame, text="Logseq md属性扫描", padding="10")
        logseq_lf.pack(padx=10, pady=10, fill="x")
        ttk.Checkbutton(logseq_lf, text="页内属性键录入为词条", variable=self.scan_keys_var).pack(anchor="w", pady=2)
        ttk.Checkbutton(logseq_lf, text="页内属性值录入为词条-带双方括号[[]]的", variable=self.scan_values_var).pack(anchor="w", pady=2)
        ttk.Checkbutton(logseq_lf, text="页内属性值录入为词条 (无[[]]的纯文本)", variable=self.scan_pure_values_var).pack(anchor="w", pady=2)
        
        button_frame = ttk.Frame(self)
        button_frame.pack(pady=10)
        ttk.Button(button_frame, text="保存", command=self.save_and_close).pack(side="left", padx=5)
        ttk.Button(button_frame, text="取消", command=self.destroy).pack(side="left", padx=5)
        
        self.saved_options = None
        
    def save_and_close(self):
        self.saved_options = {
            "logseq_scan_keys": self.scan_keys_var.get(),
            "logseq_scan_values": self.scan_values_var.get(),
            "logseq_scan_pure_values": self.scan_pure_values_var.get(),
            "run_on_startup": self.run_on_startup_var.get(),
            "minimize_to_tray": self.minimize_to_tray_var.get()
        }
        self.destroy()
        
    def show(self):
        self.wait_window()
        return self.saved_options

    def _center_window(self, parent):
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

class BlacklistWindow(tk.Toplevel):
    def __init__(self, parent, all_possible_basenames, blacklist_manager):
        super().__init__(parent)
        self.title("🚫 词库排除选择 (黑名单)")
        self.geometry("450x450")
        self._center_window(parent)
        self.transient(parent)
        self.grab_set()
        
        self.blacklist_manager = blacklist_manager
        current_blacklist = self.blacklist_manager()
        
        # Combine possible basenames with anything historically in the blacklist
        all_known_basenames = set(current_blacklist)
        for basename in all_possible_basenames:
            all_known_basenames.add(basename)
            
        self.vars = {}
        
        info_lbl = ttk.Label(self, text="打勾的词库将被永久剔除，以后扫描绝不生成并将在列表中隐藏：", foreground="gray", justify=tk.LEFT)
        info_lbl.pack(anchor="w", padx=15, pady=(15, 5))
        
        frame = ttk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        
        canvas = tk.Canvas(frame)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)

        self.scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        if not all_known_basenames:
            ttk.Label(self.scrollable_frame, text="暂无发现任何生成过的词库...").pack(pady=20)
            
        for basename in sorted(list(all_known_basenames)):
            var = tk.BooleanVar(value=(basename in current_blacklist))
            self.vars[basename] = var
            cb = ttk.Checkbutton(self.scrollable_frame, text=basename, variable=var)
            cb.pack(anchor="w", pady=2)

        button_frame = ttk.Frame(self)
        button_frame.pack(pady=10)
        ttk.Button(button_frame, text="✅ 保存黑名单", command=self.save_and_close).pack(side="left", padx=5)
        ttk.Button(button_frame, text="取消", command=self.destroy).pack(side="left", padx=5)
        
        self.saved = False
        self.final_blacklist = current_blacklist

    def save_and_close(self):
        new_list = set()
        for basename, var in self.vars.items():
            if var.get():
                new_list.add(basename)
        self.final_blacklist = new_list
        self.saved = True
        self.destroy()

    def show(self):
        self.wait_window()
        return self.saved, self.final_blacklist

    def _center_window(self, parent):
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")
