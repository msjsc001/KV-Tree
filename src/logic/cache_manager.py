# app_logic/cache_manager.py
# 负责管理解析缓存 (parsing_cache.json)

import json
import os
import threading

class CacheManager:
    def __init__(self, cache_file_path):
        self.cache_file = cache_file_path
        self.cache_data = {}
        self.lock = threading.Lock() # 线程锁，确保多线程写入安全
        self.load_cache()

    def load_cache(self):
        """从文件加载缓存到内存中。"""
        with self.lock:
            if os.path.exists(self.cache_file):
                try:
                    with open(self.cache_file, 'r', encoding='utf-8') as f:
                        self.cache_data = json.load(f)
                except (json.JSONDecodeError, IOError):
                    # 如果文件损坏或无法读取，则视为空缓存
                    self.cache_data = {}
            else:
                self.cache_data = {}

    def save_cache(self):
        """将内存中的缓存数据保存到文件。"""
        with self.lock:
            try:
                with open(self.cache_file, 'w', encoding='utf-8') as f:
                    json.dump(self.cache_data, f, ensure_ascii=False, indent=4)
            except IOError as e:
                print(f"Error saving cache file: {e}")

    def get_entry(self, file_path):
        """获取单个文件的缓存条目。"""
        with self.lock:
            return self.cache_data.get(file_path)

    def update_entry(self, file_path, mtime, generated_outputs):
        """
        更新或添加一个文件的缓存条目。
        
        Args:
            file_path (str): 源文件的绝对路径。
            mtime (float): 源文件的最后修改时间。
            generated_outputs (dict): 由此文件生成的输出文件信息 {output_path: [entry1, entry2], ...}
        """
        with self.lock:
            self.cache_data[file_path] = {
                "mtime": mtime,
                "outputs": generated_outputs
            }

    def remove_entry(self, file_path):
        """从缓存中移除一个文件的条目。"""
        with self.lock:
            if file_path in self.cache_data:
                del self.cache_data[file_path]

    def get_all_cached_paths(self):
        """获取所有已缓存的文件路径列表。"""
        with self.lock:
            return list(self.cache_data.keys())

    def get_outputs_for_file(self, file_path):
        """获取一个文件生成的所有输出文件及其条目。"""
        with self.lock:
            entry = self.cache_data.get(file_path, {})
            return entry.get("outputs", {})
