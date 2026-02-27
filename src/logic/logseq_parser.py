# app_logic/logseq_parser.py
# 专门用于解析 Logseq .md 文件页眉属性的模块

import re

class LogseqParser:
    def __init__(self, scan_keys=False, scan_values=False):
        """
        初始化解析器。
        :param scan_keys: 是否扫描属性键 (e.g., "tags::")
        :param scan_values: 是否扫描双方括号括起来的属性值 (e.g., "[[value]]")
        """
        self.scan_keys = scan_keys
        self.scan_values = scan_values
        # 匹配 "key::" 格式
        self.key_pattern = re.compile(r'^\s*([^\s:]+)::')
        # 匹配 "[[value]]" 格式
        self.value_pattern = re.compile(r'\[\[(.*?)\]\]')

    def parse_file_content(self, content: str) -> list[str]:
        """
        解析给定的文件内容，提取词条。
        :param content: 文件的完整内容字符串。
        :return: 从文件中提取的词条列表。
        """
        if not self.scan_keys and not self.scan_values:
            return []

        entries = set()
        lines = content.splitlines()

        for line in lines:
            # 现在我们需要扫描整个文件，而不是仅仅扫描头部。
            # 因此，我们将移除原来用于在遇到非属性行时中断扫描的逻辑。
            
            # 检查行中是否包含属性分隔符 '::'
            is_property_line = '::' in line
            
            if not is_property_line:
                # 如果当前行不是属性行，则跳过，继续检查下一行。
                continue

            # 提取属性键
            if self.scan_keys:
                # 查找所有 "key::"
                found_keys = re.findall(self.key_pattern, line)
                for key in found_keys:
                    entries.add(f"- {key.strip()}::")

            # 提取属性值
            if self.scan_values:
                # 查找所有 "[[value]]"
                found_values = self.value_pattern.findall(line)
                for value in found_values:
                    entries.add(f"- [[{value}]]")
        
        return sorted(list(entries))