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
            # 根据我们商定的规则，我们只扫描文件头部。
            # 一旦遇到非属性行（如空行或正文），就停止扫描。
            clean_line = line.strip()
            if not clean_line:
                break # 遇到空行，停止
            
            # 使用一个更通用的模式来判断是否是属性行
            is_property_line = '::' in clean_line
            
            if not is_property_line and not clean_line.startswith('-'):
                 # 如果不是属性行，并且不是列表项（通常是正文的开始），就停止
                 pass
            elif not is_property_line and clean_line.startswith('-'):
                break 

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