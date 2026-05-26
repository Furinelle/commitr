# commitr

[English](README.md) · [简体中文](README.zh-CN.md)

AI 生成的 git commit message，**自动学习你项目的风格** —— 语言、格式、scope、emoji、body 习惯都会自适应。通过 [LiteLLM](https://github.com/BerriAI/litellm) 内置 **7 家 AI 提供商**、100+ 模型支持。

> 把改动 `git add`，运行 `commitr`，选 accept / edit / regenerate 即可提交。就这么简单。

**commitr 的差异化优势** —— 更安全、更干净地整理提交：

- **Hunk 级拆分** (`--split --hunks`) —— 在**单个文件内部**也能拆分，不止按文件拆
- **Index-safe 拆分流程** —— 保留 partial staging，不会误把未 staged hunk 一起提交
- **隐私防线** —— prompt 发出前自动脱敏常见密钥，并把 diff 当作不可信数据处理
- **Diff 缓存** —— 同样的 diff 秒级命中，重新生成零 API 成本
- **Issue 上下文** (`--issue N`) —— 模型能看到 issue 标题/正文，知道你**为什么**改，不止**改了什么**
- **PR 模式** (`commitr pr`) —— 同样的风格学习流水线，用于生成 Pull Request 描述

## 支持的 AI 提供商

开箱即用的预设，随时用 `commitr providers` 查看：

| 预设 | 默认模型 | 环境变量 | 备注 |
|---|---|---|---|
| `deepseek` | `deepseek/deepseek-v4-flash` | `DEEPSEEK_API_KEY` | V4 Flash · 1M 上下文 · ~¥1/¥2 每 Mtok · 中文最强 |
| `openai` | `gpt-5.4-mini` | `OPENAI_API_KEY` | GPT-5.4 mini · 质量/成本平衡好 |
| `anthropic` | `claude-haiku-4-5` | `ANTHROPIC_API_KEY` | Haiku 4.5 · 风格匹配最佳，便宜 |
| `gemini` | `gemini/gemini-3.5-flash` | `GEMINI_API_KEY` | Gemini 3.5 Flash · 有免费额度 |
| `mistral` | `mistral/mistral-small-latest` | `MISTRAL_API_KEY` | Mistral Small 4 · 欧盟托管 · $0.15/$0.60 每 Mtok |
| `groq` | `groq/qwen/qwen3-32b` | `GROQ_API_KEY` | Qwen3 32B · 推理速度极快 |
| `ollama` | `ollama/qwen2.5-coder:7b` | — | 本地运行，零成本，零泄露 |

> 默认模型在 **2026 年 5 月**经过验证。其他模型直接用 `--model <litellm-string>` 即可（DeepSeek V4 Pro、Claude Sonnet 4.6、GPT-5.5、Gemini 3.5 Pro 等）。

## 安装

需要 Python ≥ 3.12。

```bash
pip install commitr
```

或者用 [uv](https://github.com/astral-sh/uv)（推荐，会拉一个干净的隔离环境）：

```bash
uv tool install commitr
```

<details>
<summary>从源码安装（开发用）</summary>

```bash
git clone https://github.com/Furinelle/commitr
cd commitr
uv sync
ln -s "$PWD/.venv/bin/commitr" /usr/local/bin/commitr  # 可选：加到 PATH
```

</details>

## 快速开始

零配置路径 —— 只要设个 API key，commitr 会自动检测：

```bash
export DEEPSEEK_API_KEY=sk-...        # （或者 OPENAI_API_KEY、ANTHROPIC_API_KEY ……）

cd /your/project
git add somefile
commitr                                # 使用第一个有 key 的 provider
```

你会看到一个交互式提示：

```
╭── Proposed commit (via deepseek/deepseek-v4-flash) ────╮
│ feat(parser): 处理空 heredoc 边界情况                  │
│                                                        │
│ 原本会抛异常，改为返回空字符串；修复 #42。             │
╰────────────────────────────────────────────────────────╯
? What now?
❯ Accept and commit
  Edit before committing
  Regenerate
  Cancel
```

## 配置

`commitr` 按以下**优先级**读取配置：

1. CLI 参数：`--model` > `--provider`
2. 环境变量：`$COMMITR_MODEL`，以及各 provider 的 key
3. 配置文件：`~/.config/commitr/config.toml`
4. 自动检测：环境里第一个有 key 的 provider

### 一次配好长期使用

```bash
commitr config --init
```

这会创建两个文件：

- `~/.config/commitr/config.toml` —— 选择默认 provider/model
- `~/.config/commitr/.env` —— 放 API key 的地方（自动加载）

`config.toml` 示例：

```toml
[default]
# 注释掉这行让 commitr 根据已配置的 API key 自动检测，
# 或取消注释来固定一个默认 provider。
# provider = "deepseek"
# model = "deepseek/deepseek-reasoner"   # 或指定精确的模型字符串
```

`.env` 示例：

```
DEEPSEEK_API_KEY=sk-...
OPENAI_API_KEY=sk-...
```

### 查看当前配置

```bash
commitr providers     # 列表展示所有预设以及哪些 key 已配置
commitr config        # 显示当前解析出的 model 和配置文件位置
```

## 命令行用法

```bash
commitr                                # 交互模式（默认）
commitr --yes                          # 不询问直接提交（CI 友好）
commitr --dry-run                      # 只打印消息，不提交
commitr --split                        # 文件级多 commit 拆分
commitr --split --hunks                # HUNK 级拆分（文件内部）—— v0.3+
commitr --split --yes                  # 非交互拆分（逐组自动提交）
commitr --issue 42                     # 注入 issue #42 作为上下文（通过 `gh`）
commitr --no-issue                     # 跳过从分支名自动检测 issue
commitr --no-cache                     # 强制重新生成（绕过缓存）
commitr --version                      # 打印版本号
commitr --provider deepseek            # 本次运行用指定 provider
commitr --model deepseek/deepseek-reasoner   # 精确模型覆盖
commitr providers                      # 子命令：列出 provider
commitr config --init                  # 子命令：写入模板配置
commitr style                          # 查看学到的提交风格
commitr doctor                         # 在生成前检查 staged 改动
commitr cache                          # 查看缓存；--clear 清空
commitr pr                             # 生成 PR 标题 + 正文
commitr pr --create                    # ……并通过 `gh pr create` 创建
commitr install-hook                   # 安装 prepare-commit-msg git hook
commitr uninstall-hook                 # 卸载 hook
```

## Git Hook 模式（`commitr install-hook`）

想让普通的 `git commit` 也"自带 AI"？每个仓库装一次 hook 就行：

```bash
cd /your/project
commitr install-hook
```

从此 `git commit`（不带 `-m`）会打开编辑器，里面已经预填好 AI 生成的消息：

```bash
git add some-file
git commit              # 编辑器自动带上 AI 生成的消息
# 修改 / 保存 / 完成
```

- 传 `-m` 时跳过；merge / squash commit 也跳过；`PATH` 里没有 `commitr` 也跳过
- LLM 调用失败时静默退回到空编辑器（不会阻塞你的 commit）
- 随时卸载：`commitr uninstall-hook`

## 智能 commit 拆分（`--split`）

如果你一次 staged 了**一个 feature** + **一个不相关的 bug fix** + **一些文档**，
`commitr --split` 会让模型把 staged 的文件按独立逻辑分组，然后逐组让你确认：

```
╭─ Group 1/3 · 2 file(s) · 给 parser 添加空 heredoc 边界处理 ─╮
│ feat(parser): 处理空 heredoc                                 │
│                                                              │
│ Files:                                                       │
│   src/parser.py                                              │
│   src/utils.py                                               │
╰──────────────────────────────────────────────────────────────╯
? What now?
❯ Commit this group
  Edit message, then commit
  Skip this group
  Stop (abort remaining)
```

- 默认是文件级拆分；加上 `--hunks` 可以**深入到文件内部**（见下文）
- 模型被明确指示"只拆分清晰独立的改动"
- 中途 Stop / Skip 的话，未处理的文件会重新 staged，方便你手动收尾

## 风格学习是怎么做的

每次运行，`commitr` 都会收集：

- 最近 **20 条 commit subject**（用于宽度风格扫描）
- 最近 **5 条完整 commit message**（subject + body，作为 few-shot 示例）

这些会带着明确指令进入 prompt，让模型识别并匹配：**语言、scope 习惯、emoji 习惯、body 习惯、type 词汇**。所以如果你的仓库用中文写 commit、有 `(scope)`、有 gitmoji，生成出来的就是中文 + `(scope)` + gitmoji。

你也可以在不调用 LLM 的情况下查看推断出来的风格：

```bash
commitr style
```

示例输出：

```
╭──────────── Commit style profile ────────────╮
│ Language: Chinese                            │
│ Conventional commits: yes                    │
│ Emoji prefix: no                             │
│ Body usage: occasional                       │
│ Types: feat, fix, docs                       │
│ Scopes: cli, config                          │
╰──────────────────────────────────────────────╯
```

## Commit doctor

在调用模型之前，可以先跑一次本地预检：

```bash
commitr doctor
```

`doctor` 能捕获这些确定性的问题：

- 没有 staged 改动
- 没配置 model / provider
- staged 了二进制文件（模型看不到内容）
- diff 过大（可能丢失细节）
- 只 staged 了 lockfile（可能漏 staged 真正的依赖改动）

主 commit 流程会自动跑一次 doctor —— `error` 级别的发现会在调用 API 前短路退出，省钱。

## Issue 上下文（`--issue`）

`commitr` 知道**为什么改**比**改了什么**更重要。指向一个 issue，模型在写消息时就能看到该 issue 的标题、正文、标签、状态：

```bash
commitr --issue 42                     # 显式指定
commitr                                # 在 feat/42-foo 分支上会自动检测并注入
commitr --no-issue                     # 关闭自动检测
```

自动检测支持以下常见分支命名：`feat/123-name`、`fix-issue-42-crash`、`gh-777`、`issue/9000`。底层用 `gh` 命令调用 GitHub API，所以你需要先安装并登录 `gh`。如果 `gh` 不可用，会静默跳过，不会阻塞你的 commit。

## Diff 缓存

相同的 diff 会得到相同的消息。缓存命中时秒级返回，零 API 调用 —— 对于 regenerate、doctor、staged 反复折腾的场景特别有用：

```bash
commitr cache                          # 查看条目数 + 占用
commitr cache --clear                  # 全部清空
commitr --no-cache                     # 本次绕过缓存
```

缓存位置：`~/.cache/commitr/`（或 `$XDG_CACHE_HOME/commitr/`）。LRU-by-mtime 策略，7 天 TTL，200 条上限。模型 / diff / 仓库风格变化时自动失效。

## PR 描述模式（`commitr pr`）

同样的风格学习流水线，但用来生成 Pull Request —— 从你仓库最近的 merged PR 标题里学风格，结合本分支的 commits + diff：

```bash
commitr pr                             # 仅打印
commitr pr --create                    # 一次性生成 + `gh pr create`
commitr pr --base origin/develop       # 用不同 base 分支
```

## Hunk 级拆分（`--split --hunks`）

Roadmap 的招牌功能。`commitr --split` 默认按**文件**分组成独立 commit。加上 `--hunks` 就能深入一层 —— 在**单个文件内部**也能拆：

```bash
git add big-refactor.py                # 这个文件里有 3 个不相关的 hunk
commitr --split --hunks
# → group 1: hunks #0 + #2（feature 部分）
# → group 2: hunk #1（不相关的 bug fix）
# 每组通过 `git apply --cached` 单独 stage 然后 commit
```

重命名、二进制 diff、mode 变更会保持原子（不拆）。如果模型解析失败或返回乱码，未提交的 hunk 会被重新 stage 让你手动完成。

## Roadmap

- [x] MVP：读取 staged diff → LLM → 交互 accept/edit/regen → commit
- [x] 从 `git log` 学风格
- [x] 多 provider 预设 + 配置文件 + `.env` 加载
- [x] 智能 commit 拆分（文件级，`--split`）
- [x] `prepare-commit-msg` git hook 模式（`commitr install-hook`）
- [x] 可选 `Co-Authored-By` trailer（每个仓库独立开关）
- [x] 本地 `style` / `doctor` 检查命令
- [x] Hunk 级 commit 拆分（文件内部）—— v0.3
- [x] Diff 缓存（相同 diff 不重复调用 LLM）—— v0.3
- [x] Issue 上下文注入（`--issue N` + 分支自动检测）—— v0.3
- [x] PR 描述模式（`commitr pr`）—— v0.3
- [ ] 语义级 diff 降噪（自动过滤 import 重排、空白等）
- [ ] 团队策略文件（`.commitr.toml`）
- [ ] Monorepo 每个 package 独立的风格 profile
- [ ] 多 provider 竞速模式（`--race openai,anthropic,deepseek`）
- [ ] `commitr lint` —— 给历史 commit 评分并建议改写
- [ ] macOS Raycast 扩展，一键 commit
- [ ] Homebrew tap

## 项目结构

```
src/commitr/
├── __init__.py   # Typer CLI：callback + 子命令
├── cache.py      # 本地消息缓存（LRU + TTL）
├── config.py     # provider 预设、config & .env 加载、模型解析
├── doctor.py     # staged diff 本地预检
├── git.py        # git 子命令的薄封装
├── hook.py       # prepare-commit-msg 安装 / 卸载 / 填充
├── hunks.py      # hunk 级 diff 解析 + 分组（`--split --hunks`）
├── issue.py      # 分支 → issue 号自动检测 + `gh` 抓取上下文
├── llm.py        # LiteLLM 调用 + 风格化 prompt + 缓存
├── pr.py         # PR 标题 + 正文生成（`commitr pr`）
├── splitter.py   # LLM 驱动的文件级多 commit 分组（`--split`）
└── style.py      # 从 commit 历史推断风格
```

## License

MIT。
