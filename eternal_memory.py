"""Eternal Memories - 本地优先的永恒记忆系统核心引擎.

零第三方依赖：仅使用 Python 标准库。
自研六臂融合召回、四类关系图、证据分级与矛盾治理，
以单 SQLite 文件承载全部记忆，零第三方依赖。

数据全部落在单个 SQLite 文件；所有写入按内容哈希幂等。
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import math
import os
import re
import sqlite3
import threading
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

ARMS = ("lex", "act", "graph", "profile", "temporal", "causal")
ARM_WEIGHTS = {"lex": 1.0, "act": 0.85, "graph": 0.95, "profile": 0.8, "temporal": 0.7, "causal": 0.9}
# 精确词法命中优先级：与 ARM_WEIGHTS 正交，仅作用于 lex 臂前三名的名次加成，集中配置避免散落魔数。
LEX_RANK_BOOST = (3.0, 2.0, 1.5)
EDGE_KINDS = ("temporal", "entity", "causal", "semantic")
EVIDENCE = ("extracted", "inferred", "ambiguous")
MEMORY_TYPES = ("semantic", "episodic", "procedural", "preference", "fact", "identity")

_STOP = {"的", "了", "和", "是", "在", "我", "你", "他", "她", "它", "这", "那", "有", "及", "与", "或", "一个", "the", "a", "an", "of", "to", "and", "or", "is", "it", "for", "on", "in"}

# 轻量概念词典：零依赖的语义扩展，补上向量检索缺席时的同义召回通道。
_CONCEPTS = (
    ("记忆", "召回", "检索", "星云", "remember", "recall"),
    ("项目", "计划", "任务", "排期", "里程碑", "复盘"),
    ("文档", "方案", "规则", "流程", "模板", "规范"),
    ("数据", "统计", "同比", "增速", "excel", "报表"),
    ("协作", "会议", "纪要", "待办", "责任人", "跟进"),
    ("偏好", "输出", "格式", "结论", "占位符", "表格"),
    ("边界", "隐私", "脱敏", "敏感", "约束", "容错"),
)


def _concept_expand(qtoks: list[str]) -> list[str]:
    """查询同义扩展：命中任一概念词时，补入同组词的 token（低权重）。"""
    seen = set(qtoks)
    extra: list[str] = []
    for group in _CONCEPTS:
        if not any(w in seen for w in group):
            continue
        for word in group:
            for tok in _tokens(word):
                if tok not in seen and tok not in extra:
                    extra.append(tok)
    return extra[:12]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
        # 统一补时区：兼容外部导入的无时区时间字符串，避免与 UTC now 相减报错
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _tokens(text: str) -> list[str]:
    """中文 bigram + 英文词，兼顾中文召回与英文精确匹配。"""
    if not text:
        return []
    out: list[str] = []
    for chunk in re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z0-9_]+", text.lower()):
        if re.match(r"[a-zA-Z0-9_]", chunk):
            if chunk not in _STOP:
                out.append(chunk)
            continue
        if len(chunk) == 1:
            out.append(chunk)
            continue
        for i in range(len(chunk) - 1):
            bg = chunk[i : i + 2]
            if bg not in _STOP:
                out.append(bg)
    return out


def _jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


class EternalMemory:
    """永恒记忆系统：存储、六臂召回、图治理、导入导出。"""

    def __init__(self, data_dir: str | os.PathLike[str] | None = None):
        default_dir = os.environ.get("EM_DATA_DIR") or str(Path(__file__).resolve().parent / "data")
        base = Path(data_dir) if data_dir else Path(default_dir)
        base.mkdir(parents=True, exist_ok=True)
        self.data_dir = base
        self.db_path = base / "eternal.db"
        self._lock = threading.RLock()
        self._inv: dict[str, set[str]] = {}
        self._df: dict[str, int] = {}
        self._doc_tokens: dict[str, Counter[str]] = {}
        self._dirty = True
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_db()

    # ------------------------------------------------------------------ db
    def _init_db(self) -> None:
        with self._lock, self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    title TEXT DEFAULT '',
                    summary TEXT DEFAULT '',
                    memory_type TEXT DEFAULT 'semantic',
                    source TEXT DEFAULT 'manual',
                    tags TEXT DEFAULT '[]',
                    weight REAL DEFAULT 0.7,
                    importance REAL DEFAULT 0.5,
                    base_importance REAL,
                    stability REAL DEFAULT 7.0,
                    last_review TEXT,
                    hits INTEGER DEFAULT 0,
                    pinned INTEGER DEFAULT 0,
                    archived INTEGER DEFAULT 0,
                    created_at TEXT,
                    updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS edges (
                    id TEXT PRIMARY KEY,
                    src TEXT NOT NULL,
                    dst TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    evidence TEXT DEFAULT 'inferred',
                    confidence REAL DEFAULT 0.6,
                    note TEXT DEFAULT '',
                    created_at TEXT,
                    FOREIGN KEY(src) REFERENCES memories(id) ON DELETE CASCADE,
                    FOREIGN KEY(dst) REFERENCES memories(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS traces (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT,
                    result_ids TEXT,
                    arm_detail TEXT,
                    created_at TEXT
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_mem_type ON memories(memory_type);
                CREATE INDEX IF NOT EXISTS idx_mem_source ON memories(source);
                CREATE INDEX IF NOT EXISTS idx_edges_kind ON edges(kind);
                CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src);
                """
            )
            # 迁移：为旧库补 base_importance 列（幂等），并回填所有空值（含部分迁移库）。
            cols = {r[1] for r in self._conn.execute("PRAGMA table_info(memories)")}
            if "base_importance" not in cols:
                self._conn.execute("ALTER TABLE memories ADD COLUMN base_importance REAL")
            self._conn.execute("UPDATE memories SET base_importance=importance WHERE base_importance IS NULL")

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _setting(self, key: str, default: str | None = None) -> str | None:
        row = self._conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def _set_setting(self, key: str, value: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    # --------------------------------------------------------------- index
    def _rebuild_index(self) -> None:
        if not self._dirty:
            return
        with self._lock:
            self._inv = defaultdict(set)
            self._df = defaultdict(int)
            self._doc_tokens = {}
            rows = self._conn.execute(
                "SELECT id, content, title, tags FROM memories WHERE archived=0"
            ).fetchall()
            for row in rows:
                toks = _tokens(f"{row['title']} {row['content']} {row['tags']}")
                counter = Counter(toks)
                self._doc_tokens[row["id"]] = counter
                for tok in counter:
                    self._inv[tok].add(row["id"])
                    self._df[tok] += 1
            self._dirty = False

    @staticmethod
    def _mid(*parts: str) -> str:
        raw = "|".join(parts)
        return hashlib.sha256(raw.encode("utf-8", "ignore")).hexdigest()[:16]

    # ---------------------------------------------------------------- CRUD
    def remember(
        self,
        content: str,
        title: str = "",
        memory_type: str = "semantic",
        tags: list[str] | str | None = None,
        source: str = "manual",
        weight: float = 0.7,
        importance: float = 0.5,
        pinned: bool = False,
        created_at: str | None = None,
    ) -> tuple[str, bool]:
        """写入一条记忆。返回 (id, 是否新增)。同 source+content 幂等。"""
        content = (content or "").strip()
        if not content:
            raise ValueError("content 不能为空")
        if memory_type not in MEMORY_TYPES:
            memory_type = "semantic"
        if isinstance(tags, str):
            tags = [t.strip() for t in re.split(r"[,，\s]+", tags) if t.strip()]
        tags = list(dict.fromkeys(tags or []))
        mid = self._mid(source, content)
        now = _now()
        with self._lock, self._conn:
            exists = self._conn.execute("SELECT id FROM memories WHERE id=?", (mid,)).fetchone()
            if exists:
                self._conn.execute(
                    "UPDATE memories SET updated_at=? WHERE id=?", (now, mid)
                )
                return mid, False
            self._conn.execute(
                """INSERT INTO memories
                   (id,content,title,summary,memory_type,source,tags,weight,importance,base_importance,
                    stability,last_review,hits,pinned,archived,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?,?)""",
                (
                    mid,
                    content,
                    title or content[:40],
                    content[:120],
                    memory_type,
                    source,
                    json.dumps(tags, ensure_ascii=False),
                    float(weight),
                    float(importance),
                    float(importance),
                    7.0,
                    None,
                    0,
                    int(bool(pinned)),
                    created_at or now,
                    now,
                ),
            )
        self._dirty = True
        return mid, True

    def link(
        self,
        src: str,
        dst: str,
        kind: str = "semantic",
        evidence: str = "inferred",
        confidence: float = 0.6,
        note: str = "",
    ) -> str:
        if kind not in EDGE_KINDS:
            kind = "semantic"
        if evidence not in EVIDENCE:
            evidence = "inferred"
        eid = self._mid(src, dst, kind)
        with self._lock, self._conn:
            self._conn.execute(
                """INSERT OR IGNORE INTO edges(id,src,dst,kind,evidence,confidence,note,created_at)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (eid, src, dst, kind, evidence, float(confidence), note, _now()),
            )
        return eid

    def get(self, mid: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM memories WHERE id=?", (mid,)).fetchone()
        return dict(row) if row else None

    def archive(self, mid: str) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute("UPDATE memories SET archived=1 WHERE id=?", (mid,))
        self._dirty = True
        return cur.rowcount > 0

    def pin(self, mid: str, pinned: bool = True) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute("UPDATE memories SET pinned=? WHERE id=?", (int(pinned), mid))
        return cur.rowcount > 0

    def forget(self, mid: str) -> bool:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM edges WHERE src=? OR dst=?", (mid, mid))
            cur = self._conn.execute("DELETE FROM memories WHERE id=?", (mid,))
        self._dirty = True
        return cur.rowcount > 0

    # --------------------------------------------------------------- recall
    def _arm_lex(self, qtoks: list[str], limit: int) -> dict[str, float]:
        self._rebuild_index()
        if not qtoks or not self._doc_tokens:
            return {}
        n = max(len(self._doc_tokens), 1)
        qtf = Counter(qtoks)
        # 语义扩展词以 0.35 权重参与，避免概念泛化压过原始查询
        for tok in _concept_expand(qtoks):
            qtf[tok] = qtf.get(tok, 0) + 0.35
        qnorm = math.sqrt(sum((tf * math.log(1 + n / (1 + self._df.get(t, 0)))) ** 2 for t, tf in qtf.items()))
        if not qnorm:
            return {}
        scores: dict[str, float] = {}
        for tok, qtfreq in qtf.items():
            ids = self._inv.get(tok)
            if not ids:
                continue
            idf = math.log(1 + n / (1 + self._df[tok]))
            qpart = qtfreq * idf
            for mid in ids:
                dtf = self._doc_tokens[mid][tok]
                dpart = dtf * idf
                scores[mid] = scores.get(mid, 0.0) + qpart * dpart
        if not scores:
            return {}
        norm = max(scores.values()) or 1.0
        top = sorted(scores.items(), key=lambda x: -x[1])[:limit]
        # 分数统一归一到 [0,1]，与其他臂口径一致（RRF 用名次，不依赖该绝对值）。
        return {mid: s / norm for mid, s in top}

    def _arm_act(self, limit: int) -> dict[str, float]:
        now = datetime.now(timezone.utc)
        rows = self._conn.execute(
            "SELECT id,weight,importance,stability,hits,pinned,last_review,created_at FROM memories WHERE archived=0"
        ).fetchall()
        scored: list[tuple[str, float]] = []
        for r in rows:
            # 衰减基准用创建时间：last_review 只作短期激活加分，避免越召回越活跃的正反馈。
            ts = _parse_ts(r["created_at"])
            age = max((now - ts).total_seconds() / 86400, 0) if ts else 0
            decay = math.exp(-age / max(r["stability"] or 7.0, 1.0))
            boost = 1 + 0.12 * math.log1p(r["hits"] or 0)
            pin = 1.5 if r["pinned"] else 1.0
            scored.append((r["id"], (r["weight"] or 0.5) * (r["importance"] or 0.5) * decay * boost * pin))
        scored.sort(key=lambda x: -x[1])
        top = scored[:limit]
        if not top:
            return {}
        mx = top[0][1] or 1.0
        return {mid: s / mx for mid, s in top}

    def _neighbors(self, seeds: list[str], hops: int = 2) -> dict[str, float]:
        if not seeds:
            return {}
        scores: dict[str, float] = {s: 1.0 for s in seeds}
        frontier = list(seeds)
        for hop in range(1, hops + 1):
            nxt: dict[str, float] = {}
            placeholders = ",".join("?" for _ in frontier)
            rows = self._conn.execute(
                f"SELECT src,dst,kind,confidence FROM edges WHERE src IN ({placeholders}) OR dst IN ({placeholders})",
                tuple(frontier) + tuple(frontier),
            ).fetchall()
            kw = {"causal": 1.3, "entity": 1.1, "semantic": 1.0, "temporal": 0.9}
            for r in rows:
                other = r["dst"] if r["src"] in frontier else r["src"]
                gain = (1.0 / (hop + 1)) * kw.get(r["kind"], 1.0) * (r["confidence"] or 0.6)
                nxt[other] = max(nxt.get(other, 0.0), scores.get(r["src"] if other == r["dst"] else r["dst"], 1.0) * gain)
            if not nxt:
                break
            for mid, s in nxt.items():
                scores[mid] = max(scores.get(mid, 0.0), s)
            frontier = list(nxt.keys())
        seed_set = set(seeds)
        neighbors = {mid: s for mid, s in scores.items() if mid not in seed_set}
        if not neighbors:
            return {}
        mx = max(neighbors.values()) or 1.0
        return {mid: s / mx for mid, s in neighbors.items()}

    def _entity_seeds(self, qtoks: list[str], limit: int) -> list[str]:
        """从 tags/title 与查询词重叠构造种子，作为图臂/因果臂的独立入口。"""
        if not qtoks:
            return []
        qset = set(qtoks)
        rows = self._conn.execute(
            "SELECT id,title,tags FROM memories WHERE archived=0"
        ).fetchall()
        scored: list[tuple[str, float]] = []
        for r in rows:
            toks = set(_tokens(f"{r['title']} {r['tags']}"))
            overlap = _jaccard(qset, toks)
            if overlap > 0:
                scored.append((r["id"], overlap))
        scored.sort(key=lambda x: -x[1])
        return [mid for mid, _ in scored[:limit]]

    def _arm_graph(self, seeds: list[str], limit: int) -> dict[str, float]:
        res = self._neighbors(seeds[:12], hops=2)
        return dict(sorted(res.items(), key=lambda x: -x[1])[:limit])

    def _arm_causal(self, seeds: list[str], limit: int) -> dict[str, float]:
        if not seeds:
            return {}
        placeholders = ",".join("?" for _ in seeds[:12])
        rows = self._conn.execute(
            f"SELECT src,dst,confidence FROM edges WHERE kind='causal' AND (src IN ({placeholders}) OR dst IN ({placeholders}))",
            tuple(seeds[:12]) + tuple(seeds[:12]),
        ).fetchall()
        scores: dict[str, float] = {}
        for r in rows:
            other = r["dst"] if r["src"] in seeds[:12] else r["src"]
            scores[other] = max(scores.get(other, 0.0), r["confidence"] or 0.6)
        return dict(sorted(scores.items(), key=lambda x: -x[1])[:limit])

    def _arm_profile(self, qtoks: list[str], limit: int) -> dict[str, float]:
        rows = self._conn.execute(
            """SELECT id,title,content,tags,memory_type,pinned FROM memories
               WHERE archived=0 AND (memory_type IN ('preference','identity') OR pinned=1)"""
        ).fetchall()
        scored: dict[str, float] = {}
        for r in rows:
            toks = _tokens(f"{r['title']} {r['content']} {r['tags']}")
            overlap = _jaccard(qtoks, toks) if qtoks else 0.0
            base = 0.55 if (r["pinned"] or r["memory_type"] == "identity") else 0.35
            scored[r["id"]] = min(1.0, base + overlap)
        return dict(sorted(scored.items(), key=lambda x: -x[1])[:limit])

    def _arm_temporal(self, query: str, qtoks: list[str], limit: int) -> dict[str, float]:
        now = datetime.now(timezone.utc)
        recent = any(k in query for k in ("最近", "近期", "今天", "昨天", "上周", "这周", "本月", "recent", "latest"))
        years = re.findall(r"(20\d{2})年?", query)
        months = re.findall(r"(20\d{2})[-/](\d{1,2})", query)
        rows = self._conn.execute("SELECT id,created_at FROM memories WHERE archived=0").fetchall()
        scored: dict[str, float] = {}
        for r in rows:
            ts = _parse_ts(r["created_at"])
            if not ts:
                continue
            s = 0.35 if recent else 0.15
            if years and any(y == str(ts.year) for y in years):
                s += 0.5
            if months and any(int(y) == ts.year and int(m) == ts.month for y, m in months):
                s += 0.5
            age = (now - ts).days
            s += max(0.0, 0.3 - age / 2000.0)
            scored[r["id"]] = min(1.0, s)
        return dict(sorted(scored.items(), key=lambda x: -x[1])[:limit])

    def recall(
        self,
        query: str,
        top_k: int = 8,
        arms: list[str] | None = None,
        min_score: float = 0.0,
        trace: bool = True,
    ) -> dict[str, Any]:
        """六臂召回 + RRF 融合，返回命中、分臂分数与可直接注入的上下文包。"""
        active = [a for a in (arms or ARMS) if a in ARMS] or list(ARMS)
        qtoks = _tokens(query)
        cands = max(top_k * 4, 24)
        per: dict[str, dict[str, float]] = {}
        per["lex"] = self._arm_lex(qtoks, cands)
        per["act"] = self._arm_act(cands)
        lex_seeds = list(per["lex"].keys())
        # 独立入口：从 tags/title 命中构造实体种子，保证无词法命中时图臂/因果臂仍可工作。
        entity_seeds = self._entity_seeds(qtoks, cands)
        graph_seeds = list(dict.fromkeys(lex_seeds + entity_seeds))
        per["graph"] = self._arm_graph(graph_seeds, cands)
        per["profile"] = self._arm_profile(qtoks, cands)
        per["temporal"] = self._arm_temporal(query, qtoks, cands)
        per["causal"] = self._arm_causal(graph_seeds, cands)

        fused: dict[str, float] = defaultdict(float)
        hit_arms: dict[str, list[str]] = defaultdict(list)
        for arm in active:
            ranked = sorted(per.get(arm, {}).items(), key=lambda x: -x[1])
            for rank, (mid, _) in enumerate(ranked):
                score = ARM_WEIGHTS[arm] / (60 + rank + 1)
                # 精确词法命中优先（名次加成为显式配置，避免高频短记忆靠多臂累积压过真正匹配项）。
                if arm == "lex" and rank < len(LEX_RANK_BOOST):
                    score *= LEX_RANK_BOOST[rank]
                fused[mid] += score
                hit_arms[mid].append(arm)

        items: list[dict[str, Any]] = []
        for mid, score in sorted(fused.items(), key=lambda x: -x[1])[:top_k]:
            if score < min_score:
                continue
            row = self.get(mid)
            if not row or row.get("archived"):
                continue
            row["tags"] = json.loads(row.get("tags") or "[]")
            row["score"] = round(score * 100, 4)
            row["arms"] = hit_arms.get(mid, [])
            row["arm_scores"] = {a: round(per.get(a, {}).get(mid, 0.0), 4) for a in active}
            items.append(row)

        # trace=False 表示只读召回（如自动 hook 注入），不写 hits/last_review/trace，
        # 避免统计口径被自动召回污染，也避免 last_review 刷新干扰衰减。
        if trace:
            with self._lock, self._conn:
                for it in items:
                    self._conn.execute(
                        "UPDATE memories SET hits=hits+1, last_review=? WHERE id=?", (_now(), it["id"])
                    )
                self._conn.execute(
                    "INSERT INTO traces(query,result_ids,arm_detail,created_at) VALUES(?,?,?,?)",
                    (
                        query,
                        json.dumps([i["id"] for i in items]),
                        json.dumps({a: len(per.get(a, {})) for a in active}, ensure_ascii=False),
                        _now(),
                    ),
                )

        context = "\n".join(
            f"[{i + 1}] 《{it['title']}》({it['memory_type']}｜{it['source']})\n{it['content']}"
            for i, it in enumerate(items)
        )
        return {
            "query": query,
            "arms": active,
            "arm_counts": {a: len(per.get(a, {})) for a in active},
            "items": items,
            "context_pack": context,
        }

    # ---------------------------------------------------------- governance
    def consolidate(self, decay_days: float = 90.0) -> dict[str, Any]:
        """巩固：重要度衰减、访问提升、过期归档、共享标签建边。

        衰减始终从不随时间变化的 base_importance 重算，避免多次调用把 importance 累乘到 0。
        """
        decay_days = max(float(decay_days or 0), 1.0)  # 除零容错
        now = datetime.now(timezone.utc)
        rows = self._conn.execute(
            "SELECT id,importance,base_importance,hits,pinned,created_at,tags FROM memories WHERE archived=0"
        ).fetchall()
        archived = 0
        with self._lock, self._conn:
            for r in rows:
                ts = _parse_ts(r["created_at"])
                age = max((now - ts).days, 0) if ts else 0
                # 基准值固定：历史库迁移后 base_importance 已回填，旧行缺失时回退到 importance。
                base = r["base_importance"] if r["base_importance"] is not None else (r["importance"] or 0.5)
                decayed = base * math.exp(-age / decay_days) * (1 + 0.05 * math.log1p(r["hits"]))
                decayed = min(max(decayed, 0.0), 1.0)
                if r["pinned"]:
                    decayed = max(decayed, 0.8)
                if decayed < 0.02 and age > 180:
                    self._conn.execute("UPDATE memories SET archived=1 WHERE id=?", (r["id"],))
                    archived += 1
                else:
                    # 只更新展示用的 importance；base_importance 永不写回。
                    self._conn.execute("UPDATE memories SET importance=? WHERE id=?", (round(decayed, 4), r["id"]))

            tag_map: dict[str, list[str]] = defaultdict(list)
            for r in rows:
                for t in json.loads(r["tags"] or "[]"):
                    tag_map[t].append(r["id"])
            linked = 0
            for tag, ids in tag_map.items():
                if len(ids) > 12:
                    continue
                for i in range(len(ids)):
                    for j in range(i + 1, len(ids)):
                        before = self._conn.total_changes
                        self.link(ids[i], ids[j], "semantic", "inferred", 0.45, f"共享标签:{tag}")
                        if self._conn.total_changes > before:
                            linked += 1
        self._dirty = True
        return {"processed": len(rows), "archived": archived, "new_links": linked}

    def find_conflicts(self) -> list[dict[str, Any]]:
        """检测"同一主题 + 肯定/否定共现"的可疑矛盾，只报告不删除。

        改进：否定词带窗口（如"不再允许""未启用"）参与判定，降低脱离上下文的误报与漏报。
        """
        yes = ("启用", "允许", "使用", "保留", "开启", "通过", "有效", "实施")
        no = ("禁用", "不允许", "不是", "停用", "取消", "废弃", "无效", "禁止", "不再", "未启用", "不实施")
        neg_prefix = ("不", "未", "无", "非", "不再")
        def polarity(text: str) -> int:
            # 先把"不/未+肯定词"整体剥离，避免其内部的肯定词被误计为正（"不允许启用"应为负）。
            stripped, negated = text, 0
            for w in yes:
                for p in neg_prefix:
                    phrase = p + w
                    c = stripped.count(phrase)
                    if c:
                        negated += c
                        stripped = stripped.replace(phrase, "※")
            pos = sum(stripped.count(w) for w in yes)
            neg = sum(text.count(w) for w in no) + negated
            return pos - neg
        rows = self._conn.execute(
            "SELECT id,title,content,tags,source FROM memories WHERE archived=0"
        ).fetchall()
        buckets: dict[str, list[sqlite3.Row]] = defaultdict(list)
        for r in rows:
            for t in json.loads(r["tags"] or "[]")[:4]:
                buckets[t].append(r)
        found: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for tag, group in buckets.items():
            if len(group) < 2 or len(group) > 20:
                continue
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    a, b = group[i], group[j]
                    key = tuple(sorted((a["id"], b["id"])))
                    if key in seen:
                        continue
                    ta, tb = _tokens(a["content"]), _tokens(b["content"])
                    overlap = _jaccard(ta, tb)
                    if overlap < 0.18:
                        continue
                    pa, pb = polarity(a["content"]), polarity(b["content"])
                    if (pa > 0 > pb) or (pb > 0 > pa):
                        seen.add(key)
                        found.append(
                            {
                                "tag": tag,
                                "a": {"id": a["id"], "title": a["title"], "content": a["content"][:180], "source": a["source"]},
                                "b": {"id": b["id"], "title": b["title"], "content": b["content"][:180], "source": b["source"]},
                                "overlap": round(overlap, 3),
                            }
                        )
        return found[:50]

    def profile(self) -> dict[str, Any]:
        rows = self._conn.execute(
            "SELECT id,title,content,memory_type,pinned,hits,created_at FROM memories WHERE archived=0 AND (memory_type IN ('identity','preference') OR pinned=1)"
        ).fetchall()
        return {
            "count": len(rows),
            "items": [
                {
                    "id": r["id"],
                    "title": r["title"],
                    "content": r["content"],
                    "type": r["memory_type"],
                    "pinned": bool(r["pinned"]),
                    "hits": r["hits"],
                }
                for r in rows
            ],
        }

    # ----------------------------------------------------------- importing
    def import_nebula_export(self, path: str | os.PathLike[str]) -> dict[str, int]:
        """导入外部记忆系统导出包（memories + edges）。"""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        added = 0
        dup = 0
        mapping: dict[str, str] = {}
        for m in data.get("memories", []):
            mid, is_new = self.remember(
                content=m.get("content", ""),
                title=m.get("title") or m.get("content", "")[:40],
                memory_type=m.get("memory_type") or "semantic",
                tags=m.get("tags") or [],
                source=m.get("source") or "external-import",
                weight=float(m.get("weight") or 0.7),
                importance=float(m.get("weight") or 0.7),
                pinned=bool(m.get("pinned")),
                created_at=m.get("created_at"),
            )
            mapping[str(m.get("id"))] = mid
            added += int(is_new)
            dup += int(not is_new)
        linked = 0
        for e in data.get("edges", []):
            s, d = mapping.get(str(e.get("src") or e.get("from"))), mapping.get(str(e.get("dst") or e.get("to")))
            if not s or not d:
                continue
            before = self._conn.total_changes
            self.link(s, d, "semantic", "extracted", float(e.get("weight") or 0.6), "外部记忆迁移")
            linked += int(self._conn.total_changes > before)
        return {"memories_added": added, "memories_duplicate": dup, "edges": linked}

    def import_markdown(self, path: str | os.PathLike[str], source: str | None = None) -> dict[str, int]:
        """导入 Markdown（iwe 互通）：解析 YAML frontmatter、按标题/空行分段、[[双链]] 自动建 entity 边。"""
        p = Path(path)
        text = p.read_text(encoding="utf-8", errors="ignore")
        meta: dict[str, Any] = {}
        fm = re.match(r"\A---\s*\n([\s\S]*?)\n---\s*\n?", text)
        if fm:
            for line in fm.group(1).splitlines():
                if ":" not in line:
                    continue
                key, _, val = line.partition(":")
                key, val = key.strip(), val.strip().strip("'\"")
                if key in ("title", "memory_type", "source"):
                    meta[key] = val
                elif key == "tags":
                    meta["tags"] = [t.strip() for t in val.strip("[]").split(",") if t.strip()]
                elif key in ("importance", "weight"):
                    try:
                        meta[key] = float(val)
                    except ValueError:
                        pass
            text = text[fm.end():]

        # 先按标题切分，再在段内按空行切分；标题行不受长度阈值限制（修复短标题 #甲 丢失）。
        sections = re.split(r"(?=^#{1,6}\s+)", text, flags=re.M)
        chunks: list[tuple[str, str]] = []
        for sec in sections:
            sec = sec.strip()
            if not sec:
                continue
            hm = re.match(r"^#{1,6}\s+(.+)", sec)
            sec_title = hm.group(1).strip() if hm else ""
            # 标题行本身不单独成记忆（否则与正文重复），仅作为该段所有段落的 title。
            body = sec[hm.end():] if hm else sec
            for para in re.split(r"\n\s*\n", body):
                para = para.strip()
                if not para or not para.strip("# ").strip():
                    continue
                chunks.append((para, sec_title))
        if not chunks and meta.get("title"):
            chunks.append((meta.get("title", ""), meta["title"]))

        added = dup = 0
        ids: list[str] = []
        default_tags = meta.get("tags") or []
        for chunk, sec_title in chunks:
            title = sec_title or meta.get("title", "")
            link_titles = re.findall(r"\[\[([^\]]+)\]\]", chunk)
            tags = list(dict.fromkeys(default_tags + link_titles))[:8]
            mtype = meta.get("memory_type", "")
            if mtype not in MEMORY_TYPES:
                mtype = "preference" if any(k in chunk for k in ("偏好", "要求", "禁忌")) else "semantic"
            mid, is_new = self.remember(
                content=chunk,
                title=title,
                memory_type=mtype,
                tags=tags,
                source=meta.get("source") or source or str(p),
                importance=float(meta.get("importance", 0.5)),
            )
            ids.append(mid)
            added += int(is_new)
            dup += int(not is_new)

        # 双链建边：优先按标题匹配，其次按正文含 [[标题]] 的显示文本匹配。
        by_title = {self.get(mid)["title"]: mid for mid in ids if self.get(mid) and self.get(mid)["title"]}
        for mid in ids:
            row = self.get(mid)
            if not row:
                continue
            for t in json.loads(row["tags"] or "[]"):
                target = by_title.get(t)
                if target and target != mid:
                    self.link(mid, target, "entity", "extracted", 0.75, f"[[{t}]]")
        return {"memories_added": added, "memories_duplicate": dup, "chunks": len(chunks), "frontmatter": bool(fm)}

    def import_workbuddy(
        self,
        profile_dir: str | os.PathLike[str] | None = None,
        workspace_dir: str | os.PathLike[str] | None = None,
        days: int = 180,
    ) -> dict[str, Any]:
        """导入 WorkBuddy 用户 MEMORY.md、工作区日志与外部记忆导出包。

        只读源文件，不改动 WorkBuddy 任何内容。按 source+content 哈希幂等。
        """
        result: dict[str, Any] = {"profile": 0, "workspace": 0, "nebula": {}, "skipped": []}
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        if profile_dir:
            p = Path(profile_dir) / "MEMORY.md"
            if p.exists():
                if datetime.fromtimestamp(p.stat().st_mtime, timezone.utc) >= cutoff:
                    r = self.import_markdown(p, source="workbuddy:profile/MEMORY.md")
                    result["profile"] = r["memories_added"]
                else:
                    result["skipped"].append(f"{p} 超出 {days} 天")
        if workspace_dir:
            md_dir = Path(workspace_dir) / ".workbuddy" / "memory"
            if md_dir.exists():
                for f in sorted(md_dir.glob("*.md")):
                    if datetime.fromtimestamp(f.stat().st_mtime, timezone.utc) >= cutoff:
                        r = self.import_markdown(f, source=f"workbuddy:workspace/{f.name}")
                        result["workspace"] += r["memories_added"]
        neb = Path.home() / ".workbuddy" / "nebula-memory" / "memory-export.json"
        if neb.exists():
            result["nebula"] = self.import_nebula_export(neb)
        return result

    def import_jsonl(self, path: str | os.PathLike[str], text_key: str = "content") -> dict[str, int]:
        p = Path(path)
        added = dup = 0
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            text = obj.get(text_key) or obj.get("text") or obj.get("message")
            if not text:
                continue
            mid, is_new = self.remember(
                content=str(text),
                title=str(obj.get("title") or "")[:80],
                memory_type=obj.get("memory_type") or "episodic",
                tags=obj.get("tags") or [],
                source=str(obj.get("source") or p),
                created_at=obj.get("created_at"),
            )
            added += int(is_new)
            dup += int(not is_new)
        return {"memories_added": added, "memories_duplicate": dup}

    def import_file(self, path: str | os.PathLike[str], source: str | None = None) -> dict[str, int]:
        """按扩展名自动摄取：md/txt/html/eml/jsonl/json（零第三方依赖）。"""
        p = Path(path)
        ext = p.suffix.lower()
        if ext == ".jsonl":
            return self.import_jsonl(p)
        if ext == ".json":
            obj = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
            if isinstance(obj, dict) and "memories" in obj:
                return self.import_nebula_export(p)
            text = (obj.get("content") or obj.get("text") or json.dumps(obj, ensure_ascii=False)) if isinstance(obj, dict) else str(obj)
            mid, is_new = self.remember(
                content=str(text)[:20000], title=str(obj.get("title") or p.stem)[:80] if isinstance(obj, dict) else p.stem,
                memory_type=(obj.get("memory_type") or "semantic") if isinstance(obj, dict) else "semantic",
                tags=(obj.get("tags") or []) if isinstance(obj, dict) else [], source=source or str(p),
            )
            return {"memories_added": int(is_new), "memories_duplicate": int(not is_new)}
        if ext in (".md", ".markdown", ".txt"):
            return self.import_markdown(p, source)
        if ext in (".html", ".htm"):
            raw = p.read_text(encoding="utf-8", errors="ignore")
            raw = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
            text = re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", raw)).strip()
            mid, is_new = self.remember(content=text[:20000], title=p.stem, memory_type="semantic",
                                        tags=[], source=source or str(p))
            return {"memories_added": int(is_new), "memories_duplicate": int(not is_new)}
        if ext == ".eml":
            from email import policy
            from email.parser import BytesParser

            msg = BytesParser(policy=policy.default).parsebytes(p.read_bytes())
            parts: list[str] = []
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        try:
                            parts.append(str(part.get_content()))
                        except (UnicodeDecodeError, LookupError):
                            pass
            else:
                try:
                    parts.append(str(msg.get_content()))
                except (UnicodeDecodeError, LookupError):
                    pass
            body = "\n".join(x for x in parts if x)[:20000]
            mid, is_new = self.remember(content=body, title=str(msg.get("subject") or p.stem),
                                        memory_type="episodic", tags=["邮件"],
                                        source=source or str(msg.get("from") or p.name))
            return {"memories_added": int(is_new), "memories_duplicate": int(not is_new)}
        return {"error": f"unsupported extension: {ext}", "memories_added": 0, "memories_duplicate": 0}

    IMPORT_EXTS = {".md", ".markdown", ".txt", ".html", ".htm", ".eml", ".json", ".jsonl"}
    SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".idea", ".vscode", ".ref", "backups"}

    def import_folder(
        self,
        folder: str | os.PathLike[str],
        recursive: bool = True,
        max_files: int = 200,
        source: str | None = None,
        follow_symlinks: bool = False,
    ) -> dict[str, Any]:
        """批量把本地目录内的文件变成记忆点（幂等，单文件失败不影响整体）。

        - 仅摄取 import_file 支持的扩展名；跳过隐藏文件与常见噪声目录
        - max_files 限制单次导入文件数，防止误选整盘
        - 每个文件复用 import_file，内容哈希幂等，重复导入只跳过
        - 返回 scanned/imported/added/duplicate/skipped/errors 汇总
        """
        root = Path(folder)
        result: dict[str, Any] = {
            "folder": str(root), "scanned": 0, "imported": 0, "memories_added": 0,
            "memories_duplicate": 0, "skipped": [], "errors": [],
        }
        if not root.is_dir():
            result["errors"].append({"path": str(root), "error": "not a directory"})
            return result

        walker = root.rglob("*") if recursive else root.iterdir()
        for p in walker:
            try:
                if not p.is_file():
                    continue
                if p.name.startswith(".") or p.suffix.lower() not in self.IMPORT_EXTS:
                    continue
                if any(part in self.SKIP_DIRS or part.startswith(".") for part in p.relative_to(root).parts[:-1]):
                    continue
                if not follow_symlinks and p.is_symlink():
                    continue
                if p.stat().st_size > 2_000_000:  # 单文件 2MB 上限，避免整本 PDF 转文本撑爆
                    result["skipped"].append({"path": str(p), "reason": "file too large (>2MB)"})
                    continue
                result["scanned"] += 1
                if result["imported"] >= max_files:
                    result["skipped"].append({"path": str(p), "reason": f"max_files={max_files} reached"})
                    continue
                r = self.import_file(p, source or str(root))
                if r.get("error"):
                    result["errors"].append({"path": str(p), "error": r["error"]})
                    continue
                result["imported"] += 1
                result["memories_added"] += int(r.get("memories_added", 0))
                result["memories_duplicate"] += int(r.get("memories_duplicate", 0))
            except Exception as exc:  # noqa: BLE001 - 单文件失败不阻断整批
                result["errors"].append({"path": str(p), "error": f"{type(exc).__name__}: {exc}"})
        return result

    # ----------------------------------------------------------- exporting
    def export_json(self, path: str | os.PathLike[str] | None = None) -> dict[str, Any] | str:
        data = {
            "engine": "eternal-memories",
            "exported_at": _now(),
            "stats": self.stats(),
            "memories": [
                dict(r, tags=json.loads(r["tags"] or "[]")) for r in self._conn.execute("SELECT * FROM memories")
            ],
            "edges": [dict(r) for r in self._conn.execute("SELECT * FROM edges")],
            "traces": [dict(r) for r in self._conn.execute("SELECT * FROM traces ORDER BY id DESC LIMIT 200")],
        }
        if path:
            Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return str(path)
        return data

    def export_markdown(self, out_dir: str | os.PathLike[str]) -> str:
        """导出为可被 iwe 直接索引的 Markdown 双链库。"""
        base = Path(out_dir)
        base.mkdir(parents=True, exist_ok=True)
        vault = base / "vault"
        vault.mkdir(exist_ok=True)
        rows = self._conn.execute("SELECT * FROM memories WHERE archived=0").fetchall()
        title_to_file: dict[str, str] = {}
        for r in rows:
            tagjson = json.loads(r["tags"] or "[]")
            safe = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", r["title"] or r["id"])[:40] or r["id"]
            fn = f"{safe}_{r['id']}.md"  # 用完整 id，杜绝同名标题与 6 位截断碰撞
            title_to_file[r["id"]] = fn
            fm = [
                "---",
                f"id: {r['id']}",
                f"title: {r['title']}",
                f"type: {r['memory_type']}",
                f"source: {r['source']}",
                f"importance: {r['importance']}",
                f"tags: [{', '.join(tagjson)}]",
                "---",
                "",
                f"# {r['title']}",
                "",
                r["content"],
                "",
            ]
            (vault / fn).write_text("\n".join(fm), encoding="utf-8")
        index = ["# Eternal Memories 索引", "", f"共 {len(rows)} 条记忆。", ""]
        for typ in MEMORY_TYPES:
            group = [r for r in rows if r["memory_type"] == typ]
            if not group:
                continue
            index.append(f"## {typ} ({len(group)})")
            index.append("")
            for r in group:
                fn = title_to_file.get(r["id"], "")
                index.append(f"- [{r['title']}]({fn}) — {r['content'][:60]}")
            index.append("")
        (vault / "index.md").write_text("\n".join(index), encoding="utf-8")
        return str(vault)

    def graph_data(self, limit: int = 400) -> dict[str, Any]:
        rows = self._conn.execute(
            "SELECT id,title,content,memory_type,source,tags,weight,importance,hits,pinned,created_at FROM memories WHERE archived=0 ORDER BY importance DESC LIMIT ?",
            (limit,),
        ).fetchall()
        ids = {r["id"] for r in rows}
        nodes = []
        for r in rows:
            nodes.append(
                {
                    "id": r["id"],
                    "title": r["title"],
                    "content": r["content"][:400],
                    "type": r["memory_type"],
                    "source": r["source"],
                    "tags": json.loads(r["tags"] or "[]"),
                    "importance": r["importance"],
                    "hits": r["hits"],
                    "pinned": bool(r["pinned"]),
                    "created_at": r["created_at"],
                }
            )
        edges = []
        for r in self._conn.execute("SELECT src,dst,kind,evidence,confidence FROM edges"):
            if r["src"] in ids and r["dst"] in ids:
                edges.append(dict(r))
        return {"nodes": nodes, "edges": edges, "total": self.stats()["memories"]}

    def stats(self) -> dict[str, Any]:
        def count(sql: str, params: tuple = ()) -> int:
            return int(self._conn.execute(sql, params).fetchone()[0])

        by_type = {
            r["memory_type"]: r["n"]
            for r in self._conn.execute(
                "SELECT memory_type, COUNT(*) n FROM memories WHERE archived=0 GROUP BY memory_type"
            )
        }
        by_edge = {
            r["kind"]: r["n"] for r in self._conn.execute("SELECT kind, COUNT(*) n FROM edges GROUP BY kind")
        }
        by_evidence = {
            r["evidence"]: r["n"]
            for r in self._conn.execute("SELECT evidence, COUNT(*) n FROM edges GROUP BY evidence")
        }
        return {
            "memories": count("SELECT COUNT(*) FROM memories WHERE archived=0"),
            "archived": count("SELECT COUNT(*) FROM memories WHERE archived=1"),
            "edges": count("SELECT COUNT(*) FROM edges"),
            "traces": count("SELECT COUNT(*) FROM traces"),
            "by_type": by_type,
            "by_edge": by_edge,
            "by_evidence": by_evidence,
            "db_bytes": sum(
                p.stat().st_size for p in (self.db_path, Path(str(self.db_path) + "-wal"), Path(str(self.db_path) + "-shm")) if p.exists()
            ),
            "top_hits": [
                dict(r)
                for r in self._conn.execute(
                    "SELECT title,hits,memory_type FROM memories WHERE archived=0 ORDER BY hits DESC LIMIT 8"
                )
            ],
        }

    def backup(self, out_dir: str | os.PathLike[str] | None = None) -> str:
        base = Path(out_dir) if out_dir else self.data_dir
        base.mkdir(parents=True, exist_ok=True)
        dst = base / f"em-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
        with self._lock:
            src = sqlite3.connect(str(self.db_path))
            tgt = sqlite3.connect(str(dst))
            src.backup(tgt)
            tgt.close()
            src.close()
        return str(dst)
