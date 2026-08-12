# skill-browser

[English](README.md) | [简体中文](README.zh-CN.md)

[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-3776AB.svg)](https://www.python.org/)
[![Agent Skill](https://img.shields.io/badge/Agent%20Skill-compatible-5B5BD6.svg)](https://agentskills.io/)

面向本机已安装 Agent Skills 的只读导航器。

`skill-browser` 实时扫描本机 Skill 目录，提取可复核的来源事实，帮助 Agent 解释、比较、搜索或推荐本地 Skills，但不会执行它们。它把确定性的盘点事实与导航判断明确分开，来源无法支持的信息会保留为待确认。

![skill-browser 将本机实时 Skill 集合转化为来源事实、导航判断和待确认项](illustrations/01-infographic-skill-browser-overview.png)

**快速导航：** [为什么需要它](#为什么需要-skill-browser) · [工作机制](#工作机制) · [调用方式](#调用方式) · [安装](#安装) · [信任边界](#信任与隐私边界) · [开发与校验](#开发与校验)

## 为什么需要 skill-browser

本机 Skill 数量增加后，三个问题会越来越难回答：

- 现在究竟安装了什么？
- 哪个 Skill 真正适合当前任务，而不只是碰巧命中了关键词？
- 哪些结论来自 Skill 文件，哪些只是 Agent 的解释？

`skill-browser` 每次调用都会重新生成结构化盘点结果。它能合并软链接形成的重复安装、报告同名冲突、保留宿主可见性，并提供足够的来源证据供 Agent 谨慎导航。

它不是包管理器或市场，不负责安装、更新、删除、发布、评分、安全打分或执行其他 Skills。

## 工作机制

![skill-browser 的实时扫描与证据处理流程](illustrations/02-infographic-live-scan-evidence.png)

1. 从当前工作目录出发，发现指定宿主可见的 Skill 目录。
2. 限量读取 UTF-8 `SKILL.md`，解析元数据、标题、选项、资源和直接引用。
3. 返回确定性的来源事实、警告、冲突和来源哈希。
4. 由调用它的 Agent 补充明确标注的分类、排序、适配性和取舍判断。
5. 证据缺失或两侧信息不对称时保留为待确认，不用假设填补空白。

扫描器不会创建持久索引；新安装或更新的 Skill 会在下一次调用时出现。

## 证据模型

| 证据类别 | 含义 | 示例 |
|---|---|---|
| 来源事实 | 直接从选定的本地文件解析 | 名称、描述、标题、已记录选项、资源、宿主可见性 |
| 导航判断 | Agent 针对当前任务补充 | 分类、首选项、适配性、取舍 |
| 待确认 | 扫描来源无法证明 | 未记录行为、输出质量、兼容性声明 |

词法搜索分数只用于发现候选，不代表语义推荐、质量评分、流行度排行或官方 Skill 元数据。

## 调用方式

在 `$skill-browser` 或 `/skill-browser` 后输入的内容决定具体工作流：

| 调用示例 | 返回结果 |
|---|---|
| `$skill-browser` | 精简能力地图 |
| `$skill-browser <skill>` | 单个 Skill 详情页 |
| `$skill-browser <skill> options` | 已记录的选项分组 |
| `$skill-browser compare <skill-a> <skill-b>` | 基于双方证据的比较 |
| `$skill-browser search <query>` | 检索名称、描述和标题 |
| `$skill-browser recommend <task>` | 最多三个候选、明确首选和主要取舍 |

本仓库的所有示例均使用虚构 Skill 名称。

## 安装

使用 [`npx skills`](https://github.com/vercel-labs/skills) 安装：

```bash
npx skills add zz-zed/skill-browser
```

如需安装到用户级共享目录：

```bash
npx skills add zz-zed/skill-browser -g
```

仓库中只有一个 Skill，位于 `skills/skill-browser/`，因此无需额外指定 `--skill`。

## 通过 Agent 使用

Codex 使用 `$` 前缀：

```text
$skill-browser
$skill-browser diagram-skill
$skill-browser compare diagram-skill architecture-skill
$skill-browser recommend 适合编辑现有表格的 Skill
$skill-browser search 可编辑流程图
```

Claude Code 使用 `/` 前缀：

```text
/skill-browser
/skill-browser compare skill-a skill-b
```

随包提供的 Codex 界面元数据关闭了隐式调用。用户需要显式启动导航器、审阅推荐结果，再单独决定是否调用最终选中的 Skill。

## 直接使用扫描器

随包提供的扫描器只使用 Python 标准库：

```bash
python3 skills/skill-browser/scripts/skill_browser.py \
  --host codex \
  --cwd "$PWD" \
  list
```

常用聚焦命令：

```bash
python3 skills/skill-browser/scripts/skill_browser.py --host codex --cwd "$PWD" show <skill>
python3 skills/skill-browser/scripts/skill_browser.py --host codex --cwd "$PWD" options <skill>
python3 skills/skill-browser/scripts/skill_browser.py --host codex --cwd "$PWD" compare <skill-a> <skill-b>
python3 skills/skill-browser/scripts/skill_browser.py --host codex --cwd "$PWD" search <query>
python3 skills/skill-browser/scripts/skill_browser.py --host codex --cwd "$PWD" recommend <task>
```

使用 `--format text` 获取精简输出，使用 `--root <目录>` 增加额外 Skill 容器，使用 `--host all` 明确执行跨宿主盘点，或使用 `--include-self` 诊断扫描器自身。

## 默认扫描范围

| 宿主筛选 | 用户级目录 | 项目级目录 |
|---|---|---|
| `codex` | `~/.agents/skills`、`~/.codex/skills` | 从当前目录到仓库根目录沿途的 `.agents/skills` |
| `claude` | `~/.claude/skills` | 从当前目录到仓库根目录沿途的 `.claude/skills` |
| `all` | 以上全部目录 | 以上全部目录 |

通过 `--root` 传入的目录按自定义根目录处理。指向同一物理 Skill 目录的软链接会合并；名称相同但物理目录不同的 Skill 会保持独立并报告冲突。

## 信任与隐私边界

![skill-browser 的只读执行与隐私边界](illustrations/03-infographic-trust-boundary.png)

扫描器将所有被扫描字符串视为不可信数据。它只解析文本，不会遵循其他 Skill 内的指令，也不会执行其中出现的命令；它不发起网络请求，也不写入持久盘点索引。

防护行为包括：

- 每个 `SKILL.md` 最多读取 2 MiB
- 校验 UTF-8，单个 Skill 失败不会中断整体扫描
- 阻止解析逃逸出物理 Skill 目录的本地引用
- 将失效链接和不可读目录记录为警告，不让整体扫描失败
- 提供 SHA-256 来源哈希，便于识别具体版本

扫描结果仍可能包含本机绝对路径、描述、标题、选项名和来自私有 Skill 的受限长度摘录。公开分享日志、Issue 或报告前，应先检查并脱敏。

## 环境要求

- Python 3.9 或更高版本
- 兼容 Agent Skills 的编程 Agent
- 可选：用于仓库安装和发现检查的 Node.js 与 `npx`

运行时扫描器没有第三方 Python 依赖。

## 开发与校验

运行单元测试：

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

使用 Agent Skills 参考实现校验 Skill：

```bash
agentskills validate skills/skill-browser
```

只验证仓库发现结果，不执行安装：

```bash
npx skills add . --list
```

贡献要求见 [CONTRIBUTING.md](CONTRIBUTING.md)，漏洞报告方式见 [SECURITY.md](SECURITY.md)。本项目遵循 [Agent Skills 规范](https://github.com/agentskills/agentskills/blob/main/docs/specification.mdx)。
