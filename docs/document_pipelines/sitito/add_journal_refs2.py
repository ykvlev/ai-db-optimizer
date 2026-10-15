"""Второй заход по п. 1.4.14: ещё три журнальные статьи и запас по доле.

    python add_journal_refs2.py
"""

from __future__ import annotations

import ast
import re
import shutil
from datetime import datetime
from pathlib import Path

TMP = Path(r"C:\Users\Артём\Documents\Science\ai-db-optimizer\tmp\sitito")
MD = TMP / "manuscript.md"
BUILD = TMP / "build.py"

NEW_REFS = {
    "NL2SQLREV": "Luo Y., Li G., Fan J., Chai C., Tang N. Natural Language to SQL: State of the Art "
                 "and Open Problems // Proceedings of the VLDB Endowment. 2025. Vol. 18, № 12. "
                 "P. 5466–5471. doi:10.14778/3750601.3750696.",
    "DAWN": "Li B., Luo Y., Chai C., Li G., Tang N. The Dawn of Natural Language to SQL: Are We Fully "
            "Ready? // Proceedings of the VLDB Endowment. 2024. Vol. 17, № 11. P. 3318–3331. "
            "doi:10.14778/3681954.3682003.",
    "CODEERR": "Wen H., Zhu Y., Liu C., Ren X., Du W., Yan M., et al. Analyzing and Fixing Code "
               "Generation Errors of Foundation Large Language Models // Empirical Software "
               "Engineering. 2026. Vol. 32, № 1. doi:10.1007/s10664-026-10958-5.",
}

INSERT = [
    ("[5, 6, 7, 8]", "[5, 6, 7, 8, @NL2SQLREV, @DAWN]"),
    ("[18, 19]", "[18, 19, @CODEERR]"),
]

# Исправление оплошности: после замены точки предложение начиналось со строчной буквы.
FIX = [
    ("комплекс [43]. точный использованный срез",
     "комплекс [43]. Точный использованный срез"),
]

GROUP = re.compile(r"\[([^\[\]]+)\]")


def citation_parts(inner: str):
    parts = [p.strip() for p in inner.split(",")]
    if not parts:
        return None
    if not all(p.isdigit() or re.fullmatch(r"@[A-Z0-9]+", p) for p in parts):
        return None
    nums = [p for p in parts if p.isdigit()]
    if len(set(nums)) != len(nums):
        return None
    return parts


def main() -> None:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for f in (MD, BUILD):
        shutil.copy2(f, f.with_name(f"{f.stem}.backup-journal2-{stamp}{f.suffix}"))

    src = BUILD.read_text(encoding="utf-8")
    tree = ast.parse(src)
    node = next(n for n in tree.body
                if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == "refs" for t in n.targets))
    refs = ast.literal_eval(node.value)

    text = MD.read_text(encoding="utf-8")
    for old, new in FIX:
        n = text.count(old)
        print(f"  исправление регистра: вхождений {n}")
        if n:
            text = text.replace(old, new)
    for old, new in INSERT:
        n = text.count(old)
        if n != 1:
            raise SystemExit(f"якорь встречается {n} раз: {old!r}")
        text = text.replace(old, new)

    order: list[str] = []
    for m in GROUP.finditer(text):
        parts = citation_parts(m.group(1))
        if not parts:
            continue
        for p in parts:
            if p not in order:
                order.append(p)
    numbers = {tok: i + 1 for i, tok in enumerate(order)}

    def replace(m):
        parts = citation_parts(m.group(1))
        if not parts:
            return m.group(0)
        return "[" + ", ".join(str(n) for n in sorted(numbers[p] for p in parts)) + "]"

    new_text = GROUP.sub(replace, text)
    final = [refs[int(t) - 1] if t.isdigit() else NEW_REFS[t.lstrip("@")] for t in order]

    MD.write_text(new_text, encoding="utf-8", newline="\n")
    lines = src.splitlines(keepends=True)
    block = "refs=[\n" + "".join(f" {t!r},\n" for t in final) + "]\n"
    BUILD.write_text("".join(lines[:node.lineno - 1]) + block + "".join(lines[node.end_lineno:]),
                     encoding="utf-8", newline="\n")
    print(f"источников стало: {len(final)}")


if __name__ == "__main__":
    main()
