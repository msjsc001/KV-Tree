# app_logic/logseq_parser.py
# 专门用于解析 Logseq .md 文件页眉属性的模块

import re

class LogseqParser:
    def __init__(self, scan_keys=False, scan_values=False, scan_pure_values=False, exclude_keys=None):
        """
        初始化解析器。
        :param scan_keys: 是否扫描属性键 (e.g., "tags::")
        :param scan_values: 是否扫描双方括号括起来的属性值 (e.g., "[[value]]")
        :param scan_pure_values: 是否扫描页内属性值为词条 (无[[]]的纯文本)
        :param exclude_keys: 排除的特定属性键集合 (碰到这些键整行跳过)
        """
        self.scan_keys = scan_keys
        self.scan_values = scan_values
        self.scan_pure_values = scan_pure_values
        self.exclude_keys = set(exclude_keys) if exclude_keys else set()
        # 匹配 "key::" 格式，支持前面带 "- " 缩进
        self.key_pattern = re.compile(r'^\s*(?:-\s*)?([^\s:]+)::')
        # 匹配 "[[value]]" 格式
        self.value_pattern = re.compile(r'\[\[(.*?)\]\]')

    def parse_file_content(self, content: str) -> list[str]:
        """
        解析给定的文件内容，提取词条。
        :param content: 文件的完整内容字符串。
        :return: 从文件中提取的词条列表。
        """
        if not self.scan_keys and not self.scan_values and getattr(self, 'scan_pure_values', False) is False:
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

            # 检查当前行是否包含任何黑名单里的键（支持精确匹配和前缀匹配）
            skip_line = False
            key_match = self.key_pattern.match(line)
            if not key_match:
                # :: 前没有有效键名（空格或空），跳过这种畸形行
                continue
            
            line_key = key_match.group(1)
            for ex in self.exclude_keys:
                if ex.endswith('*'):
                    # 前缀匹配模式：card-* 匹配所有以 card- 开头的键
                    prefix = ex[:-1]
                    if line_key.startswith(prefix):
                        skip_line = True
                        break
                else:
                    # 精确匹配模式
                    if line_key == ex:
                        skip_line = True
                        break
                    
            if skip_line:
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
                    
            if getattr(self, 'scan_pure_values', False):
                # 提取 :: 后面的所有纯文本（去除可能的 [[]] 内容以防重复，这里简单抽取）
                # 按照用户需求：如 "属性键:: 值"，提取 "值"
                # 先分割得到 :: 后面的部分
                parts = line.split("::", 1)
                if len(parts) > 1:
                    raw_val = parts[1].strip()
                    # 把带方括号的移除掉，避免在这项里提取出来
                    pure_val = re.sub(r'\[\[.*?\]\]', '', raw_val).strip()
                    # 如果还有剩余非空字符，则作为一个词条
                    
                    # 按照逗号、中文逗号等可能的分隔符切分支持多词条并置情况
                    # 比如 alias:: QK, QKV
                    candidates = re.split(r'[,，、;；]', pure_val)
                    for c in candidates:
                        c = c.strip()
                        if c:
                            entries.add(f"- {c}")
        
        return sorted(list(entries))