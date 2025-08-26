# app_logic/config_manager.py
# 用于管理应用的配置加载、保存和默认值

import json
import os

DEFAULT_RULES = """
[排除规则]
; 每行一个正则表达式，匹配到的整行内容都将被忽略
排除行_1 = ^\s*id::.*
排除行_2 = ^\s*collapsed::.*

[替换规则]
; 将匹配到的内容替换为空
替换内容_1 = \(\(.*?\)\)
""".strip()

class ConfigManager:
    def __init__(self, config_file="kv_tree_config.json"):
        self.config_file = config_file
        self.config = {
            "source_files": {},
            "output_path": os.getcwd(),
            "rules": DEFAULT_RULES,
            "advanced_options": {
                "logseq_scan_keys": False,
                "logseq_scan_values": False,
                "run_on_startup": False,
                "minimize_to_tray": True
            },
            "output_selection": {}
        }

    def load_config(self):
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                loaded_config = json.load(f)
            
            # 加载和升级旧配置
            loaded_sources = loaded_config.get("source_files", {})
            for path, data in loaded_sources.items():
                if "type" not in data: 
                    data["type"] = "file"
                if data["type"] == "folder" and "files" not in data:
                    data["files"] = {}
            self.config["source_files"] = loaded_sources
            
            self.config["output_path"] = loaded_config.get("output_path", os.getcwd())
            
            self.config["rules"] = loaded_config.get("rules", DEFAULT_RULES)
            if not self.config["rules"].strip():
                self.config["rules"] = DEFAULT_RULES

            # 加载高级选项，如果不存在则使用默认值
            # 加载高级选项，并确保新键存在
            loaded_advanced = loaded_config.get("advanced_options", {})
            default_advanced = self.config["advanced_options"]
            self.config["advanced_options"] = {**default_advanced, **loaded_advanced}
            
            # 加载输出选择，如果不存在则使用默认值
            self.config["output_selection"] = loaded_config.get("output_selection", {})

        except (FileNotFoundError, json.JSONDecodeError):
            # 如果文件不存在或无效，则使用默认配置
            pass
        return self.config

    def save_config(self, app_data):
        """ 使用从主应用传入的最新数据来保存配置 """
        config_to_save = {
            "source_files": app_data.get("source_files", {}),
            "output_path": app_data.get("output_path", os.getcwd()),
            "rules": app_data.get("rules", DEFAULT_RULES),
            "advanced_options": app_data.get("advanced_options", {}),
            "output_selection": app_data.get("output_selection", {})
        }
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(config_to_save, f, indent=4)