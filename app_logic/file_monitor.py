# app_logic/file_monitor.py
# 使用 watchdog 实现高效的文件和文件夹变化监控
# V0.7: 传递更详细的事件信息以支持增量更新

import time
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class AppEventHandler(FileSystemEventHandler):
    """处理文件系统事件，并触发UI回调，传递具体事件信息"""

    def __init__(self, app_instance):
        super().__init__()
        self.app = app_instance
        self.last_event_time = {} # 使用字典记录每个文件的最后事件时间，以进行更精细的防抖

    def process_event(self, event_type, path):
        """
        对事件进行防抖处理，并调用主程序的回调。
        """
        # 只处理.md文件，忽略其他文件和目录事件
        if not path.endswith('.md'):
            return

        current_time = time.time()
        
        # 防抖检查：如果同一个文件在1秒内连续触发，则忽略
        if path in self.last_event_time and current_time - self.last_event_time[path] < 1.0:
            return
        
        self.last_event_time[path] = current_time
        
        # 调用主应用的回调方法，传递事件类型和路径
        self.app.queue_process_file(event_type, path)
    
    def on_modified(self, event):
        if not event.is_directory:
            self.process_event("modified", event.src_path)

    def on_created(self, event):
        if not event.is_directory:
            self.process_event("created", event.src_path)

    def on_deleted(self, event):
        if not event.is_directory:
            self.process_event("deleted", event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            # 一个移动事件等同于 "从旧位置删除" 和 "在新位置创建"
            self.process_event("deleted", event.src_path)
            self.process_event("created", event.dest_path)


class FileMonitor:
    """管理 watchdog 观察者，启动和停止监控"""

    def __init__(self, app_instance):
        self.app = app_instance
        self.observer = None
        self.event_handler = AppEventHandler(self.app)

    def start(self, paths_to_watch):
        """
        启动监控。
        """
        if self.observer and self.observer.is_alive():
            self.stop() 

        self.observer = Observer()
        
        watched_paths = set()
        for path in paths_to_watch:
            if not os.path.exists(path):
                continue
            
            watch_path = os.path.dirname(path) if os.path.isfile(path) else path
            
            if watch_path not in watched_paths:
                self.observer.schedule(self.event_handler, watch_path, recursive=True)
                watched_paths.add(watch_path)
        
        if watched_paths:
            self.observer.start()
            self.app.set_status(f"监控已开启，正在监视 {len(watched_paths)} 个位置。")
        else:
            self.app.set_status("监控开启，但无启用的源可供监视。")

    def stop(self):
        """停止监控"""
        if self.observer and self.observer.is_alive():
            self.observer.stop()
            self.observer.join()
            self.observer = None
            self.app.set_status("监控已关闭。")
