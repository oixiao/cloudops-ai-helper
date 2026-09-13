# -*- coding: utf-8 -*-
"""
推送前安全审计 — 检查密钥泄露风险

用法：python scripts/security_check.py
说明：自动定位项目根目录，扫描所有被 git 跟踪的文件（含二进制 Word 文档），
      检查是否存在 API 密钥泄露。建议在每次 push 前运行一次。
"""
import os
import re
import subprocess
import sys
import zipfile

# 自动定位项目根目录：本文件位于 <项目根>/scripts/ 下
PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PROJECT)

# 真实密钥的特征（严格匹配，避免 mask-image / task-input 这类误报）
PATTERNS = [
    ("DeepSeek/OpenAI 密钥", re.compile(rb"sk-[A-Za-z0-9]{20,}")),
    ("GitHub 经典令牌", re.compile(rb"ghp_[A-Za-z0-9]{20,}")),
    ("GitHub 细粒度令牌", re.compile(rb"github_pat_[A-Za-z0-9_]{20,}")),
    ("ARK 密钥被真实赋值", re.compile(rb"ARK_API_KEY\s*=\s*[A-Za-z0-9\-]{24,}")),
    ("DeepSeek 密钥被真实赋值", re.compile(rb"DEEPSEEK_API_KEY\s*=\s*sk-[A-Za-z0-9]{20,}")),
    ("OpenAI 密钥被真实赋值", re.compile(rb"OPENAI_API_KEY\s*=\s*sk-[A-Za-z0-9]{20,}")),
]

print("=" * 60)
print("  推送前安全审计")
print("=" * 60)
print()

# ---------- 1. 获取被跟踪文件（用 -z 正确处理含空格的文件名） ----------
raw = subprocess.run(["git", "ls-files", "-z"], capture_output=True).stdout
tracked = [x.decode("utf-8") for x in raw.split(b"\x00") if x]
print(f"[1] 版本库中被跟踪的文件数: {len(tracked)}")

# ---------- 2. 逐个扫描 ----------
print()
print("[2] 扫描所有被跟踪的文件")
hits = []
for rel in tracked:
    path = os.path.join(PROJECT, rel)
    if not os.path.isfile(path):
        print(f"    [警告] 已跟踪但磁盘上不存在: {rel}")
        continue
    with open(path, "rb") as f:
        data = f.read()
    for name, pat in PATTERNS:
        for m in pat.finditer(data):
            hits.append((rel, name))
            print(f"    [危险] {rel} -> {name}")

if not hits:
    print("    全部干净，未发现任何密钥")
print()

# ---------- 3. 检查 .env 是否被跟踪 ----------
print("[3] 检查 .env")
if ".env" in tracked:
    print("    [危险] .env 被 git 跟踪了！")
    hits.append((".env", "配置文件被跟踪"))
else:
    print("    [安全] .env 不在版本库中")
print()

# ---------- 4. 找出未跟踪的文件（看看有什么没提交） ----------
print("[4] 工作区中未被跟踪的文件")
untracked_raw = subprocess.run(
    ["git", "status", "--porcelain", "-z", "--untracked-files=all"],
    capture_output=True,
).stdout
entries = [x.decode("utf-8") for x in untracked_raw.split(b"\x00") if x]
untracked = [e[3:] for e in entries if e.startswith("?? ")]
if untracked:
    for u in untracked:
        size = ""
        fp = os.path.join(PROJECT, u)
        if os.path.isfile(fp):
            size = f"  ({os.path.getsize(fp) / 1024:.1f} KB)"
        print(f"    未跟踪: {u}{size}")
else:
    print("    无未跟踪文件（全部已提交）")
print()

# ---------- 5. 深度检查 docx（二进制，git grep 搜不到） ----------
print("[5] 深度检查工作区中的所有 Word 文档")
docx_files = [f for f in os.listdir(PROJECT) if f.lower().endswith(".docx")]
if not docx_files:
    print("    未找到 .docx 文件")
for name in docx_files:
    fp = os.path.join(PROJECT, name)
    print(f"    文件: {name}  ({os.path.getsize(fp) / 1024:.1f} KB)")
    docx_hits = 0
    try:
        with zipfile.ZipFile(fp) as z:
            xmls = [n for n in z.namelist() if n.endswith(".xml")]
            print(f"      内含 {len(xmls)} 个 XML 部件")
            for n in xmls:
                data = z.read(n)
                for pname, pat in PATTERNS:
                    for m in pat.finditer(data):
                        docx_hits += 1
                        print(f"      [危险] {n} -> {pname}")
    except Exception as e:
        print(f"      读取失败: {e}")
        continue
    if docx_hits == 0:
        print("      [安全] 未发现任何密钥")
    else:
        hits.append((name, "Word 文档内含密钥"))
print()

# ---------- 6. 最终判定 ----------
print("=" * 60)
if hits:
    print("  结论: 发现泄露风险，禁止推送！")
    for rel, name in hits:
        print(f"        {rel} -> {name}")
    sys.exit(1)
else:
    print("  结论: 全部安全，可以放心推送")
print("=" * 60)
