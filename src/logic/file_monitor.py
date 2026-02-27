import time
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class AppEventHandler(FileSystemEventHandler):
    """处理文件系统事件，并触发回调，传递具体事件信息"""

    def __init__(self, task_dispatcher, app_state):
        super().__init__()
        self.dispatcher = task_dispatcher
        self.state = app_state
        self.last_event_time = {} # 使用字典记录每个文件的最后事件时间，以进行初级防抖

    def process_event(self, event_type, path):
        # 只处理.md文件，忽略其他文件和目录事件
        if not path.endswith('.md'):
            return

        current_time = time.time()
        
        # 初级防抖检查
        if path in self.last_event_time and current_time - self.last_event_time[path] < 1.0:
            return
        
        self.last_event_time[path] = current_time
        
        # [NEW] Risk 3 Mitigation (Shadow State Fix)
        # Check if this new/deleted file belongs to a watched folder
        self._sync_shadow_state(event_type, path)
        
        # 将事件推入到任务调度队列中，由 Dispatcher 在后台做全局防抖和处理
        self.dispatcher.put_task(("process_file", event_type, path))
        
    def _sync_shadow_state(self, event_type, path):
        # 遍历 state._source_files，如果文件在该目录下，动态更新 files 字典
        sources = self.state.get_source_files()
        state_changed = False
        dir_path = os.path.dirname(path)
        
        for spath, data in sources.items():
            if data.get("type") == "folder" and dir_path.startswith(spath):
                if event_type == "created" or event_type == "modified":
                    if path not in data.get("files", {}):
                        data.setdefault("files", {})[path] = os.path.getmtime(path)
                        state_changed = True
                elif event_type == "deleted":
                    if path in data.get("files", {}):
                        del data["files"][path]
                        state_changed = True
                
                if state_changed:
                    self.state.update_source_file(spath, data)

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
            self.process_event("deleted", event.src_path)
            self.process_event("created", event.dest_path)


class FileMonitor:
    """管理 watchdog 观察者，启动和停止监控"""

    def __init__(self, task_dispatcher, app_state, ui_callbacks):
        self.dispatcher = task_dispatcher
        self.state = app_state
        self.ui_cb = ui_callbacks
        self.observer = None
        self.event_handler = AppEventHandler(self.dispatcher, self.state)

    def start(self):
        """启动监控"""
        if self.observer and self.observer.is_alive():
            self.stop() 

        self.observer = Observer()
        paths_to_watch = [p for p, d in self.state.get_source_files().items() if d.get("enabled")]
        
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
            self.ui_cb['set_status'](f"监控已开启，正在监视 {len(watched_paths)} 个位置。")
        else:
            self.ui_cb['set_status']("监控开启，但无启用的源可供监视。")

    def stop(self):
        """停止监控"""
        if self.observer and self.observer.is_alive():
            self.observer.stop()
            self.observer.join()
            self.observer = None
            self.ui_cb['set_status']("监控已关闭。")
