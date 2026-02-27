import re
from collections import defaultdict

class Node:
    """
    表示 AST 中的一个节点，对应于源文本中的一行。
    """
    def __init__(self, raw_line: str, indent: int, parent=None):
        self.raw_line = raw_line  # 原始行内容
        self.indent = indent      # 缩进级别
        self.parent = parent      # 父节点
        self.children = []        # 子节点列表
        self.tag = None           # 解析出的标签信息 (e.g., {'lib': '读书词库', 'mode': '父与子'})
        self.content = self._parse_content() # 去除标签后的纯内容

    def _parse_content(self):
        """从原始行中解析出标签和纯内容。"""
        tag_pattern = re.compile(r'^(?P<content>.*?)\s*(?P<tag>#KV树-(?P<lib>[^-]+)(?:-(?P<mode>父与子|不包含父))?)$')
        match = tag_pattern.search(self.raw_line.strip())
        if match:
            gd = match.groupdict()
            self.tag = {
                'lib': f"#KV树-{gd['lib']}.md",
                'mode': gd['mode']
            }
            # 返回移除了标签和前导 `- ` 的内容
            return gd['content'].lstrip('- ').strip()
        # 如果没有标签，同样移除前导 `- `
        return self.raw_line.strip().lstrip('- ').strip()

    def add_child(self, node):
        """添加一个子节点。"""
        self.children.append(node)
        node.parent = self

    def __repr__(self):
        return f"Node(indent={self.indent}, content='{self.content}', tag={self.tag})"


class AstParser:
    """
    使用 AST 方法解析文本，以更健壮地处理层级关系。
    """
    def get_indent(self, s: str) -> int:
        """计算字符串的缩进量。"""
        return len(s) - len(s.lstrip(' \t'))

    def _build_ast(self, lines: list[str]) -> Node:
        """
        从文本行构建一个 AST。
        """
        root = Node("root", -1)
        last_node_at_indent = {-1: root}

        for line in lines:
            if not line.strip():
                continue # 暂时忽略空行，后续可以作为节点处理

            indent = self.get_indent(line)
            
            # 找到正确的父节点
            parent_indent = -1
            for i in sorted(last_node_at_indent.keys(), reverse=True):
                if indent > i:
                    parent_indent = i
                    break
            
            parent_node = last_node_at_indent[parent_indent]
            
            new_node = Node(line, indent, parent=parent_node)
            parent_node.add_child(new_node)
            
            last_node_at_indent[indent] = new_node

        return root

    def parse(self, text: str, rules_text: str = "") -> tuple[dict, list]:
        """
        解析文本并返回结果。
        这是将替换旧解析器的主入口点。
        """
        # 1. 清理和预处理文本行
        # 0. 标准化输入：将所有 Tab 替换为 4 个空格
        text = text.replace('\t', '    ')
        
        # 1. 清理和预处理文本行
        lines = text.split('\n')
        exclude_patterns, replace_patterns = self._parse_rules(rules_text)
        processed_lines = self._preprocess_lines(lines, exclude_patterns, replace_patterns)

        # 2. 构建 AST
        root = self._build_ast(processed_lines)

        # 3. 从 AST 中提取数据
        kv_trees = self._extract_data(root)

        # 4. 格式化最终输出
        final_results = {lib: list(dict.fromkeys(entries)) for lib, entries in kv_trees.items()}
        return final_results, [] # 暂时不处理冲突

    def _parse_rules(self, rules_text: str) -> tuple[list, list]:
        """解析规则文本。"""
        if not rules_text:
            return [], []
        exclude_patterns = [re.compile(p) for p in re.findall(r'排除行_.*=\s*(.*)', rules_text)]
        replace_patterns = [(re.compile(p), '') for p in re.findall(r'替换内容_.*=\s*(.*)', rules_text)]
        return exclude_patterns, replace_patterns

    def _preprocess_lines(self, lines: list[str], exclude_patterns: list, replace_patterns: list) -> list[str]:
        """根据规则清理行。"""
        filtered_lines = [line for line in lines if not any(p.search(line) for p in exclude_patterns)]
        
        processed_lines = []
        for line in filtered_lines:
            for p, r in replace_patterns:
                line = p.sub(r, line)
            processed_lines.append(line)
        return processed_lines

    def _extract_data(self, root: Node) -> defaultdict:
        kv_trees = defaultdict(list)
        processed_nodes = set()

        all_nodes = []
        def get_all_nodes(node):
            all_nodes.append(node)
            for child in node.children:
                get_all_nodes(child)
        get_all_nodes(root)

        # Phase 1: Process block-level tags ('父与子', '不包含父')
        for node in all_nodes:
            if node in processed_nodes or not node.tag or not node.tag.get('mode'):
                continue
            
            lib = node.tag['lib']
            mode = node.tag['mode']
            
            processed_nodes.add(node) # Mark parent as processed

            if mode == '父与子':
                kv_trees[lib].append(node.raw_line.split('#KV树')[0].rstrip())
                self._render_block_children(node, lib, -1, kv_trees, processed_nodes)
            
            elif mode == '不包含父':
                base_indent = -1
                if node.children:
                    for child in node.children:
                        if child.raw_line.strip():
                            base_indent = child.indent
                            break
                    if base_indent != -1:
                        self._render_block_children(node, lib, base_indent, kv_trees, processed_nodes)

        # Phase 2: Process all remaining single-line tags
        for node in all_nodes:
            if node in processed_nodes or not node.tag:
                continue
            
            lib = node.tag['lib']
            # For single lines, we always want un-indented content.
            content = node.raw_line.split('#KV树')[0].strip().lstrip('-').strip()
            kv_trees[lib].append(f"- {content}")
            processed_nodes.add(node)

        return kv_trees

    def _render_block_children(self, parent_node: Node, lib: str, base_indent: int, kv_trees: defaultdict, processed_nodes: set):
        """ Renders all children of a block-defining node. """
        for node in parent_node.children:
            if node in processed_nodes:
                continue
            
            # If a child defines its own block, stop rendering this branch.
            if node.tag and node.tag.get('mode'):
                continue

            processed_nodes.add(node)
            
            line = node.raw_line.split('#KV树')[0].rstrip() if node.tag else node.raw_line

            if base_indent != -1: # '不包含父' mode
                output_line = ' ' * (node.indent - base_indent) + line.lstrip()
            else: # '父与子' mode
                output_line = line
            
            kv_trees[lib].append(output_line)

            # Recurse only if the node is NOT a tag itself.
            if not node.tag:
                self._render_block_children(node, lib, base_indent, kv_trees, processed_nodes)
