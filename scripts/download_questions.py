#!/usr/bin/env python3
"""Download 2020-2025 成人高考专升本 政治/民法 真题到 questions/ 目录。"""

from __future__ import annotations

import re
import subprocess
import urllib.parse
import urllib.request
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = ROOT / "questions"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# (科目, 年份) -> [(filename, url, kind)]  kind: pdf | html
SOURCES: dict[tuple[str, int], list[tuple[str, str, str]]] = {
    ("政治", 2020): [
        (
            "政治_2020_真题及答案.pdf",
            "https://oss-hqwx-video.hqwx.com/2020年成人高考专升本政治考试真题及答案解析_c7dd1fb85aeb326a965e365d317f809478c0ab2f.pdf",
            "pdf",
        ),
        (
            "政治_2020_真题及答案.html",
            "https://www.aipta.com/article/586.html",
            "html_aipta",
        ),
    ],
    ("政治", 2021): [
        (
            "政治_2021_真题及答案.pdf",
            "https://oss-hqwx-video.hqwx.com/2021年成人高考专升本《政治》真题答案_2dfbeac9825f84957261e0f90984d0b3468cc362.pdf",
            "pdf",
        ),
        (
            "政治_2021_真题及答案.html",
            "http://www.ah-edu.com/beikao/10271.html",
            "html",
        ),
    ],
    ("政治", 2022): [
        (
            "政治_2022_真题.pdf",
            "https://oss-hqwx-video.hqwx.com/2022年成人高考（专升本）政治真题（考生回忆版）_ca6198c642ee2b148b5e52fe8ae1404e7e2fc641.pdf",
            "pdf",
        ),
        (
            "政治_2022_答案.pdf",
            "https://oss-hqwx-video.hqwx.com/2022年成人高考（专升本）政治真题答案（考生回忆版）_e3ff0fa5a454d8b4becff2c7cfd95bc98c122bef.pdf",
            "pdf",
        ),
        (
            "政治_2022_真题及答案.html",
            "https://www.aipta.com/article/6435.html",
            "html_aipta",
        ),
    ],
    ("政治", 2023): [
        (
            "政治_2023_真题及答案.pdf",
            "https://oss-hqwx-video.hqwx.com/2023年成人高考（专升本）政治真题答案（考生回忆版）_8323dd113e17667a07c3483e84acdc1158e1f715.pdf",
            "pdf",
        ),
        (
            "政治_2023_真题及答案.html",
            "https://www.aipta.com/article/9369.html",
            "html_aipta",
        ),
    ],
    ("政治", 2024): [
        (
            "政治_2024_真题及答案.pdf",
            "https://oss-hqwx-video.hqwx.com/2024年成人高考专升本政治真题答案（10.20更新版）_247bb73ce0597ea6c900bdae678347704891fe57.pdf",
            "pdf",
        ),
        (
            "政治_2024_真题及答案.html",
            "https://hbcj1.com/xiangqing?article_id=874",
            "html",
        ),
    ],
    ("政治", 2025): [
        (
            "政治_2025_真题及答案.pdf",
            "https://oss-hqwx-video.hqwx.com/免费-2025年成考专升本政治真题及答案解析_2877f4d0681cfe162eb7d5632337f6920e4dd172.pdf",
            "pdf",
        ),
    ],
    ("民法", 2020): [
        (
            "民法_2020_真题及答案.html",
            "https://www.aipta.com/article/604.html",
            "html_aipta",
        ),
    ],
    ("民法", 2021): [
        (
            "民法_2021_真题及答案.html",
            "https://www.aipta.com/article/603.html",
            "html_aipta",
        ),
    ],
    ("民法", 2022): [
        (
            "民法_2022_答案.pdf",
            "https://oss-hqwx-video.hqwx.com/2022年成人高考（专升本）民法真题答案（考生回忆版）_e93b3b44127e3262510c84a20dad5ee294c64ec3.pdf",
            "pdf",
        ),
        (
            "民法_2022_真题及答案.html",
            "https://www.aipta.com/article/8979.html",
            "html_aipta",
        ),
    ],
    ("民法", 2023): [
        (
            "民法_2023_真题及答案.html",
            "https://www.aipta.com/article/8980.html",
            "html_aipta",
        ),
    ],
    ("民法", 2024): [
        (
            "民法_2024_真题及答案.html",
            "https://www.aipta.com/article/10129.html",
            "html_aipta",
        ),
    ],
    ("民法", 2025): [
        (
            "民法_2025_真题及答案.html",
            "https://www.gdck84.com/show-24-21655-1.html",
            "html",
        ),
    ],
}


def fetch(url: str) -> bytes:
    """优先 curl（兼容中文 URL 与本机证书环境）。"""
    dest = Path("/tmp/question_repo_dl.bin")
    proc = subprocess.run(
        [
            "curl",
            "-fsSL",
            "-A",
            UA,
            "--max-time",
            "120",
            "-o",
            str(dest),
            url,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0 and dest.exists() and dest.stat().st_size > 0:
        data = dest.read_bytes()
        dest.unlink(missing_ok=True)
        return data

    parsed = urllib.parse.urlsplit(url)
    safe_url = urllib.parse.urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            urllib.parse.quote(parsed.path),
            urllib.parse.quote(parsed.query, safe="=&"),
            parsed.fragment,
        )
    )
    req = urllib.request.Request(safe_url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def html_to_text(html: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", "", html, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", "", text, flags=re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p>", "\n", text, flags=re.I)
    text = re.sub(r"</h[1-6]>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_aipta(html: str) -> str:
    m = re.search(r'<div class="info-body">([\s\S]*?)</div>\s*</div>\s*<div class=', html)
    if not m:
        m = re.search(r'class="info-body">([\s\S]*?)(?:<div class="relatelist"|<div class="footer)', html)
    chunk = m.group(1) if m else html
    return html_to_text(chunk)


def extract_generic(html: str) -> str:
    for pattern in (
        r'<div class="content[^"]*">([\s\S]*?)</div>',
        r'<article[\s\S]*?>([\s\S]*?)</article>',
        r'<div id="content"[^>]*>([\s\S]*?)</div>',
    ):
        m = re.search(pattern, html, flags=re.I)
        if m:
            return html_to_text(m.group(1))
    return html_to_text(html)


def save_file(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def save_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def download_one(subject: str, year: int, filename: str, url: str, kind: str) -> dict:
    dest_dir = QUESTIONS / subject / str(year)
    dest = dest_dir / filename
    meta = {
        "subject": subject,
        "year": year,
        "filename": filename,
        "url": url,
        "kind": kind,
        "status": "ok",
        "error": "",
        "bytes": 0,
    }
    try:
        raw = fetch(url)
        meta["bytes"] = len(raw)

        if kind == "pdf":
            save_file(dest, raw)
            return meta

        html = raw.decode("utf-8", errors="replace")
        save_file(dest, raw)

        if kind == "html_aipta":
            text = extract_aipta(html)
        else:
            text = extract_generic(html)

        txt_name = Path(filename).stem + ".txt"
        save_text(dest_dir / txt_name, text)
        return meta
    except Exception as exc:  # noqa: BLE001
        meta["status"] = "failed"
        meta["error"] = str(exc)
        return meta


def build_readme(results: list[dict]) -> str:
    lines = [
        "# 专升本真题下载清单",
        "",
        "科目：**政治**、**民法**（成人高考专升本，法学类）",
        "年份：**2020–2025**",
        "",
        "> 来源为公开网页/PDF，多为考生回忆版，仅供个人学习；若后续入库请自行校对。",
        "",
        "## 目录结构",
        "",
        "```",
        "questions/",
        "  政治/2021/ ...",
        "  民法/2021/ ...",
        "```",
        "",
        "## 下载结果",
        "",
        "| 科目 | 年份 | 文件 | 状态 | 大小 | 来源 |",
        "|------|------|------|------|------|------|",
    ]
    for r in sorted(results, key=lambda x: (x["subject"], x["year"], x["filename"])):
        size = f"{r['bytes']:,} B" if r["bytes"] else "-"
        status = r["status"]
        if r["error"]:
            status += f" ({r['error'][:40]})"
        lines.append(
            f"| {r['subject']} | {r['year']} | {r['filename']} | {status} | {size} | {r['url']} |"
        )

    failed = [r for r in results if r["status"] != "ok"]
    lines.extend(["", "## 说明", ""])
    lines.append("- PDF 文件可直接打开查看；HTML 为原始页面，同目录下有提取出的 `.txt` 纯文本。")
    lines.append("- 2025 年民法目前公开资源较少，本次使用广东成考网回忆版。")
    lines.append("- 爱真题打包下载需付费，故采用其免费网页版 + 环球网校公开 PDF。")
    if failed:
        lines.append(f"- **{len(failed)} 个文件下载失败**，见上表。")
    return "\n".join(lines) + "\n"


def main() -> None:
    results: list[dict] = []
    for (subject, year), items in sorted(SOURCES.items()):
        for filename, url, kind in items:
            print(f"Downloading {subject}/{year}/{filename} ...")
            results.append(download_one(subject, year, filename, url, kind))

    readme = build_readme(results)
    save_text(QUESTIONS / "README.md", readme)

    ok = sum(1 for r in results if r["status"] == "ok")
    print(f"\nDone: {ok}/{len(results)} files saved under {QUESTIONS}")


if __name__ == "__main__":
    main()
