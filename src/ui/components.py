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

class RulesWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("自定义排除规则")
        self.geometry("500x400")
        self._center_window(parent)
        self.transient(parent)
        self.grab_set()
        
        self.rules_text = tk.Text(self, wrap="word", font=("", 10))
        self.rules_text.pack(expand=True, fill="both", padx=10, pady=5)
        
        button_frame = ttk.Frame(self)
        button_frame.pack(pady=5)
        ttk.Button(button_frame, text="保存", command=self.save_and_close).pack(side="left", padx=5)
        ttk.Button(button_frame, text="取消", command=self.destroy).pack(side="left", padx=5)
        
        self.saved_rules = None
        
    def show(self, initial_rules):
        self.rules_text.insert("1.0", initial_rules)
        self.wait_window()
        return self.saved_rules
        
    def save_and_close(self):
        self.saved_rules = self.rules_text.get("1.0", "end-1c")
        self.destroy()

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

    def _center_window(self, parent):
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")
