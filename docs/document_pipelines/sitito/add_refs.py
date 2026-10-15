"""Вставка 14 проверенных источников в рукопись СИТИТО с автоматической перенумерацией.

    python tmp/sitito/add_refs.py

Что делает:
 1. вставляет новые ссылки в текст рядом с тематически близкими существующими;
 2. перенумеровывает ВСЕ ссылки в порядке первого упоминания (требование журнала);
 3. перестраивает список литературы в build.py в новом порядке.

Блоки вида [1,1,1,1] и [1,1,1] в разделе результатов — это данные, а не ссылки:
они распознаются по повторяющемуся номеру и не трогаются.
"""

from __future__ import annotations

import ast
import re
import shutil
from datetime import datetime
from pathlib import Path

from docx import Document

TMP = Path(r"C:\Users\Артём\Documents\Science\ai-db-optimizer\tmp\sitito")
MD = TMP / "manuscript.md"
BUILD = TMP / "build.py"
NIR = Path(r"C:\Users\Артём\Documents\Science\Научные материалы\05 Заявки и конкурсы\Наука 3.5 — ВоГУ 2026\Комплект к подаче — 15 октября 2026\01 НИР.docx")

# вставки: точная строка в тексте -> строка с токенами
INSERT = [
    ("[3, 4]", "[3, 4, @SONG, @TAN, @DHAR, @RESEQ]"),
    ("[5]", "[5, @DAIL]"),
    ("[6]", "[6, @DRSPIDER]"),
    ("[8]", "[8, @RAHAMAN]"),
    ("[10]", "[10, @HOTTSQL]"),
    ("[11]", "[11, @ZHOU]"),
    ("[10, 11]", "[10, 11, @DING]"),
    ("[12]", "[12, @SQLASER]"),
    ("[13]", "[13, @RIGGERPART]"),
    ("[20]", "[20, @RICCIOTTI]"),
    ("без выбора лучшей попытки.", "без выбора лучшей попытки [@FU]."),
]

NEW_REFS = {
    "SONG": "Song M., Zheng M. A Survey of Query Optimization in Large Language Models. 2024. arXiv:2412.17558. URL: https://arxiv.org/abs/2412.17558 (дата обращения: 16.10.2026).",
    "TAN": "Tan J., Zhao K., Li R., Yu J. X., Piao C., Cheng H., et al. Can Large Language Models Be Query Optimizer for Relational Databases? 2025. arXiv:2502.05562. URL: https://arxiv.org/abs/2502.05562 (дата обращения: 16.10.2026).",
    "DHAR": "Dharwada S., Devrani H., Haritsa J., Doraiswamy H. Query Rewriting via LLMs. 2025. arXiv:2502.12918. URL: https://arxiv.org/abs/2502.12918 (дата обращения: 16.10.2026).",
    "RESEQ": "Fathollahzadeh S., Mansour E., Boehm M. ReSequel: Robust LLM-assisted Query Rewriting and Optimization using Templatization and Sampling // Proceedings of the VLDB Endowment. 2026. Vol. 19, № 10. P. 2880–2893. doi:10.14778/3828612.3828639.",
    "DAIL": "Gao D., Wang H., Li Y., Sun X., Qian Y., Ding B., et al. Text-to-SQL Empowered by Large Language Models: A Benchmark Evaluation. 2023. arXiv:2308.15363. URL: https://arxiv.org/abs/2308.15363 (дата обращения: 16.10.2026).",
    "DRSPIDER": "Chang S., Wang J., Dong M., Pan L., Zhu H., Li A. H., et al. Dr.Spider: A Diagnostic Evaluation Benchmark towards Text-to-SQL Robustness. 2023. arXiv:2301.08881. URL: https://arxiv.org/abs/2301.08881 (дата обращения: 16.10.2026).",
    "RAHAMAN": "Rahaman A., Zheng A., Milani M., Chiang F., Pottinger R. Evaluating SQL Understanding in Large Language Models // Proceedings of EDBT. 2025. P. 909–921. doi:10.48786/EDBT.2025.74.",
    "HOTTSQL": "Chu S., Weitz K., Cheung A., Suciu D. HoTTSQL: Proving Query Rewrites with Univalent SQL Semantics. 2016. arXiv:1607.04822. URL: https://arxiv.org/abs/1607.04822 (дата обращения: 16.10.2026).",
    "ZHOU": "Zhou Q., Arulraj J., Navathe S., Harris W., Wu J. A Symbolic Approach to Proving Query Equivalence Under Bag Semantics. 2020. arXiv:2004.00481. URL: https://arxiv.org/abs/2004.00481 (дата обращения: 16.10.2026).",
    "RICCIOTTI": "Ricciotti W., Cheney J. A Formalization of SQL with Nulls. 2020. arXiv:2003.11331. URL: https://arxiv.org/abs/2003.11331 (дата обращения: 16.10.2026).",
    "SQLASER": "Wei J., Chen P., Lu K., Dai J., Sun X. SQLaser: Detecting DBMS Logic Bugs with Clause-Guided Fuzzing. 2024. arXiv:2407.04294. URL: https://arxiv.org/abs/2407.04294 (дата обращения: 16.10.2026).",
    "FU": "Fu T., Martínez G., Conde J., Arriaga C., Reviriego P., Qi X., et al. Beyond Reproducibility: Token Probabilities Expose Large Language Model Nondeterminism // IEEE Transactions on Computers. 2026. arXiv:2601.06118. URL: https://arxiv.org/abs/2601.06118 (дата обращения: 16.10.2026).",
}

GROUP = re.compile(r"\[([^\[\]]+)\]")


def citation_parts(inner: str):
    """Ссылка это или данные?

    Ссылка состоит из чисел и токенов вида @SONG. Данные вида [1,1,1,1]
    содержат повторяющийся номер и ссылкой не считаются.
    """
    parts = [p.strip() for p in inner.split(",")]
    if not parts:
        return None
    if not all(p.isdigit() or re.fullmatch(r"@[A-Z]+", p) for p in parts):
        return None
    nums = [p for p in parts if p.isdigit()]
    if len(set(nums)) != len(nums):
        return None  # [1,1,1,1] — данные
    return parts


def nir_reference(fragment: str) -> str:
    d = Document(NIR)
    for p in d.paragraphs:
        t = p.text.strip()
        if fragment in t:
            return re.sub(r"^\s*\d{1,2}[\.\)]\s*", "", t)
    raise SystemExit(f"в НИР не найдена запись: {fragment}")


def main() -> None:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for f in (MD, BUILD):
        shutil.copy2(f, f.with_name(f"{f.stem}.backup-{stamp}{f.suffix}"))

    src = BUILD.read_text(encoding="utf-8")
    tree = ast.parse(src)
    refs_node = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "refs" for t in node.targets):
            refs_node = node
    if refs_node is None:
        raise SystemExit("в build.py не найден список refs")
    old_refs = ast.literal_eval(refs_node.value)
    print(f"в build.py сейчас источников: {len(old_refs)}")

    new_refs = dict(NEW_REFS)
    new_refs["DING"] = nir_reference("Proving Query Equivalence Using Linear Integer Arithmetic")
    new_refs["RIGGERPART"] = nir_reference("Finding Bugs in Database Systems via Query Partitioning")
    print(f"добавляем источников: {len(new_refs)}")

    text = MD.read_text(encoding="utf-8")
    for old, new in INSERT:
        cnt = text.count(old)
        if cnt != 1:
            raise SystemExit(f"якорь встречается {cnt} раз, ожидался один: {old!r}")
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
    print(f"всего ссылок после вставки: {len(order)}")

    def replace(m):
        parts = citation_parts(m.group(1))
        if not parts:
            return m.group(0)
        nums = sorted(numbers[p] for p in parts)
        return "[" + ", ".join(str(n) for n in nums) + "]"

    new_text = GROUP.sub(replace, text)

    final_refs = []
    for tok in order:
        if tok.isdigit():
            final_refs.append(old_refs[int(tok) - 1])
        else:
            final_refs.append(new_refs[tok.lstrip("@")])
    assert len(final_refs) == len(order)

    MD.write_text(new_text, encoding="utf-8", newline="\n")

    lines = src.splitlines(keepends=True)
    start = refs_node.lineno - 1
    end = refs_node.end_lineno
    block = "refs=[\n" + "".join(f" {t!r},\n" for t in final_refs) + "]\n"
    BUILD.write_text("".join(lines[:start]) + block + "".join(lines[end:]), encoding="utf-8", newline="\n")

    print(f"источников стало: {len(final_refs)}")
    print("резервные копии:", f"manuscript.backup-{stamp}.md", f"build.backup-{stamp}.py")
    print("\nперенумерация (первые 12):")
    for tok in order[:12]:
        print(f"   {numbers[tok]:>3}  {tok}")


if __name__ == "__main__":
    main()
