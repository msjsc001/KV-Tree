# app_logic/file_monitor.py
# 用于监控文件和文件夹的变化

import os
import time
import threading

class FileMonitor:
    def __init__(self, app_instance, stop_event):
        self.app = app_instance
        self.stop_monitoring = stop_event

    def rescan_folder_if_needed(self, folder_path, data):
        """
        重新扫描文件夹，如果文件列表或mtime有变则更新，并返回是否有变化。
        """
        try:
            current_mtime = os.path.getmtime(folder_path)
            # 检查文件夹本身的mtime，这可以捕获顶层的文件/夹增删
            if data.get("mtime", 0) != current_mtime:
                self.app.set_status(f"检测到文件夹 {os.path.basename(folder_path)} 结构变化，重新扫描...")
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
                        self.app.set_status(f"检测到 {os.path.basename(f_path)} 内容变化...")
                        # 只需返回True，proc_all会处理所有文件的重新生成
                        return True
        except OSError:
            return False # 文件夹或文件可能已被删除
        return False

    def file_monitor_worker(self):
        while not self.stop_monitoring.is_set():
            changed = False
            # 创建一个副本以安全地迭代
            source_items = list(self.app.source_files.items())

            for path, data in source_items:
                if not data.get("enabled") or not os.path.exists(path):
                    continue
                
                try:
                    item_type = data.get("type", "file")
                    if item_type == "file":
                        mtime = os.path.getmtime(path)
                        if data.get("mtime", 0) != mtime:
                            self.app.set_status(f"检测到 {os.path.basename(path)} 更改...")
                            data["mtime"] = mtime
                            changed = True
                    elif item_type == "folder":
                        if self.rescan_folder_if_needed(path, data):
                            changed = True

                except OSError:
                    # 文件或文件夹可能在检查期间被删除
                    continue
            
            if changed:
                self.app.set_status("检测到更改，正在重新生成...")
                self.app.proc_all(from_monitor=True)
                self.app.set_status("自动生成完成。")

            time.sleep(3)