#!/usr/bin/env python3
"""openspec-wiki 同步状态工具

职责边界：只做「确定性记账」，不做内容生成。
- plan   ：扫描 openspec/（+ 项目结构）与 wiki/.wiki-manifest.json 账本，输出本次要做什么（JSON）。
- commit ：生成完成后，把已处理的 artifact / capability / change 记入账本。

增量机制（与账本联动，全部只比 sha256，不做内容比对）：
1. syncedChanges —— 每个已写入 changelog 的归档变更按 Change ID 记账；
   新归档变更 = 账本里查不到的 archive 目录。
2. specs —— 每个已生成能力页按 spec.md 的 sha256 记账；哈希变化即为漂移
   （含「绕过 OpenSpec 流程直改 spec」的情况）。
3. decisions —— 每个已提取进 decisions.md 的变更按 design.md 的 sha256 记账；
   有 design.md 却不在账本里的变更即 pendingDecisions。
4. architectureHash —— 架构页事实源组合哈希：总览源 + config.yaml + 项目目录结构
   + 依赖文件 + 能力名集合 + 全部 design.md 的「约束 / Non-Goals」节。
5. glossaryHash —— 术语表事实源组合哈希：能力名 + 各 spec 的 Purpose 段
   + Requirement 标题 + 行内代码标识符。
6. overviewHash —— 总览（README）事实源哈希。
7. apiHash / dataModelHash / integrationHash —— 声明类提取结果哈希（见下）。

声明类提取（extract 子命令）
   只读「声明」，不解析函数体实现逻辑：路由装饰器与函数签名、权限依赖、
   DDL / ORM 模型、外部调用点、URL 线索、依赖清单。
   覆盖 FastAPI / Flask / Express / Koa / Spring 与裸 DDL / SQLAlchemy / JPA；
   未命中即降级为待补占位。自测 / mock / 种子示例文件归入 auxiliary，不进哈希。
   哈希会剥离行号——行号随无关编辑漂移，不能当触发信号。

用法：
  python3 wiki_state.py plan <project_dir>
  python3 wiki_state.py commit <project_dir> [--caps a,b] [--change-ids x,y] \\
      [--remove-caps a,b] [--decisions x,y] [--overview] [--architecture] \\
      [--glossary] [--api] [--data-model] [--integrations]
  python3 wiki_state.py extract <project_dir> [--only api,dataModel,integrations]
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

MANIFEST_NAME = ".wiki-manifest.json"
MANIFEST_VERSION = 2

# 项目结构扫描时忽略的目录：依赖、构建产物、VCS、工具缓存与本技能自身产物
IGNORE_DIRS = {
    "node_modules", "__pycache__", "dist", "build", "target", "out",
    ".venv", "venv", "env", "vendor", "coverage", "htmlcov", ".next", ".nuxt",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".idea", ".vscode",
    ".workbuddy", "wiki", "openspec", ".tox", ".gradle", ".cache",
}

# 参与架构页哈希的依赖 / 构建 / 启动文件（按目录名 + 文件名查找，最多两层）
DEP_FILES = [
    "requirements.txt", "pyproject.toml", "Pipfile", "poetry.lock", "setup.py",
    "package.json", "pom.xml", "build.gradle", "go.mod", "Cargo.toml", "Gemfile",
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    "Makefile", "start.sh", "run.sh", "deploy.sh",
    "tsconfig.json", "vite.config.js", "vite.config.ts", "next.config.js",
]

HEADING_LINE_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
BOLD_LABEL_RE = re.compile(r"^\s*(?:\*\*|__)\s*([^:：*_\n]{1,40}?)\s*[:：]?\s*(?:\*\*|__)\s*$")
PLAIN_LABEL_RE = re.compile(r"^([A-Za-z\u4e00-\u9fa5][^:：\n]{0,38})[:：]\s*$")
CONSTRAINT_TITLE_RE = re.compile(
    r"约束|前提|限制|非目标|不做|不引入|Constraints?|Boundaries|Non-?Goals", re.IGNORECASE)
NON_GOAL_TITLE_RE = re.compile(r"非目标|不做|不引入|Non-?Goals", re.IGNORECASE)
PURPOSE_TITLE_RE = re.compile(r"^Purpose$|^目标$|^目的$", re.IGNORECASE)
AUX_FILE_RE = re.compile(
    r"(^|/)(selftest|test|tests|spec|conftest|mock|seed|sample|demo|fixture)[^/]*\.|"
    r"_test\.|\.test\.|\.spec\.", re.IGNORECASE)


def die(msg, code=1):
    print(json.dumps({"error": msg}, ensure_ascii=False))
    sys.exit(code)


_BYTES_CACHE = {}


def read_bytes(path):
    """带缓存的字节读取：单次运行内同一文件只读一次盘。

    哈希与正文解析共用这一份字节（sha256 仍按原始字节计算，保证与既有账本语义一致），
    避免同一文件被读两遍——在每次 open 都有固定开销的环境里差别显著。
    """
    if path not in _BYTES_CACHE:
        try:
            with open(path, "rb") as f:
                _BYTES_CACHE[path] = f.read()
        except OSError:
            _BYTES_CACHE[path] = b""
    return _BYTES_CACHE[path]


def sha256_file(path):
    return hashlib.sha256(read_bytes(path)).hexdigest()


def read_text(path):
    return read_bytes(path).decode("utf-8", "replace")


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_manifest(wiki_dir):
    path = os.path.join(wiki_dir, MANIFEST_NAME)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def save_manifest(wiki_dir, manifest):
    os.makedirs(wiki_dir, exist_ok=True)
    path = os.path.join(wiki_dir, MANIFEST_NAME)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")


def extract_blocks(text):
    """把 markdown 切成「标题 → 正文」块。

    同时识别三种块起始写法，因为设计文档里三种混用：
      1. Markdown 标题：`## 约束`
      2. 粗体标签：`**Non-Goals:**`
      3. 纯文本标签：`约束：`
    只切块、不判断语义；调用方用标题正则过滤。
    """
    blocks, cur = [], None
    for line in text.splitlines():
        kind = title = None
        m = HEADING_LINE_RE.match(line)
        if m:
            kind, title = "heading", m.group(2).strip()
        else:
            bm = BOLD_LABEL_RE.match(line)
            if bm:
                kind, title = "label", bm.group(1).strip()
            else:
                pm = PLAIN_LABEL_RE.match(line)
                if pm:
                    kind, title = "label", pm.group(1).strip()
        if kind:
            if cur:
                blocks.append(cur)
            cur = {"title": title, "kind": kind, "body": []}
            continue
        if cur is not None:
            cur["body"].append(line)
    if cur:
        blocks.append(cur)
    return [{"title": b["title"], "kind": b["kind"],
             "body": "\n".join(b["body"]).strip()} for b in blocks]


def extract_sections(text, title_re):
    """返回标题命中 title_re 的块正文（标题、粗体标签、纯文本标签三种写法均可）。"""
    return [b["body"] for b in extract_blocks(text)
            if b["body"] and title_re.search(b["title"])]


def extract_change_id(change_dir):
    """依次尝试：proposal.md 的 Change ID 段 → .openspec.yaml 的 id/name → 目录名去日期前缀。"""
    proposal = os.path.join(change_dir, "proposal.md")
    text = read_text(proposal)
    m = re.search(r"##\s*Change ID\s*\n+\s*([^\s#][^\n]*)", text)
    if m:
        return m.group(1).strip()
    meta = os.path.join(change_dir, ".openspec.yaml")
    mtext = read_text(meta)
    m = re.search(r"^(?:id|name):\s*([^\s#]+)", mtext, re.MULTILINE)
    if m:
        return m.group(1).strip()
    base = os.path.basename(change_dir.rstrip("/"))
    return re.sub(r"^\d{4}-\d{2}-\d{2}-", "", base)


def extract_capabilities(change_dir):
    """变更涉及的能力 = 变更内 delta specs 目录 ∪ proposal.md Capabilities 段中列出的能力（含 REMOVED）。"""
    caps = []
    spec_root = os.path.join(change_dir, "specs")
    if os.path.isdir(spec_root):
        for name in sorted(os.listdir(spec_root)):
            if os.path.isfile(os.path.join(spec_root, name, "spec.md")):
                caps.append(name)
    proposal = os.path.join(change_dir, "proposal.md")
    text = read_text(proposal)
    m = re.search(r"##\s*Capabilities\s*\n(.*?)(?=\n##\s|\Z)", text, re.DOTALL)
    if m:
        for line in m.group(1).splitlines():
            cm = re.match(r"[-*]\s*`?([A-Za-z0-9][A-Za-z0-9_-]*)`?", line.strip())
            if cm and cm.group(1) not in caps:
                caps.append(cm.group(1))
    return caps


def scan_change_dirs(openspec_dir):
    """仅做目录级扫描（不读 proposal.md）。

    返回 (archived, active)：每个元素 {dir, date, design, designHash}。
    id / capabilities 由 resolve_change() 惰性补全——已同步的变更无需再解析，
    这也是稳态下 plan 快的原因。
    """
    changes_root = os.path.join(openspec_dir, "changes")
    archived_root = os.path.join(changes_root, "archive")
    date_re = re.compile(r"^(\d{4}-\d{2}-\d{2})")

    def build(cdir, rel_dir, date):
        design = os.path.join(cdir, "design.md")
        has_design = os.path.isfile(design)
        return {
            "dir": rel_dir,
            "date": date,
            "design": has_design,
            "designHash": sha256_file(design) if has_design else None,
        }

    archived = []
    if os.path.isdir(archived_root):
        for name in sorted(os.listdir(archived_root)):
            cdir = os.path.join(archived_root, name)
            if not os.path.isdir(cdir):
                continue
            m = date_re.match(name)
            archived.append(build(cdir, os.path.join("changes", "archive", name),
                                  m.group(1) if m else ""))

    active = []
    if os.path.isdir(changes_root):
        for name in sorted(os.listdir(changes_root)):
            if name == "archive":
                continue
            cdir = os.path.join(changes_root, name)
            if not os.path.isdir(cdir):
                continue
            active.append(build(cdir, os.path.join("changes", name), ""))
    return archived, active


def resolve_change(openspec_dir, entry):
    """惰性补全 change 的 id 与 capabilities（需要读 proposal.md，已读则走缓存）。"""
    cdir = os.path.join(openspec_dir, entry["dir"])
    entry["id"] = extract_change_id(cdir)
    entry["capabilities"] = extract_capabilities(cdir)
    return entry


def change_slug(entry):
    """目录名去掉日期前缀——即从目录名可直接推出的 Change ID。"""
    return re.sub(r"^\d{4}-\d{2}-\d{2}-", "", os.path.basename(entry["dir"].rstrip("/")))


def change_key(entry):
    """用于排序 / 记账的稳定标识：优先已解析的 id，否则用目录 slug（不触盘）。"""
    return entry.get("id") or change_slug(entry)


def overview_sources(project_dir, openspec_dir):
    """总览页事实源：openspec/project.md 优先，其次项目 README.md；config.yaml 始终参与。"""
    items = []
    proj_md = os.path.join(openspec_dir, "project.md")
    readme = os.path.join(project_dir, "README.md")
    if os.path.isfile(proj_md):
        items.append(("openspec/project.md", proj_md))
    elif os.path.isfile(readme):
        items.append(("README.md", readme))
    config = os.path.join(openspec_dir, "config.yaml")
    if os.path.isfile(config):
        items.append(("openspec/config.yaml", config))
    return items


def overview_hash(project_dir, openspec_dir):
    h = hashlib.sha256()
    for label, path in overview_sources(project_dir, openspec_dir):
        h.update(("S:" + label + "\n").encode("utf-8"))
        try:
            with open(path, "rb") as f:
                h.update(f.read())
        except OSError:
            pass
        h.update(b"\n")
    return h.hexdigest()


def structure_digest(project_dir, max_depth=2):
    """项目目录结构 + 依赖文件内容的哈希。只取目录名（不读业务代码），稳定且轻量。"""
    dirs = []

    def walk(base, rel, depth):
        if depth > max_depth:
            return
        try:
            names = sorted(os.listdir(base))
        except OSError:
            return
        for n in names:
            if n.startswith(".") or n in IGNORE_DIRS:
                continue
            p = os.path.join(base, n)
            if os.path.isdir(p):
                dirs.append(rel + n)
                walk(p, rel + n + "/", depth + 1)

    walk(project_dir, "", 1)
    h = hashlib.sha256()
    for d in dirs:
        h.update(("D:" + d + "\n").encode("utf-8"))
    seen = set()
    for d in [""] + [x for x in dirs if x.count("/") <= 1]:
        base = os.path.join(project_dir, d)
        for fn in DEP_FILES:
            p = os.path.join(base, fn)
            if os.path.isfile(p) and p not in seen:
                seen.add(p)
                h.update(("F:" + os.path.relpath(p, project_dir) + "\n").encode("utf-8"))
                h.update(read_text(p)[:20000].encode("utf-8"))
                h.update(b"\n")
    return h.hexdigest()


def constraint_digest(openspec_dir, archived, active):
    """全部 design.md 的「约束 / 前提 / Non-Goals」节组合哈希。"""
    h = hashlib.sha256()
    for ch in sorted(archived + active, key=change_key):
        if not ch["design"]:
            continue
        text = read_text(os.path.join(openspec_dir, ch["dir"], "design.md"))
        blocks = extract_sections(text, CONSTRAINT_TITLE_RE)
        if not blocks:
            continue
        h.update(("C:" + change_key(ch) + "\n").encode("utf-8"))
        for b in blocks:
            h.update(b.encode("utf-8"))
            h.update(b"\n")
    return h.hexdigest()


def architecture_hash(project_dir, openspec_dir, caps, archived, active):
    h = hashlib.sha256()
    h.update(b"--overview--\n")
    h.update(overview_hash(project_dir, openspec_dir).encode("utf-8"))
    h.update(b"\n--structure--\n")
    h.update(structure_digest(project_dir).encode("utf-8"))
    h.update(b"\n--capabilities--\n")
    for cap in caps:
        h.update((cap + "\n").encode("utf-8"))
    h.update(b"--constraints--\n")
    h.update(constraint_digest(openspec_dir, archived, active).encode("utf-8"))
    return h.hexdigest()


def glossary_digest(openspec_dir, caps):
    """术语表事实源哈希：能力名 + Purpose 段 + Requirement 标题 + 行内代码标识符。"""
    h = hashlib.sha256()
    for cap in caps:
        text = read_text(os.path.join(openspec_dir, "specs", cap, "spec.md"))
        h.update(("C:" + cap + "\n").encode("utf-8"))
        for b in extract_sections(text, PURPOSE_TITLE_RE):
            h.update(b.encode("utf-8"))
            h.update(b"\n")
        for m in re.finditer(r"^#{2,4}\s*(?:Requirement|需求)[:：]?\s*(.*)$", text, re.MULTILINE):
            h.update(("R:" + m.group(1).strip() + "\n").encode("utf-8"))
        for ident in sorted(set(re.findall(r"`([^`\n]{1,60})`", text))):
            h.update(("I:" + ident + "\n").encode("utf-8"))
    return h.hexdigest()


# ---------------------------------------------------------------------------
# 声明类提取（extract）
#   只扫描「声明」：路由装饰器与函数签名、DDL / ORM 模型、外部调用行、依赖清单。
#   不解析函数体实现逻辑（不看 if/for、不追调用链、不读算法）。
#   提取结果一份两用：
#     1) 计算 apiHash / dataModelHash / integrationHash，用于增量判定；
#     2) extract 子命令直接输出，供 LLM 组织成页面，避免重复读码。
#   提取是启发式模式匹配（非编译器级解析）：未命中即降级为「待补占位」，不报错。
# ---------------------------------------------------------------------------

SOURCE_EXTS = (".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".vue",
               ".java", ".kt", ".go", ".rb", ".php", ".cs", ".sql")
MAX_SOURCE_FILES = 600
MAX_SOURCE_BYTES = 512 * 1024
SOURCE_SKIP_DIRS = set(IGNORE_DIRS) | {"tests", "test", "__tests__", "spec",
                                       "e2e", "migrations_bak"}

# 路由声明
ROUTER_PREFIX_RE = re.compile(
    r'(?P<obj>\w+)\s*=\s*[\w.]*(?:APIRouter|Blueprint)\s*\((?P<args>[^)]*)\)')
ROUTE_DECORATOR_RE = re.compile(
    r'@(?P<obj>\w+)\.(?P<method>get|post|put|patch|delete|head|options|route)\s*\('
    r'(?P<args>[^)]*)\)')
EXPRESS_ROUTE_RE = re.compile(
    r'^\s*(?P<obj>[\w.]+)\.(?P<method>get|post|put|patch|delete|all|use)\s*\(\s*'
    r'[\'"](?P<path>[/\*][^\'"]*)[\'"]', re.MULTILINE)
SPRING_MAPPING_RE = re.compile(
    r'@(?P<method>Get|Post|Put|Patch|Delete)Mapping\s*\(\s*'
    r'(?:value\s*=\s*|path\s*=\s*)?[\'"](?P<path>[^\'"]*)[\'"]')
SPRING_CLASS_RE = re.compile(
    r'@RequestMapping\s*\(\s*(?:value\s*=\s*)?[\'"](?P<path>[^\'"]*)[\'"]')
ARG_STR_RE = re.compile(r'[\'"`]([^\'"`]*)[\'"`]')
PREFIX_KW_RE = re.compile(r'prefix\s*=\s*[\'"](?P<prefix>[^\'"]*)[\'"]')
PY_DEF_RE = re.compile(
    r'^(?P<indent>[ \t]*)(?:async\s+)?def\s+(?P<name>\w+)\s*'
    r'\((?P<sig>[^()]*(?:\([^()]*\)[^()]*)*)\)\s*(?:->[^:\n]*)?:', re.MULTILINE)
JS_FN_RE = re.compile(
    r'^\s*(?:export\s+)?(?:async\s+)?function\s+(?P<name>\w+)\s*\((?P<sig>[^)]*)\)',
    re.MULTILINE)
JS_ARROW_RE = re.compile(
    r'^\s*(?:export\s+)?(?:const|let|var)\s+(?P<name>\w+)\s*=\s*(?:async\s*)?\('
    r'(?P<sig>[^)]*)\)\s*=>', re.MULTILINE)
ROLE_ALIAS_RE = re.compile(
    r'(?P<alias>\w+)\s*=\s*[\w.]*require_roles\s*\(\s*(?P<roles>[^)]*)\)')
DEPENDS_ARG_RE = re.compile(r'Depends\s*\(\s*(?P<dep>\w+)')
INLINE_ROLES_RE = re.compile(r'require_roles\s*\(\s*(?P<roles>[^)]*)\)')
AUTH_HINT_RE = re.compile(
    r'@PreAuthorize\s*\((?P<expr>[^)]*)\)|@RolesAllowed\s*\((?P<roles>[^)]*)\)|'
    r'require_roles|require_login|require_admin|authenticate|authMiddleware',
    re.IGNORECASE)

# 数据模型声明
DDL_TABLE_RE = re.compile(
    r'CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+["`\[]?(?P<name>[\w.]+)["`\]]?\s*\(',
    re.IGNORECASE)
DDL_INDEX_RE = re.compile(
    r'CREATE\s+(?:UNIQUE\s+)?INDEX(?:\s+IF\s+NOT\s+EXISTS)?\s+["`\[]?(?P<name>[\w.]+)',
    re.IGNORECASE)
DDL_ALTER_RE = re.compile(
    r'ALTER\s+TABLE\s+["`\[]?(?P<name>[\w.]+)["`\]]?\s+(?P<action>ADD|DROP|RENAME|MODIFY)',
    re.IGNORECASE)
ORM_TABLENAME_RE = re.compile(r'__tablename__\s*=\s*[\'"](?P<name>\w+)[\'"]')
ORM_CLASS_RE = re.compile(
    r'class\s+(?P<cls>\w+)\s*\(\s*(?:Base|db\.Model|models\.Model|DeclarativeBase|'
    r'SQLModel|Model)\b[^)]*\)')
JPA_ENTITY_RE = re.compile(
    r'@Entity\b|@Table\s*\(\s*name\s*=\s*[\'"](?P<name>[^\'"]+)[\'"]')

# 外部集成声明
HTTP_CALL_RE = re.compile(
    r'\b(?P<lib>httpx|requests|aiohttp|axios|got|superagent|urllib\.request)\s*\.?\s*'
    r'(?P<method>get|post|put|patch|delete|head|request|stream)?\s*\(', re.IGNORECASE)
SDK_HINT_RE = re.compile(
    r'\b(?P<sdk>from\s+openai|import\s+openai|AzureOpenAI|Anthropic|boto3|dashscope|'
    r'zhipuai|ollama|tencentcloud|aliyunsdk|feishu|dingtalk|wecom)\b')
MQ_HINT_RE = re.compile(
    r'\b(?P<mq>redis|aioredis|StrictRedis|pika|aio_pika|amqp|KafkaProducer|'
    r'KafkaConsumer|confluent_kafka|celery|Celery|rocketmq|pulsar|nats|ActiveMQ|'
    r'RabbitMQ|RabbitTemplate|kombu)\b')
PROC_CALL_RE = re.compile(
    r'subprocess\.(?:run|Popen|call|check_output|check_call)\s*\(|'
    r'child_process\.(?:exec|spawn|execSync|spawnSync)\s*\(')
CLIENT_INIT_RE = re.compile(
    r'\b(?P<lib>httpx|requests|aiohttp)\s*\.\s*(?P<cls>[A-Z]\w*Client|Session)\s*\(|'
    r'\bnew\s+(?P<jscls>OpenAI|Anthropic|Axios|Kafka|Redis|Client)\s*\(|'
    r'\b(?P<pylib>Redis|StrictRedis|KafkaProducer|KafkaConsumer|ConnectionPool|'
    r'motor_client|AsyncIOMotorClient)\s*\(')
URL_RE = re.compile(r'https?://[^\s\'"`\)\]\},]+')
ENDPOINT_KEY_RE = re.compile(
    r'(?P<key>[A-Z][A-Z0-9_]{2,40}(?:_URL|_ENDPOINT|_HOST|_BASE|_URI))\s*[:=]\s*'
    r'[\'"](?P<url>[^\'"]+)[\'"]')

# 请求 / 响应字段结构（声明类提取：字段名 / 类型 / 必填 / 来源）
DDL_COLUMN_RE = re.compile(
    r"^\s*[\`\[]?(?P<name>[A-Za-z_]\w*)[\`\]]?\s+"
    r"(?P<type>[A-Za-z]+(?:\s*\([^)]*\))?)(?P<rest>.*)$")
# 表级约束行（PRIMARY KEY(a,b) / UNIQUE(a) / CHECK(...) / FOREIGN KEY ... / KEY idx(a)）。
# 注意：不能把名为 key 的普通列（key TEXT PRIMARY KEY）误判成 KEY 索引定义，
# 因此 KEY / INDEX 只在后面直接跟「(」或「索引名 (」时才认定为表级约束。
DDL_TABLE_CONSTRAINT_RE = re.compile(
    r"^\s*(?:CONSTRAINT\s+[\`\"]?\w+[\`\"]?\s+)?"
    r"(?:PRIMARY\s+KEY|UNIQUE|FOREIGN\s+KEY|CHECK|EXCLUDE)\b", re.IGNORECASE)
DDL_TABLE_INDEX_RE = re.compile(
    r"^\s*(?:KEY|INDEX)\s+(?:\w+\s*)?\(", re.IGNORECASE)
DDL_CONCAT_STR_RE = re.compile(r'["\']\s*["\']')
# 常量名形如 _ALTER_COLUMNS / MIGRATION_COLUMNS 的模块级列表，元素为
# (表名, 列名, 列定义) 三元组——存量表补列的常见写法（动态拼 ALTER TABLE，
# 字符串里看不到表名，只能从这份声明清单还原有效列集）。
ALTER_COLUMN_LIST_RE = re.compile(
    r"(?m)^[ \t]*(?P<var>[A-Za-z_][A-Za-z0-9_]*(?:ALTER|COLUMN|MIGRAT)[A-Z0-9_]*)\s*=\s*\["
    r"(?P<body>[\s\S]*?)^\]")
ALTER_TRIPLE_RE = re.compile(
    r"^\s*\(\s*[\'\"](?P<table>[A-Za-z_]\w*)[\'\"]\s*,\s*"
    r"[\'\"](?P<column>[A-Za-z_]\w*)[\'\"]\s*,\s*"
    r"(?P<coldef>.+?)\s*\)\s*,?\s*$", re.M)
BODY_PARAM_DECL_RE = re.compile(
    r"(?P<name>[A-Za-z_]\w*)\s*:\s*(?:dict|Dict\[|Mapping\b|Any\b|Body\b)")
BODY_PARAM_NAMES = ("payload", "body", "data", "payload_json", "req_body", "params", "form")
PARAM_ACCESS_RE = re.compile(
    r"(?P<param>[A-Za-z_]\w*)\s*\.\s*get\s*\(\s*[\'\"](?P<key>[A-Za-z_]\w*)[\'\"]"
    r"\s*(?P<rest>[^()]*)\)"
    r"|(?P<param2>[A-Za-z_]\w*)\s*\[\s*[\'\"](?P<key2>[A-Za-z_]\w*)[\'\"]\s*\]")
IF_GUARD_RE = re.compile(r"^\s*if\s+(?P<cond>.+?)\s*:\s*$")
RAISE_RE = re.compile(r"^\s+raise\b", re.M)
HTTP_ERR_RE = re.compile(
    r"HTTPException\s*\(\s*status_code\s*=\s*(?P<code>\d{3})[^)]*?"
    r"detail\s*=\s*(?P<detail>[^)]*)\)", re.DOTALL)
SELECT_FROM_RE = re.compile(
    r"SELECT\s+(?P<cols>[^\n]*?)\s+FROM\s+(?P<table>[\`\"]?\w+[\`\"]?)",
    re.IGNORECASE)
STREAM_CALL_RE = re.compile(
    r"\b(?P<cls>StreamingResponse|FileResponse|JSONResponse|RedirectResponse|Response)\s*\(")
MEDIA_TYPE_RE = re.compile(r"media_type\s*=\s*[\'\"](?P<mt>[^\'\"]+)[\'\"]")
ARN_RE = re.compile(r"^\s*(?P<arg>[A-Za-z_]\w*)\s*(?::[^=,]+)?(?:=\s*(?P<default>.+))?$")
ERR_PLACEHOLDER_RE = re.compile(r"%[sdif]|%\([^)]*\)[sdif]")


def _paren_body(text, pos):
    """从 '(' 位置做括号配对，返回内部文本（跳过引号包裹的字符串）。"""
    if pos >= len(text) or text[pos] != "(":
        return ""
    depth, quote, i = 0, None, pos
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == quote:
                quote = None
        elif ch in "'\"`":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[pos + 1:i]
        i += 1
    return text[pos + 1:]


def _split_top_level(s):
    """按顶层逗号切分（忽略括号 / 引号内的逗号）。"""
    out, buf, depth, quote, i = [], "", 0, None, 0
    while i < len(s):
        ch = s[i]
        if quote:
            if ch == "\\" and i + 1 < len(s):
                buf += s[i:i + 2]
                i += 2
                continue
            if ch == quote:
                quote = None
            buf += ch
        elif ch in "'\"`":
            quote = ch
            buf += ch
        elif ch in "([{":
            depth += 1
            buf += ch
        elif ch in ")]}":
            depth -= 1
            buf += ch
        elif ch == "," and depth == 0:
            out.append(buf.strip())
            buf = ""
        else:
            buf += ch
        i += 1
    if buf.strip():
        out.append(buf.strip())
    return out


def _bracket_span(s, open_ch, close_ch, start=0):
    """返回 (open_pos, close_pos)，找不到则 (-1, -1)。跳过引号内字符。"""
    i = s.find(open_ch, start)
    if i < 0:
        return -1, -1
    depth, quote = 0, None
    j = i
    while j < len(s):
        ch = s[j]
        if quote:
            if ch == "\\" and j + 1 < len(s):
                j += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "'\"`":
            quote = ch
        elif ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return i, j
        j += 1
    return i, -1


def _dict_entries(expr):
    """从含对象字面量的表达式中取顶层键值对；无字面量返回 None。"""
    if not expr:
        return None
    i, j = _bracket_span(expr, "{", "}")
    if i < 0 or j < 0:
        return None
    entries = []
    for part in _split_top_level(expr[i + 1:j]):
        if not part:
            continue
        km = re.match(r"^[\'\"](?P<k>[^\'\"]+)[\'\"]\s*:\s*(?P<v>.*)$", part, re.DOTALL)
        if km:
            entries.append({"name": km.group("k"), "raw": _clean(km.group("v"))})
            continue
        sm = re.match(r"^\.\.\.(?P<v>.*)$", part, re.DOTALL)
        if sm:
            entries.append({"name": "…(展开)", "raw": _clean(sm.group("v"))[:60]})
    return entries


def _infer_type(expr):
    """从表达式粗推断类型；推不出返回 any。判断顺序由具体到宽泛。"""
    e = _clean(expr)
    if not e:
        return "any"
    if re.search(r"\bint\s*\(", e) or re.fullmatch(r"-?\d+", e):
        return "integer"
    if re.search(r"\belse\s+-?\d+\s*$", e):
        return "integer"
    if re.search(r"\belse\s+[\'\"][^\'\"]*[\'\"]\s*$", e):
        return "string"
    if re.search(r"\bfloat\s*\(", e) or re.fullmatch(r"-?\d+\.\d+", e):
        return "number"
    if re.search(r"\bbool\s*\(", e) or e in ("True", "False", "true", "false"):
        return "boolean"
    if re.search(r"or\s*\[\s*\]", e) or re.search(r"\blist\s*\(", e) or re.match(r"^\[", e):
        return "array"
    if re.search(r"or\s*\{\s*\}", e) or re.search(r"\bdict\s*\(", e):
        return "object"
    if re.search(r"\.strip\(|\.lower\(|\.upper\(|\bstr\s*\(", e):
        return "string"
    if re.match(r"^[\'\"].*[\'\"]$", e, re.DOTALL):
        return "string"
    return "any"


def parse_ddl_columns(body):
    """解析 CREATE TABLE 的字段列表 → [{name, type, constraints}]。"""
    cols = []
    for raw in _split_top_level(body or ""):
        line = _clean(raw)
        if not line or DDL_TABLE_CONSTRAINT_RE.match(line) \
                or DDL_TABLE_INDEX_RE.match(line):
            continue
        m = DDL_COLUMN_RE.match(line)
        if not m:
            continue
        rest = (m.group("rest") or "").upper()
        cons = []
        if "PRIMARY KEY" in rest:
            cons.append("PK")
        if "NOT NULL" in rest:
            cons.append("NOT NULL")
        if "UNIQUE" in rest:
            cons.append("UNIQUE")
        if re.search(r"AUTOINCREMENT|AUTO_INCREMENT|SERIAL", rest):
            cons.append("AUTO")
        dm = re.search(r"DEFAULT\s+([^,\s]+)", rest)
        if dm:
            cons.append("DEFAULT " + dm.group(1).strip("'\""))
        rm = re.search(r"REFERENCES\s+(\w+)", rest)
        if rm:
            cons.append("FK→" + rm.group(1))
        if "CHECK" in rest:
            cons.append("CHECK")
        cols.append({"name": m.group("name"),
                     "type": _clean(m.group("type")).upper(),
                     "constraints": cons})
    return cols


def ddl_columns(text, pos):
    """解析 CREATE TABLE 括号体 → 字段列表。

    兼容 Python 相邻字符串字面量拼接的建表语句（"CREATE TABLE t(" " a INT," ...）：
    `_paren_body` 会把引号内文本当字符串跳过，这类写法会整段丢列，
    故先抹掉相邻引号对再兜底解析，取列数更多的一版。
    """
    body = _paren_body(text, pos)
    cols = parse_ddl_columns(body)
    if '"' in body or "'" in body:
        merged = DDL_CONCAT_STR_RE.sub("", body)
        merged = merged.replace('"', "").replace("'", "")
        mcols = parse_ddl_columns(merged)
        if len(mcols) > len(cols):
            return mcols
    return cols


def ddl_column_index(data_model):
    """{表名: [{name,type,constraints}]}，供响应字段类型联动。"""
    idx = {}
    for t in (data_model or {}).get("tables", []):
        if t.get("columns"):
            idx[t["name"]] = t["columns"]
    return idx


def _err_detail(raw):
    """把 HTTPException 的 detail 表达式还原成可读提示。

    源码常见 `detail="非法角色: %s" % role`、`detail=str(exc)`、`detail="；".join(errors)`。
    照录会带出格式化 / 拼接残留：字面量足够完整时取字面量并把占位符换成 …；
    整段就是代码表达式时标成「动态提示」并把表达式照录，便于回源。
    """
    s = (raw or "").strip()
    lit = re.match(r'(?:[fFrRbBuU]{0,2})?[\'"](?P<txt>[^\'"]*)[\'"]', s)
    if lit:
        txt, tail = lit.group("txt"), s[lit.end():].strip()
        fragment = len(txt.strip()) < 3 or tail.startswith(".join") or tail.startswith("+")
        if not fragment:
            return ERR_PLACEHOLDER_RE.sub("…", txt).strip()
    expr = re.sub(r"\s+", " ", s).strip()
    if expr.count("(") > expr.count(")"):
        expr += ")" * (expr.count("(") - expr.count(")"))
    if not expr:
        return ""
    return "（动态提示：%s）" % expr[:80]


def _py_func_body(text, def_pos):
    """取 Python 函数体（缩进敏感）；def_pos 允许指向 def 前的空白 / async。"""
    if text.startswith("async", def_pos):
        d = text.find("def", def_pos, def_pos + 16)
        if d > 0:
            def_pos = d
    if not text.startswith("def", def_pos):
        m = re.search(r"(?m)^[ \t]*(?:async\s+)?def\b", text[def_pos:def_pos + 240])
        if not m:
            return ""
        seg = m.group(0)
        def_pos = def_pos + m.start() + (len(seg) - len(seg.lstrip()))
        d = text.find("def", def_pos, def_pos + 16)
        if d > 0:
            def_pos = d
    ls = text.rfind("\n", 0, def_pos) + 1
    head = text[ls:def_pos]
    indent = len(head) - len(head.lstrip())
    nl = text.find("\n", def_pos)
    if nl < 0:
        return ""
    out = []
    for ln in text[nl + 1:].split("\n"):
        if ln.strip():
            cur = len(ln) - len(ln.lstrip())
            if cur <= indent:
                break
        out.append(ln)
    return "\n".join(out)


def _js_func_body(text, def_pos):
    """取 JS / TS 函数体：首个 '{' 起做括号配对。"""
    i = text.find("{", def_pos)
    if i < 0:
        return ""
    _, j = _bracket_span(text, "{", "}", i)
    return text[i + 1:j] if j > i else text[i + 1:]


def _return_exprs(body):
    """取函数体里全部 return 表达式（跨行括号自动续读）。"""
    out = []
    for m in re.finditer(r"^[ \t]*return\b[ \t]*(?P<expr>.*)$", body or "", re.MULTILINE):
        expr = m.group("expr").strip()
        if not expr:
            continue
        depth = (expr.count("{") + expr.count("(") + expr.count("[")
                 - expr.count("}") - expr.count(")") - expr.count("]"))
        if depth > 0:
            buf = expr
            for ln in body[m.end():].split("\n"):
                buf += " " + ln.strip()
                depth += (ln.count("{") + ln.count("(") + ln.count("[")
                          - ln.count("}") - ln.count(")") - ln.count("]"))
                if depth <= 0:
                    break
            expr = buf.strip()
        out.append(expr)
    return out


def _detect_body_param(sig):
    """识别请求体参数名：类型为 dict / Body 的形参，或常见命名。

    Depends(...) / Request / Response 注入的形参不是请求体，必须排除。
    """
    for part in _split_top_level(sig or ""):
        nm = re.match(r"^\s*\*{0,2}(?P<name>[A-Za-z_]\w*)", part)
        if not nm:
            continue
        name = nm.group("name")
        if re.search(r"=\s*Depends\s*\(", part):
            continue
        if re.search(r":\s*(?:Request|Response|BackgroundTasks|WebSocket)\b", part):
            continue
        if re.match(r"^\s*\*{0,2}[A-Za-z_]\w*\s*:\s*"
                    r"(?:dict|Dict\[|Mapping\b|Any\b|Body\b)", part):
            return name
        if name in BODY_PARAM_NAMES:
            return name
    return ""


def _upgrade_type_by_usage(body, lhs, cur):
    """按变量在函数体中的显式转换调用升级类型（int(x) / float(x) / bool(x)）。"""
    if not lhs:
        return cur
    esc = re.escape(lhs)
    if re.search(r"\bint\s*\(\s*%s\b" % esc, body):
        return "integer"
    if re.search(r"\bfloat\s*\(\s*%s\b" % esc, body):
        return "number"
    if re.search(r"\bbool\s*\(\s*%s\b" % esc, body):
        return "boolean"
    return cur


def _required_names(body):
    """扫描「取值守卫」语句，返回被判定为必填的局部变量名集合。

    只认分支里真的 `raise` 的 if（即缺值会报错），且限定为「缺失 / 空值 / 越界 / 枚举」形态：
    `not x`、`x is None`、`x == ''`、`x <= 0`、`x not in (...)`。
    `x == "platform_admin"` 这类纯枚举分支不算——它判断的是取值不是有无。
    """
    names, lines = set(), (body or "").split("\n")
    for i, ln in enumerate(lines):
        m = IF_GUARD_RE.match(ln)
        if not m:
            continue
        if not RAISE_RE.search("\n".join(lines[i + 1:i + 6])):
            continue
        cond = m.group("cond")
        names.update(re.findall(r"\bnot\s+(?!in\b|is\b)([A-Za-z_]\w*)", cond))
        names.update(re.findall(r"([A-Za-z_]\w*)\s+not\s+in\s+", cond))
        names.update(re.findall(r"([A-Za-z_]\w*)\s+is\s+None", cond))
        names.update(re.findall(r"([A-Za-z_]\w*)\s*!=\s*None", cond))
        names.update(re.findall(r'([A-Za-z_]\w*)\s*==\s*(?:None|["\']["\'])', cond))
        names.update(re.findall(r"([A-Za-z_]\w*)\s*(?:<=|<|>=|>)", cond))
    return names


def extract_request_fields(body, body_param):
    """提取请求字段：名字 / 类型 / 必填 / 默认 / 来源。仅看取值、转换与守卫语句。"""
    if not body or not body_param:
        return []
    lines = body.split("\n")
    req_names = _required_names(body)
    found, order = {}, []
    for idx, ln in enumerate(lines):
        for m in PARAM_ACCESS_RE.finditer(ln):
            param = m.group("param") or m.group("param2")
            key = m.group("key") or m.group("key2")
            if param != body_param or not key:
                continue
            direct = bool(m.group("key2"))
            rhs = ln.split("=", 1)[1] if "=" in ln else ln
            lhs = ln.split("=", 1)[0].strip() if "=" in ln else ""
            rest = m.group("rest") or ""
            ftype = _upgrade_type_by_usage(body, lhs, _infer_type(rhs))
            required = None
            if direct or (lhs and lhs in req_names):
                required = True
            default = ""
            if rest.strip().startswith(","):
                d = rest.strip()[1:].strip()
                if d and d.lower() not in ("none",):
                    default = d
            if required is None:
                if default or re.search(r"\bor\b", rhs):
                    required = False
            src = ('%s[%r]' % (param, key)) if direct else ('%s.get(%r)' % (param, key))
            item = {"name": key, "type": ftype,
                    "required": required, "from": src}
            if default:
                item["default"] = default
            if key not in found:
                found[key] = item
                order.append(key)
            else:
                prev = found[key]
                if prev.get("required") is None and item["required"] is not None:
                    prev["required"] = item["required"]
                if prev["type"] == "any" and item["type"] != "any":
                    prev["type"] = item["type"]
                if item.get("default") and not prev.get("default"):
                    prev["default"] = item["default"]
    return [found[k] for k in order]


def _norm_cols(cols):
    """规整 SELECT 列表：去 AS 别名、去表前缀、保留 *。"""
    out = []
    for c in cols:
        c = _clean(c)
        if not c:
            continue
        if c == "*":
            out.append("*")
            continue
        am = re.search(r"\bAS\s+(?P<alias>\w+)\s*$", c, re.IGNORECASE)
        if am:
            out.append(am.group("alias"))
            continue
        cm = re.search(r"(?:\.(?P<col>\w+)|\b(?P<bare>\w+))$", c)
        out.append(cm.group("col") or cm.group("bare") if cm else c)
    return out


def _main_query(body):
    """取函数体里最后一个 SELECT ... FROM 的 (表名, 列名列表)。"""
    best = None
    for m in SELECT_FROM_RE.finditer(body or ""):
        cols = m.group("cols")
        if not re.match(r"^[\w\s,\.\*`\"\(\)]+$", cols):
            continue
        best = (m.group("table").strip("`\""), _norm_cols(cols.split(",")))
    return best


def _resp_field_type(raw, col_types, callables):
    """响应字段类型：表达式推断 → 辅助函数返回形状 → `row["col"]` 回落 DDL 列类型。"""
    t = _infer_type(raw)
    if t != "any":
        return t
    fm = re.match(r"^(?P<fn>\w+)\s*\(", raw or "")
    if fm and fm.group("fn") in (callables or {}):
        kinds = callables[fm.group("fn")].get("kinds") or set()
        for k in ("array", "object", "string", "integer", "number", "boolean", "file"):
            if k in kinds:
                return k
    cm = re.fullmatch(r"\w+\s*\[\s*[\'\"](?P<col>\w+)[\'\"]\s*\]", (raw or "").strip())
    if cm and col_types and cm.group("col") in col_types:
        return col_types[cm.group("col")]
    return "any"


def build_callable_index(sources):
    """函数名 → {file, returns, kinds}，用于响应结构一层内联（仅核心文件）。"""
    idx = {}
    for rel, text in sources:
        if is_aux_file(rel):
            continue
        for m in re.finditer(r"(?m)^([ \t]*)(?:async\s+)?def\s+(?P<name>[A-Za-z_]\w*)\s*\(",
                             text):
            name = m.group("name")
            if name in idx:
                continue
            rets = _return_exprs(_py_func_body(text, m.start() + len(m.group(1))))
            if not rets:
                continue
            kinds = set()
            for r in rets:
                if STREAM_CALL_RE.search(r):
                    kinds.add("file")
                elif r.lstrip().startswith("["):
                    kinds.add("array")
                elif _dict_entries(r) is not None:
                    kinds.add("object")
                elif re.match(r"^-?\d+$", r):
                    kinds.add("integer")
                elif r in ("True", "False"):
                    kinds.add("boolean")
                else:
                    kinds.add("any")
            idx[name] = {"file": rel, "returns": rets, "kinds": kinds}
    return idx


def _returned_var(expr):
    """return 表达式对应的局部变量名（`rows` / `rows[0]`）；不是变量则返回 ''。"""
    m = re.match(r"^([A-Za-z_]\w*)\s*(?:\[[^\]]*\])?\s*$", (expr or "").strip())
    return m.group(1) if m else ""


def _assign_rhs(body, var):
    """取 `var = ...` 的右值表达式（跨行到括号配平为止）。

    只在括号内跨行续接，避免把紧随其后的新语句（缩进更深的 `var["k"] = ...`）吞进来。
    """
    m = re.search(r"(?m)^[ \t]*%s\s*=(?!=)" % re.escape(var), body or "")
    if not m:
        return ""
    i, depth, out, n = m.end(), 0, [], len(body)
    while i < n:
        ch = body[i]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth < 0:
                break
        elif ch == "\n" and depth == 0:
            if not "".join(out).rstrip().endswith((",", "\\", "+", "and", "or")):
                break
        out.append(ch)
        i += 1
    return "".join(out).strip()


def _entries_to_fields(entries, col_types, callables):
    return [{"name": e["name"],
             "type": _resp_field_type(e["raw"], col_types, callables),
             "from": e["raw"][:70]} for e in entries]


def _var_response_shape(var, body, callables, ddl_cols, depth, col_types_all, col_types):
    """回溯局部变量：`x = {...}` / `x = helper(...)` / `x.append({...})` → 响应结构。

    覆盖「先组装再补字段」的常见写法：`brief = _row_brief(row)` 之后
    再逐条 `brief["script"] = ...`，仅靠 return 表达式无法还原。
    """
    rhs = _assign_rhs(body, var)
    base = None
    if rhs:
        entries = _dict_entries(rhs)
        if entries is not None:
            base = {"kind": "array" if rhs.lstrip().startswith("[") else "object",
                    "fields": _entries_to_fields(entries, col_types, callables),
                    "source": "dict literal（`%s`）" % var}
        elif depth < 2:
            for name in re.findall(r"\b(_?[A-Za-z]\w+)\s*\(", rhs):
                sub = (callables or {}).get(name)
                if not sub:
                    continue
                for sub_ret in sub["returns"]:
                    sh = extract_response_shape(sub_ret, body, callables, ddl_cols,
                                                depth + 1, col_types_all)
                    if sh["kind"] in ("stream", "file", "raw"):
                        base = dict(sh, source="%s()  ·  %s" % (name, sub["file"]))
                        break
                    if sh["kind"] in ("object", "array") and sh["fields"]:
                        base = dict(sh, source="%s()  ·  %s" % (name, sub["file"]))
                        break
                if base:
                    break
    if base is None:
        for am in re.finditer(r"%s\.append\s*\(" % re.escape(var), body or ""):
            entries = _dict_entries(_paren_body(body, am.end() - 1))
            if entries is not None:
                base = {"kind": "array",
                        "fields": _entries_to_fields(entries, col_types, callables),
                        "source": "dict literal（`%s.append`）" % var}
                break
    if base is None:
        return None
    if base["kind"] not in ("object", "array"):
        return base
    for om in re.finditer(
            r'(?m)^[ \t]*%s\[[\'"](?P<k>[A-Za-z_]\w*)[\'"]\][ \t]*=[ \t]*(?P<rhs>[^\n]*)'
            % re.escape(var), body or ""):
        k, krhs = om.group("k"), om.group("rhs").strip()
        if any(f["name"] == k for f in base["fields"]):
            continue
        base["fields"].append({"name": k, "type": _infer_type(krhs), "from": krhs[:70]})
    return base


def _select_feeds_return(body, expr, table):
    """SELECT 列兜底只在返回值确实取自该查询时才生效。

    否则会把 handler 里的旁支子查询（如「按 uid 查题库名」）当成响应结构，
    比留空更糟——宁可退回「◐ 待补」。
    """
    var = _returned_var(expr)
    if not var:
        return False
    rhs = _assign_rhs(body, var)
    if not rhs or not re.search(r"\bSELECT\b", rhs, re.I):
        return False
    return bool(re.search(r"\bFROM\s+[`\"]?%s\b" % re.escape(table), rhs, re.I))


def extract_response_shape(ret_expr, body, callables, ddl_cols, depth=0, col_types_all=None):
    """解析 return 表达式 → {kind, fields, source, mediaType?}。

    kind: object | array | stream | file | raw | redirect | none | scalar | unknown
    优先序：dict 字面量 → 局部变量回溯（字面量 / 辅助函数 / append）→
    辅助函数调用内联 → SELECT 列兜底（需数据流成立）。
    """
    expr = (ret_expr or "").strip()
    if not expr:
        return {"kind": "unknown", "fields": [], "source": ""}
    if expr == "None":
        return {"kind": "none", "fields": [], "source": "None"}

    sm = STREAM_CALL_RE.search(expr)
    if sm:
        cls = sm.group("cls")
        kind = {"StreamingResponse": "stream", "FileResponse": "file",
                "RedirectResponse": "redirect", "JSONResponse": "object"}.get(cls, "raw")
        out = {"kind": kind, "fields": [], "source": cls + "()"}
        mt = MEDIA_TYPE_RE.search(expr)
        if mt:
            out["mediaType"] = mt.group("mt")
        return out

    query = _main_query(body)
    table, cols = (query if query else ("", []))
    col_types = dict(col_types_all or {})
    if table and table in (ddl_cols or {}):
        col_types.update({c["name"]: c["type"] for c in ddl_cols[table]})

    entries = _dict_entries(expr)
    if entries is not None:
        return {"kind": "array" if expr.lstrip().startswith("[") else "object",
                "fields": _entries_to_fields(entries, col_types, callables),
                "source": "dict literal"}

    returned_var = _returned_var(expr)
    if returned_var:
        shape = _var_response_shape(returned_var, body, callables, ddl_cols,
                                    depth, col_types_all, col_types)
        if shape:
            return shape

    if depth < 2:
        for name in re.findall(r"\b(_?[A-Za-z]\w+)\s*\(", expr):
            if name not in (callables or {}):
                continue
            sub = callables[name]
            outer_array = bool(" for " in expr or expr.lstrip().startswith("["))
            for sub_ret in sub["returns"]:
                sub_shape = extract_response_shape(sub_ret, body, callables, ddl_cols,
                                                   depth + 1, col_types_all)
                if sub_shape["kind"] in ("stream", "file", "raw"):
                    sub_shape["source"] = name + "()  ·  " + sub["file"]
                    return sub_shape
                if sub_shape["kind"] in ("object", "array") and sub_shape["fields"]:
                    sub_shape["source"] = name + "()  ·  " + sub["file"]
                    if outer_array:
                        sub_shape["kind"] = "array"
                    return sub_shape
            return {"kind": "array" if outer_array else "object", "fields": [],
                    "source": name + "()  ·  " + sub["file"], "unresolved": True}

    if table and cols and _select_feeds_return(body, expr, table):
        if cols == ["*"]:
            cols = [c["name"] for c in (ddl_cols or {}).get(table, [])]
            col_types.update({c["name"]: c["type"] for c in (ddl_cols or {}).get(table, [])})
        if cols:
            fields = [{"name": c, "type": col_types.get(c, "any"),
                       "from": "SELECT 列"} for c in cols]
            kind = "object" if re.search(r"\[\s*0\s*\]", expr) else "array"
            return {"kind": kind, "fields": fields, "source": "SELECT 自 " + table}

    if re.match(r"^-?\d+$", expr):
        return {"kind": "scalar", "fields": [], "source": "integer"}
    if expr in ("True", "False"):
        return {"kind": "scalar", "fields": [], "source": "boolean"}
    if re.match(r"^[\'\"]", expr):
        return {"kind": "scalar", "fields": [], "source": "string"}
    return {"kind": "unknown", "fields": [], "source": _clean(expr)[:70]}


def scan_sources(project_dir):
    """遍历源码文件并读取一次（走字节缓存），返回 [(相对路径, 文本)]，顺序稳定。"""
    found = []

    def walk(base, rel, depth):
        if depth > 6 or len(found) >= MAX_SOURCE_FILES:
            return
        try:
            names = sorted(os.listdir(base))
        except OSError:
            return
        for n in names:
            if n.startswith(".") or n in SOURCE_SKIP_DIRS:
                continue
            p = os.path.join(base, n)
            if os.path.isdir(p):
                walk(p, rel + n + "/", depth + 1)
            elif n.endswith(SOURCE_EXTS):
                found.append((rel + n, p))

    walk(project_dir, "", 1)
    out = []
    for rel, p in found[:MAX_SOURCE_FILES]:
        data = read_bytes(p)
        if len(data) > MAX_SOURCE_BYTES:
            continue
        out.append((rel, data.decode("utf-8", "replace")))
    return out


def _lineno(text, pos):
    return text.count("\n", 0, pos) + 1


def _clean(s):
    return " ".join((s or "").split())


def is_aux_file(rel):
    """辅助文件（自测 / 夹具 / mock / 种子示例）：不参与核心提取与哈希，仅作辅助信息列出。

    这些文件里的表、端点、URL 多属测试夹具或演示数据，混入正文会污染事实。
    若某个「辅助表」实为业务表，页面中应显式说明并人工修正。
    """
    return bool(AUX_FILE_RE.search(rel))


def _pick_path(args):
    """从装饰器参数里取路径：优先第一个字符串字面量。"""
    m = ARG_STR_RE.search(args or "")
    return m.group(1) if m else ""


def extract_api(sources, ddl_cols=None):
    """提取 HTTP 接口声明：分组 + 端点（方法 / 路径 / 处理函数 / 权限 / 位置 / 字段结构）。

    覆盖 FastAPI / Flask / Express / Koa / Spring。读声明行、函数签名，
    以及函数体内的取值与返回结构（用于请求 / 响应字段），不通读实现逻辑。
    """
    groups, endpoints = {}, []
    callables = build_callable_index(sources)
    ddl_cols = ddl_cols or {}
    col_types_all, clashes = {}, set()
    for t in ddl_cols.values():
        for c in t:
            k = c["name"]
            if k in col_types_all and col_types_all[k] != c["type"]:
                clashes.add(k)
            col_types_all[k] = c["type"]
    for k in clashes:
        col_types_all.pop(k, None)

    for rel, text in sources:
        prefix_by_obj, role_alias = {}, {}
        for m in ROLE_ALIAS_RE.finditer(text):
            role_alias[m.group("alias")] = [s for s in ARG_STR_RE.findall(m.group("roles"))]
        for m in ROUTER_PREFIX_RE.finditer(text):
            args = m.group("args") or ""
            pm = PREFIX_KW_RE.search(args)
            prefix = pm.group("prefix") if pm else _pick_path(args)
            prefix_by_obj[m.group("obj")] = prefix
            groups.setdefault(prefix, {
                "prefix": prefix, "file": rel, "line": _lineno(text, m.start()),
                "framework": "fastapi/flask", "endpoints": [],
            })
        spring_prefix = ""
        sm = SPRING_CLASS_RE.search(text)
        if sm:
            spring_prefix = sm.group("path")
            groups.setdefault(spring_prefix, {
                "prefix": spring_prefix, "file": rel, "line": _lineno(text, sm.start()),
                "framework": "spring", "endpoints": [],
            })

        def add(method, path, pos, obj=None):
            tail = text[pos:]
            handler, sig, sig_line, def_abs, is_py = "", "", _lineno(text, pos), None, False
            for i, rx in enumerate((PY_DEF_RE, JS_FN_RE, JS_ARROW_RE)):
                fm = rx.search(tail)
                if fm and tail[:fm.start()].count("\n") <= 8:
                    lead = len(fm.group(0)) - len(fm.group(0).lstrip())
                    handler = fm.group("name")
                    sig = _clean(fm.group("sig"))
                    sig_line = _lineno(text, pos) + tail[:fm.start()].count("\n")
                    def_abs = pos + fm.start() + lead
                    is_py = (i == 0)
                    break
            scope = text[pos:pos + 1200]
            roles = []
            for im in INLINE_ROLES_RE.finditer(text[pos:pos + 600]):
                roles += [s for s in ARG_STR_RE.findall(im.group("roles"))]
            for dm in DEPENDS_ARG_RE.finditer(sig):
                roles += role_alias.get(dm.group("dep"), [])

            body_text, body_param = "", ""
            request_fields, response_shape, errors = [], None, []
            if def_abs is not None:
                body_text = _py_func_body(text, def_abs) if is_py else _js_func_body(text, def_abs)
            if body_text:
                body_param = _detect_body_param(sig) if is_py else ""
                request_fields = extract_request_fields(body_text, body_param)
                rets = _return_exprs(body_text)
                if rets:
                    response_shape = extract_response_shape(
                        rets[-1], body_text, callables, ddl_cols, 0, col_types_all)
                seen_err = set()
                for em in HTTP_ERR_RE.finditer(body_text):
                    detail = _err_detail(em.group("detail"))
                    k = (int(em.group("code")), detail)
                    if k in seen_err:
                        continue
                    seen_err.add(k)
                    errors.append({"status": k[0], "detail": detail[:120]})
            prefix = prefix_by_obj.get(obj, "") if obj else spring_prefix
            full = (prefix.rstrip("/") + "/" + path.lstrip("/")) if prefix else path
            endpoints.append({
                "method": method.upper(), "path": full, "handler": handler,
                "signature": sig, "permissions": sorted(set(roles)),
                "authHint": bool(AUTH_HINT_RE.search(scope)),
                "file": rel, "line": sig_line, "prefix": prefix,
                "bodyParam": body_param,
                "request": request_fields,
                "response": response_shape,
                "errors": errors[:8],
                "isAux": is_aux_file(rel),
            })

        for m in ROUTE_DECORATOR_RE.finditer(text):
            method = m.group("method")
            decorator_scope = text[m.start():m.end() + 400]
            if method == "route":
                mm = re.search(r'methods\s*=\s*\[([^\]]*)\]', decorator_scope)
                method = (ARG_STR_RE.search(mm.group(1)).group(1) if mm and
                          ARG_STR_RE.search(mm.group(1)) else "GET")
            add(method, _pick_path(m.group("args")), m.end(), obj=m.group("obj"))

        for m in EXPRESS_ROUTE_RE.finditer(text):
            obj, method, path = m.group("obj"), m.group("method"), m.group("path")
            if method == "use":
                if path.startswith("/"):
                    groups.setdefault(path, {
                        "prefix": path, "file": rel, "line": _lineno(text, m.start()),
                        "framework": "express", "endpoints": [],
                    })
                continue
            if obj not in ("router", "app", "api", "r") and "." not in obj:
                continue
            add(method, path, m.end(), obj=obj)

        for m in SPRING_MAPPING_RE.finditer(text):
            add(m.group("method"), m.group("path"), m.end())

    meta = {p: {"prefix": p, "file": g["file"], "line": g["line"],
                "framework": g["framework"]} for p, g in groups.items()}

    def collect(eps):
        out = {}
        for e in eps:
            p = e["prefix"]
            info = meta.get(p, {"prefix": p, "file": e["file"], "line": e["line"],
                                "framework": "unknown"})
            out.setdefault(p, dict(info, endpoints=[]))["endpoints"].append(e)
        res = sorted(out.values(), key=lambda g: g["prefix"])
        for g in res:
            g["endpoints"].sort(key=lambda e: (e["file"], e["line"]))
        return res

    core = [e for e in endpoints if not e["isAux"]]
    aux = [e for e in endpoints if e["isAux"]]
    return {"groups": collect(core), "auxiliaryGroups": collect(aux),
            "endpointCount": len(core), "auxiliaryEndpointCount": len(aux)}


def extract_data_model(sources):
    """提取数据模型声明：DDL 表 / 索引 / 变更语句，以及 ORM / JPA 模型。

    同名表按表名聚合，occurrences 记录全部声明位置（含迁移重建）；
    auxOnly=True 表示只出现在自测 / 夹具文件里——这类不进主表清单、也不参与哈希。
    """
    raw_tables, raw_indexes, raw_alters, raw_orms = [], [], [], []
    for rel, text in sources:
        test = is_aux_file(rel)
        for m in DDL_TABLE_RE.finditer(text):
            raw_tables.append({"name": m.group("name"), "kind": "ddl", "file": rel,
                               "line": _lineno(text, m.start()), "isAux": test,
                               "columns": ddl_columns(text, m.end() - 1)})
        for m in DDL_INDEX_RE.finditer(text):
            raw_indexes.append({"name": m.group("name"), "file": rel,
                                "line": _lineno(text, m.start()), "isAux": test})
        for m in DDL_ALTER_RE.finditer(text):
            raw_alters.append({"table": m.group("name"), "action": m.group("action").upper(),
                               "file": rel, "line": _lineno(text, m.start()), "isAux": test})
        for lm in ALTER_COLUMN_LIST_RE.finditer(text):
            for tm in ALTER_TRIPLE_RE.finditer(lm.group("body")):
                coldef = tm.group("coldef")
                if len(coldef) > 1 and coldef[0] == coldef[-1] and coldef[0] in "\"'":
                    coldef = coldef[1:-1]
                parsed = parse_ddl_columns("%s %s" % (tm.group("column"), coldef))
                if not parsed:
                    continue
                line = _lineno(text, lm.start() + tm.start())
                raw_tables.append({"name": tm.group("table"), "kind": "alter",
                                   "file": rel, "line": line, "isAux": test,
                                   "addCols": True, "columns": parsed})
                raw_alters.append({"table": tm.group("table"), "action": "ADD COLUMN",
                                   "column": tm.group("column"), "file": rel,
                                   "line": line, "isAux": test})
        for m in ORM_TABLENAME_RE.finditer(text):
            raw_orms.append({"name": m.group("name"), "kind": "orm", "class": "", "file": rel,
                             "line": _lineno(text, m.start()), "isAux": test})
        for m in ORM_CLASS_RE.finditer(text):
            raw_orms.append({"name": "", "kind": "orm", "class": m.group("cls"), "file": rel,
                             "line": _lineno(text, m.start()), "isAux": test})
        for m in JPA_ENTITY_RE.finditer(text):
            raw_orms.append({"name": m.group("name") or "", "kind": "jpa", "class": "",
                             "file": rel, "line": _lineno(text, m.start()), "isAux": test})

    def group(records, name_key):
        out = {}
        for r in records:
            k = r.get(name_key) or ""
            if not k:
                continue
            g = out.setdefault(k, {"name": k, "occurrences": [], "auxOnly": True,
                                   "columns": [], "_colCands": [], "_addCols": []})
            g["occurrences"].append({
                "file": r["file"], "line": r["line"],
                "kind": r.get("kind") or r.get("action") or "",
                "cols": len(r.get("columns") or [])})
            if r.get("columns"):
                cand = (0 if not r["isAux"] else 1, -len(r["columns"]),
                        r["file"], r["line"], r["columns"])
                (g["_addCols"] if r.get("addCols") else g["_colCands"]).append(cand)
            if not r["isAux"]:
                g["auxOnly"] = False
        res = []
        for g in sorted(out.values(), key=lambda x: x["name"]):
            g["occurrences"].sort(key=lambda o: (o["file"], o["line"]))
            cands = g.pop("_colCands", [])
            adds = g.pop("_addCols", [])
            if cands:
                # 核心文件优先；同类取列数最多的那一版（避免被示例库 / 夹具里的
                # 同名小表覆盖，如 SQL 题包里的 users(id,name)）；仍并列取声明最靠前的。
                cands.sort(key=lambda c: (c[0], c[1], c[2], c[3]))
                base_cols = cands[0][4]
                added = []
                for c in sorted(adds, key=lambda c: (c[2], c[3])):
                    for col in c[4]:
                        if any(x["name"] == col["name"] for x in base_cols) or \
                                any(x["name"] == col["name"] for x in added):
                            continue
                        added.append(dict(col, addedAt="%s:%d" % (c[2], c[3])))
                g["addedColumns"] = added
                g["columns"] = base_cols + added
            g["file"] = g["occurrences"][0]["file"]
            g["line"] = g["occurrences"][0]["line"]
            res.append(g)
        return res

    def plain(records, keys):
        seen, out = set(), []
        for r in records:
            k = tuple(r.get(x, "") for x in keys)
            if k in seen:
                continue
            seen.add(k)
            out.append(r)
        return sorted(out, key=lambda x: (x["file"], x["line"]))

    tables_all = group(raw_tables, "name")
    orms_all = plain(raw_orms, ["name", "class", "file"])
    idx_all = plain(raw_indexes, ["name", "file"])
    alt_all = plain(raw_alters, ["table", "action", "file"])

    def split(seq):
        def test_flag(x):
            return x.get("auxOnly", x.get("isAux", False))
        return ([x for x in seq if not test_flag(x)], [x for x in seq if test_flag(x)])

    tables, tables_aux = split(tables_all)
    orms, orms_aux = split(orms_all)
    idx, idx_aux = split(idx_all)
    alters, alters_aux = split(alt_all)
    return {
        "tables": tables, "auxiliaryTables": tables_aux,
        "ormModels": orms, "auxiliaryOrmModels": orms_aux,
        "indexes": idx, "auxiliaryIndexes": idx_aux,
        "alterations": alters, "auxiliaryAlterations": alters_aux,
        "tableCount": len(tables), "auxiliaryTableCount": len(tables_aux),
    }


def extract_integrations(project_dir, openspec_dir, sources, archived=None, active=None):
    """提取外部集成事实：依赖清单、外部调用点、消息队列线索、外部进程、Non-Goals。"""
    deps = []
    seen = set()
    for base_rel in [""] + sorted({os.path.dirname(r) for r, _ in sources if "/" not in r} |
                                  {r.split("/")[0] for r, _ in sources}):
        base = os.path.join(project_dir, base_rel) if base_rel else project_dir
        for fn in DEP_FILES:
            p = os.path.join(base, fn)
            if os.path.isfile(p) and p not in seen:
                seen.add(p)
                deps.append({"file": os.path.relpath(p, project_dir),
                             "content": read_text(p).strip()})

    http_calls, mq, sdks, procs, urls = [], [], [], [], []
    for rel, text in sources:
        test = is_aux_file(rel)
        lines = text.splitlines()

        def snip(line_no):
            return _clean(lines[line_no - 1])[:160] if 0 < line_no <= len(lines) else ""

        for m in HTTP_CALL_RE.finditer(text):
            line = _lineno(text, m.start())
            http_calls.append({"lib": m.group("lib").lower(),
                               "method": (m.group("method") or "").upper(),
                               "kind": "call", "file": rel, "line": line,
                               "snippet": snip(line), "isAux": test})
        for m in CLIENT_INIT_RE.finditer(text):
            line = _lineno(text, m.start())
            name = (m.group("cls") or m.group("jscls") or m.group("pylib") or "")
            lib = m.group("lib") or name
            http_calls.append({"lib": lib.lower(), "method": "", "kind": "init",
                               "file": rel, "line": line, "snippet": snip(line),
                               "isAux": test})
        for m in URL_RE.finditer(text):
            line = _lineno(text, m.start())
            urls.append({"url": m.group(0), "key": "", "file": rel, "line": line,
                         "isAux": test})
        for m in ENDPOINT_KEY_RE.finditer(text):
            line = _lineno(text, m.start())
            urls.append({"url": m.group("url"), "key": m.group("key"), "file": rel,
                         "line": line, "isAux": test})
        for m in MQ_HINT_RE.finditer(text):
            mq.append({"client": m.group("mq"), "file": rel,
                       "line": _lineno(text, m.start()), "isAux": test})
        for m in SDK_HINT_RE.finditer(text):
            sdks.append({"sdk": _clean(m.group("sdk")), "file": rel,
                         "line": _lineno(text, m.start()), "isAux": test})
        for m in PROC_CALL_RE.finditer(text):
            line = _lineno(text, m.start())
            procs.append({"file": rel, "line": line, "snippet": snip(line),
                          "isAux": test})

    non_goals = []
    for ch in (archived or []) + (active or []):
        if not ch.get("design"):
            continue
        dpath = os.path.join(openspec_dir, ch["dir"], "design.md")
        for body in extract_sections(read_text(dpath), NON_GOAL_TITLE_RE):
            non_goals.append({"change": change_key(ch), "text": body[:2000]})

    def uniq(seq, keys):
        seen, out = set(), []
        for x in seq:
            k = tuple(x.get(k, "") for k in keys)
            if k in seen:
                continue
            seen.add(k)
            out.append(x)
        return sorted(out, key=lambda x: (x["file"], x["line"]))

    mq_u = uniq(mq, ["client", "file"])
    return {
        "dependencies": deps,
        "httpCalls": uniq(http_calls, ["lib", "method", "kind", "file"]),
        "urls": uniq(urls, ["url", "file", "line"]),
        "messageQueue": mq_u,
        "sdkHints": uniq(sdks, ["sdk", "file"]),
        "externalProcesses": uniq(procs, ["file", "line"]),
        "nonGoals": non_goals,
        "usesMessageQueue": bool([m for m in mq_u if not m["isAux"]]),
    }


def _strip_positions(obj):
    """递归去掉行号：行号会随无关编辑整体漂移，不能作为触发信号。"""
    if isinstance(obj, dict):
        return {k: _strip_positions(v) for k, v in sorted(obj.items()) if k != "line"}
    if isinstance(obj, list):
        return [_strip_positions(i) for i in obj]
    return obj


def _digest(records):
    h = hashlib.sha256()
    h.update(json.dumps(_strip_positions(records), ensure_ascii=False,
                        sort_keys=True).encode("utf-8"))
    return h.hexdigest()


def _core(records):
    return [r for r in records if not (isinstance(r, dict) and r.get("isAux"))]


def api_hash(sources, ddl_cols=None):
    if ddl_cols is None:
        ddl_cols = ddl_column_index(extract_data_model(sources))
    return _digest(extract_api(sources, ddl_cols)["groups"])


def data_model_hash(sources, dm=None):
    dm = dm or extract_data_model(sources)
    return _digest({k: dm[k] for k in ("tables", "ormModels", "indexes", "alterations")})


def integration_hash(project_dir, openspec_dir, sources, archived, active):
    ig = extract_integrations(project_dir, openspec_dir, sources, archived, active)
    return _digest({
        "dependencies": ig["dependencies"],
        "httpCalls": _core(ig["httpCalls"]),
        "urls": _core(ig["urls"]),
        "messageQueue": _core(ig["messageQueue"]),
        "sdkHints": _core(ig["sdkHints"]),
        "externalProcesses": _core(ig["externalProcesses"]),
        "usesMessageQueue": ig["usesMessageQueue"],
    })


def list_capabilities(openspec_dir):
    spec_root = os.path.join(openspec_dir, "specs")
    caps = []
    if os.path.isdir(spec_root):
        for name in sorted(os.listdir(spec_root)):
            if os.path.isfile(os.path.join(spec_root, name, "spec.md")):
                caps.append(name)
    return caps


ARTIFACT_FILES = ["README.md", "architecture.md", "decisions.md", "glossary.md",
                  "api.md", "data-model.md", "integrations.md"]


def artifact_files():
    return list(ARTIFACT_FILES)


def cmd_plan(args):
    project_dir = os.path.abspath(args.project)
    openspec_dir = os.path.join(project_dir, "openspec")
    if not os.path.isdir(openspec_dir):
        die("项目目录下不存在 openspec/：%s" % project_dir)
    wiki_dir = os.path.join(project_dir, "wiki")
    manifest = load_manifest(wiki_dir)

    caps = list_capabilities(openspec_dir)
    archived, active = scan_change_dirs(openspec_dir)
    for c in active:
        resolve_change(openspec_dir, c)

    synced_changes = (manifest or {}).get("syncedChanges", {})
    synced_specs = (manifest or {}).get("specs", {})
    synced_decisions = (manifest or {}).get("decisions", {})

    # 已同步的变更直接按目录匹配则不入候选，省去读取 proposal.md 的开销
    synced_dirs = {v.get("dir") for v in synced_changes.values()}
    candidates = [c for c in archived if c["dir"] not in synced_dirs]
    for c in candidates:
        resolve_change(openspec_dir, c)
    pending = [c for c in candidates
               if c["id"] not in synced_changes and c["dir"] not in synced_dirs]
    touched = {cap for c in pending for cap in c["capabilities"]}

    drifted = []
    if manifest:
        for cap in caps:
            recorded = synced_specs.get(cap, {}).get("hash")
            if recorded and recorded != sha256_file(os.path.join(openspec_dir, "specs", cap, "spec.md")):
                drifted.append(cap)

    missing_pages = [cap for cap in caps
                     if not os.path.isfile(os.path.join(wiki_dir, "specs", cap + ".md"))]
    removed = [cap for cap in sorted(synced_specs) if cap not in caps]

    dec_by_dir = {v.get("dir"): v.get("designHash") for v in synced_decisions.values()}
    pending_decisions = []
    for c in archived:
        if not c["design"]:
            continue
        if dec_by_dir.get(c["dir"]) == c["designHash"]:
            continue
        resolve_change(openspec_dir, c)
        synced_before = c["dir"] in dec_by_dir or c["id"] in synced_decisions
        pending_decisions.append({
            "id": c["id"], "date": c["date"], "dir": c["dir"],
            "capabilities": c["capabilities"],
            "reason": "design.md 已变更" if synced_before else "未提取",
        })

    need_full = (not manifest or not os.path.isfile(os.path.join(wiki_dir, "README.md")))
    if need_full:
        mode = "full"
        to_generate = list(caps)
    else:
        mode = "incremental"
        to_generate = sorted(touched | set(drifted) | set(missing_pages))

    current_ohash = overview_hash(project_dir, openspec_dir)
    overview_dirty = (not manifest or not manifest.get("overviewSynced")
                      or manifest.get("overviewHash") != current_ohash)

    current_ahash = architecture_hash(project_dir, openspec_dir, caps, archived, active)
    architecture_dirty = (not manifest or not manifest.get("architectureSynced")
                          or manifest.get("architectureHash") != current_ahash)

    current_ghash = glossary_digest(openspec_dir, caps)
    glossary_dirty = (not manifest or not manifest.get("glossarySynced")
                      or manifest.get("glossaryHash") != current_ghash)

    # 声明类提取（一次遍历源码，三个哈希共用同一份读取）
    sources = scan_sources(project_dir)
    dm = extract_data_model(sources)
    ddl_cols = ddl_column_index(dm)
    current_aphash = api_hash(sources, ddl_cols)
    api_dirty = (not manifest or not manifest.get("apiSynced")
                 or manifest.get("apiHash") != current_aphash)
    current_dmhash = data_model_hash(sources, dm)
    data_model_dirty = (not manifest or not manifest.get("dataModelSynced")
                        or manifest.get("dataModelHash") != current_dmhash)
    current_ihash = integration_hash(project_dir, openspec_dir, sources, archived, active)
    integration_dirty = (not manifest or not manifest.get("integrationSynced")
                         or manifest.get("integrationHash") != current_ihash)

    missing_artifacts = [f for f in artifact_files()
                         if not os.path.isfile(os.path.join(wiki_dir, f))]
    readme_dirty = bool(overview_dirty or missing_artifacts)

    artifacts = []
    if mode == "full":
        artifacts = ["README.md", "architecture.md", "decisions.md", "glossary.md",
                     "api.md", "data-model.md", "integrations.md",
                     "specs/*.md", "changelog.md"]
    else:
        if readme_dirty:
            artifacts.append("README.md")
        if architecture_dirty:
            artifacts.append("architecture.md")
        if pending_decisions:
            artifacts.append("decisions.md")
        if glossary_dirty:
            artifacts.append("glossary.md")
        if api_dirty:
            artifacts.append("api.md")
        if data_model_dirty:
            artifacts.append("data-model.md")
        if integration_dirty:
            artifacts.append("integrations.md")
        if to_generate:
            artifacts.append("specs/*.md")
        if pending:
            artifacts.append("changelog.md")

    plan = {
        "project": project_dir,
        "wikiDir": wiki_dir,
        "mode": mode,
        "artifactsToGenerate": artifacts,
        "allCapabilities": caps,
        "capabilitiesToGenerate": to_generate,
        "driftedCapabilities": drifted,
        "missingPages": missing_pages,
        "capabilitiesRemoved": removed,
        "pendingChanges": pending,
        "pendingDecisions": pending_decisions,
        "activeChanges": active,
        "overviewDirty": overview_dirty,
        "readmeDirty": readme_dirty,
        "architectureDirty": architecture_dirty,
        "glossaryDirty": glossary_dirty,
        "apiDirty": api_dirty,
        "dataModelDirty": data_model_dirty,
        "integrationDirty": integration_dirty,
        "changelogDirty": bool(pending),
        "stats": {
            "capabilities": len(caps),
            "archivedChanges": len(archived),
            "syncedChanges": len(synced_changes),
            "pendingChanges": len(pending),
            "decisionsSynced": len(synced_decisions),
            "pendingDecisions": len(pending_decisions),
            "changesWithDesign": len([c for c in archived if c["design"]]),
            "sourceFilesScanned": len(sources),
            "apiEndpoints": extract_api(sources, ddl_cols)["endpointCount"],
            "dataTables": dm["tableCount"],
            "dataColumns": sum(len(t.get("columns") or []) for t in dm["tables"]),
        },
    }
    print(json.dumps(plan, ensure_ascii=False, indent=2))


def cmd_commit(args):
    project_dir = os.path.abspath(args.project)
    openspec_dir = os.path.join(project_dir, "openspec")
    if not os.path.isdir(openspec_dir):
        die("项目目录下不存在 openspec/：%s" % project_dir)
    wiki_dir = os.path.join(project_dir, "wiki")
    manifest = load_manifest(wiki_dir) or {
        "version": MANIFEST_VERSION,
        "overviewSynced": False,
        "specs": {},
        "syncedChanges": {},
        "decisions": {},
    }
    manifest.setdefault("decisions", {})
    manifest.setdefault("specs", {})
    manifest.setdefault("syncedChanges", {})

    caps = [c for c in (args.caps or "").split(",") if c]
    for cap in caps:
        spec_file = os.path.join(openspec_dir, "specs", cap, "spec.md")
        if os.path.isfile(spec_file):
            manifest["specs"][cap] = {"hash": sha256_file(spec_file), "syncedAt": now_iso()}
        else:
            print("warn: capability 不存在，跳过：%s" % cap, file=sys.stderr)

    remove_caps = [c for c in (args.remove_caps or "").split(",") if c]
    for cap in remove_caps:
        manifest["specs"].pop(cap, None)

    archived, active = scan_change_dirs(openspec_dir)
    all_entries = archived + active
    slug_map = {change_slug(e): e for e in all_entries}
    resolved = {}

    def find_change(cid):
        """按 id 定位变更：先用目录 slug 快匹配（不触盘），必要时才解析 proposal.md。"""
        if cid in resolved:
            return resolved[cid]
        entry = slug_map.get(cid)
        if entry is None:
            for e in all_entries:
                if "id" not in e:
                    resolve_change(openspec_dir, e)
                if e["id"] == cid:
                    entry = e
                    break
        if entry is None:
            return None
        if "id" not in entry:
            resolve_change(openspec_dir, entry)
        resolved[entry["id"]] = entry
        return entry

    change_ids = [c for c in (args.change_ids or "").split(",") if c]
    for cid in change_ids:
        change = find_change(cid)
        if not change:
            print("warn: change 不存在，跳过：%s" % cid, file=sys.stderr)
            continue
        manifest["syncedChanges"][cid] = {
            "dir": change["dir"],
            "capabilities": change["capabilities"],
            "syncedAt": now_iso(),
        }

    decision_ids = [c for c in (args.decisions or "").split(",") if c]
    for cid in decision_ids:
        change = find_change(cid)
        if not change or not change["design"]:
            print("warn: change 无 design.md，跳过决策记账：%s" % cid, file=sys.stderr)
            continue
        manifest["decisions"][cid] = {
            "dir": change["dir"],
            "designHash": change["designHash"],
            "syncedAt": now_iso(),
        }

    if args.overview:
        manifest["overviewSynced"] = True
        manifest["overviewHash"] = overview_hash(project_dir, openspec_dir)

    if args.architecture:
        manifest["architectureSynced"] = True
        manifest["architectureHash"] = architecture_hash(
            project_dir, openspec_dir, list_capabilities(openspec_dir), archived, active)

    if args.glossary:
        manifest["glossarySynced"] = True
        manifest["glossaryHash"] = glossary_digest(openspec_dir, list_capabilities(openspec_dir))

    if args.api or args.data_model or args.integrations:
        sources = scan_sources(project_dir)
        dm = extract_data_model(sources)
        ddl_cols = ddl_column_index(dm)
        if args.api:
            manifest["apiSynced"] = True
            manifest["apiHash"] = api_hash(sources, ddl_cols)
        if args.data_model:
            manifest["dataModelSynced"] = True
            manifest["dataModelHash"] = data_model_hash(sources, dm)
        if args.integrations:
            manifest["integrationSynced"] = True
            manifest["integrationHash"] = integration_hash(
                project_dir, openspec_dir, sources, archived, active)

    manifest["version"] = MANIFEST_VERSION
    manifest["lastSyncAt"] = now_iso()
    save_manifest(wiki_dir, manifest)
    print(json.dumps({
        "ok": True,
        "committedCaps": caps,
        "removedCaps": remove_caps,
        "committedChanges": change_ids,
        "committedDecisions": decision_ids,
        "overview": bool(args.overview),
        "architecture": bool(args.architecture),
        "glossary": bool(args.glossary),
        "api": bool(args.api),
        "dataModel": bool(args.data_model),
        "integrations": bool(args.integrations),
        "lastSyncAt": manifest["lastSyncAt"],
    }, ensure_ascii=False, indent=2))


def cmd_extract(args):
    """输出声明类提取结果（JSON），供 LLM 直接组织页面，无需重读源码。"""
    project_dir = os.path.abspath(args.project)
    openspec_dir = os.path.join(project_dir, "openspec")
    if not os.path.isdir(openspec_dir):
        die("项目目录下不存在 openspec/：%s" % project_dir)
    live = getattr(args, "only", None)
    if live:
        targets = [s.strip() for s in live.split(",") if s.strip()]
    else:
        targets = ["api", "dataModel", "integrations"]
    sources = scan_sources(project_dir)
    archived, active = scan_change_dirs(openspec_dir)
    dm = extract_data_model(sources)
    out = {"project": project_dir, "sourceFilesScanned": len(sources)}
    if "api" in targets:
        out["api"] = extract_api(sources, ddl_column_index(dm))
    if "dataModel" in targets:
        out["dataModel"] = dm
    if "integrations" in targets:
        out["integrations"] = extract_integrations(
            project_dir, openspec_dir, sources, archived, active)
    print(json.dumps(out, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="openspec-wiki 同步状态工具")
    sub = parser.add_subparsers(dest="command", required=True)

    p_plan = sub.add_parser("plan", help="输出本次同步计划（JSON）")
    p_plan.add_argument("project", help="项目目录（须含 openspec/）")
    p_plan.set_defaults(func=cmd_plan)

    p_commit = sub.add_parser("commit", help="生成完成后记账")
    p_commit.add_argument("project", help="项目目录（须含 openspec/）")
    p_commit.add_argument("--caps", default="", help="本次(重)生成的能力，逗号分隔")
    p_commit.add_argument("--change-ids", default="", help="本次已写入 changelog 的变更 ID，逗号分隔")
    p_commit.add_argument("--remove-caps", default="", help="已从 wiki 删除页面的能力，逗号分隔")
    p_commit.add_argument("--decisions", default="", help="本次已提取进 decisions.md 的变更 ID，逗号分隔")
    p_commit.add_argument("--overview", action="store_true", help="总览页（README.md）本次已更新")
    p_commit.add_argument("--architecture", action="store_true", help="架构页本次已更新")
    p_commit.add_argument("--glossary", action="store_true", help="术语表本次已更新")
    p_commit.add_argument("--api", action="store_true", help="接口清单页本次已更新")
    p_commit.add_argument("--data-model", dest="data_model", action="store_true",
                          help="数据库设计页本次已更新")
    p_commit.add_argument("--integrations", action="store_true", help="外部集成页本次已更新")
    p_commit.set_defaults(func=cmd_commit)

    p_extract = sub.add_parser("extract", help="输出声明类提取结果（JSON）")
    p_extract.add_argument("project", help="项目目录（须含 openspec/）")
    p_extract.add_argument("--only", default="",
                           help="只提取指定部分：api,dataModel,integrations 逗号分隔")
    p_extract.set_defaults(func=cmd_extract)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
