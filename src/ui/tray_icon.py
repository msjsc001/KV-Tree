import pystray
import threading
from PIL import Image
from tkinter import messagebox
import sys
import os

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class AppTrayIcon:
    def __init__(self, app_ui, version):
        self.app_ui = app_ui
        self.version = version
        self.icon = None

    def setup(self):
        try: 
            image = Image.open(resource_path("icon.ico"))
        except Exception as e: 
            self.app_ui.after(100, lambda: messagebox.showerror("图标错误", f"图标文件'icon.ico'加载失败: {e}"))
            return
            
        menu = (
            pystray.MenuItem("显示/隐藏", self.toggle_window, default=True), 
            pystray.Menu.SEPARATOR, 
            pystray.MenuItem("退出", self.on_closing_from_tray)
        )
        self.icon = pystray.Icon("kv_tree_app", image, f"KVTree {self.version}", menu)
        threading.Thread(target=self.icon.run, daemon=True).start()

    def stop(self):
        if self.icon:
            self.icon.stop()

    def toggle_window(self):
        if self.app_ui.state() == "normal": 
            self.app_ui.withdraw()
        else: 
            self.app_ui.deiconify()
            self.app_ui.lift()
            self.app_ui.focus_force()

    def on_closing_from_tray(self):
        self.app_ui.on_closing(from_tray=True)

