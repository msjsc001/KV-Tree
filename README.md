# KVTree：您的终极 QuickKV 词库可视化管理器

KVTree (KVT) 是一款强大的桌面端效率工具，专为 [QuickKV (QKV)](https://github.com/msjsc001/QuickKV) 用户设计。它允许您在**任何 Markdown 笔记软件**（如 Obsidian、Logseq、Typora）中，通过直观的无序列表（大纲）树来优雅地管理海量词库。

KVT 会在后台静默运行，自动将您笔记中的大纲结构实时编译为 QuickKV 标准词库并输出到指定目录。无论是十几个词条还是百万量级的海量数据，**KVTree 都能让您对“词库里到底有什么词”了如指掌**。


<p align="center">
  <a href="https://github.com/msjsc001/KV-Tree/releases/latest"><img src="https://img.shields.io/github/v/release/msjsc001/KV-Tree"></a>
  <a href="https://github.com/msjsc001/KV-Tree/commits/master"><img src="https://img.shields.io/github/last-commit/msjsc001/KV-Tree"></a>
  <a href="https://github.com/msjsc001/KV-Tree/releases"><img src="https://img.shields.io/github/downloads/msjsc001/KV-Tree/total?label=Downloads&color=brightgreen"></a>
</p>

<p align="center">
  <b>📖 <a href="CHANGELOG.md">查看 KVTree 更新日志 (CHANGELOG)</a></b>
</p>

---

## ✨ 核心特性

- **⚡ 无感热更新**：开启自动监控后，您在 Obsidian/Logseq 按下 `Ctrl+S` 的瞬间，KVTree 会在后台亚秒级完成增量扫描，并将最新词库同步完毕。
- **⚙️ 双引擎过滤控制面板**: 独家原创的“内容剔除”与“整行屏蔽”双选面板，取代老旧的繁琐输入框。支持一行一行分离并配置专属正则黑名单，像剥洋葱一样剥除您笔记中的废话！
- **💻 无级平滑体验**: 原生级渲染系统支持通过鼠标滚轮无限滑动超大数据集列表，并能在关掉后自动记忆您的偏好窗口大小，无需反复拖拽。
- **🌲 智能 AST 树形解析**：摒弃粗暴的正则匹配，采用先进的抽象语法树 (AST) 算法。完美识别 `单行`、`父与子`、`不包含父` 三种复杂的提取逻辑，保证词库结构 100% 还原您的笔记逻辑。
- **🛡️ 生产级数据安全**：**原子级写入技术**确保即便在生成词库的瞬间遭遇突发断电，也绝不会导致词库文件损坏或变成 0KB。
- **🎨 现代化 Fluent 交互设计**：完全摒弃传统丑陋的开源脚本界面。全面引入微软 Fluent Design 设计语言，双标签页布局，带有详尽的悬浮提示帮助（Tips），真正实现“小白式”体验。
- **🔎 支持 Logseq md 版键值识别**：独家支持页面**任意位置**的属性键与值扫描（如键 `keys::` 和值 `[[values]]`），让 Logseq 用户的属性键或带双方的值也能瞬间转化为 QKV 高频词条，方便复用 Logseq md的键值。

---

## 🚀 极速上手指南

一图看懂功能演示V0.5-V0.9版：
<img alt="PixPin_2025-08-26_15-03-21" src="https://github.com/user-attachments/assets/5ca1791c-a537-4a8c-9f71-dd118ff7ff9c" />
<img src="https://github.com/user-attachments/assets/a65d8d84-97b6-413e-89e9-0883df4dbcb9" />

### 第 1 步：标记您的笔记
在任意 `.md` 笔记的行尾，打上 `#KV树-词库名称` 格式的标签。

**提取模式后缀介绍：**
- **默认（无后缀）**：仅将当前这一行提取为单条词条。
- **`-父与子`**：将当前无序列表节点 **及其所有子节点** 全部分别提取为词条。
- **`-不包含父`**：**跳过**当前节点，仅将其下方的所有子节点提取为独立词条。

**举个例子 `待办事项.md`：**
```markdown
- 工作项目 #KV树-我的项目-父与子
    - 撰写报告
    - 回复邮件
- 读书清单 #KV树-我的读书-不包含父
    - 聪明的投资者
    - 漫步华尔街
```

### 第 2 步：一键生成
1. 运行 `kv_tree_app.py` 启动 KVT 控制台界面。
2. **添加笔记源**：点击“添加文件”或“添加文件夹”，将刚才的 `待办事项.md`（或您整个笔记库文件夹）加入左侧监控列表。
3. **设置输出目录**：建议直接选择 [QuickKV](https://github.com/msjsc001/QuickKV) 软件本体下的自动载入文件夹。
4. **启动引擎**：点击【🚀 立即全量扫描并重建词库】！

不出 2 秒，您的指定目录下就会完美生成两个崭新的纯文本词库文件，它们能被快速输入工具无缝读取：

**`#KV树-我的项目.md`**:
```markdown
- 工作项目
- 撰写报告
- 回复邮件
```

**`#KV树-我的读书.md`**:
```markdown
- 聪明的投资者
- 漫步华尔街
```

---

## 🛠️ 纯净运行环境（官方推荐）

为了避免依赖冲突卡顿和数据污染，KVT 为您配置了标准化的 Python 独立虚拟环境（`venv`）。

如果您获取了代码源码，请在主目录下使用终端执行此条命令启动，方可获得最沉浸、最稳固的运行体验：

```powershell
.\venv\Scripts\python kv_tree_app.py
```

## 🧩 极客打包：从零编译为单 EXE 文件

如果您想将其完全便携化发给朋友，在没有 Python 环境的电脑上绿色运行：

1. 激活项目中自带的虚拟环境：
   ```powershell
   .\venv\Scripts\Activate.ps1
   ```
2. 安装编译插件：
   ```powershell
   pip install pyinstaller
   ```
3. 执行无黑窗一键编译：
   ```powershell
   pyinstaller --name "KVTree" --onefile --noconsole --icon="icon.ico" --add-data "icon.ico;." --add-data "src;src" kv_tree_app.py
   ```
4. 稍等片刻后，请在生成的 `dist` 目录下提取专属的 `KVTree.exe`，双击即可无痛运行！
