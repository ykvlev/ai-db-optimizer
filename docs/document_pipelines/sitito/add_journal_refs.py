"""Доведение списка литературы до требования п. 1.4.14.

    python add_journal_refs.py

Что делает:
 1. заменяет три записи, цитировавшиеся как препринты arXiv, их журнальными
    версиями (у них те же авторы и название, но есть издание, том, страницы и DOI);
 2. добавляет семь проверенных журнальных статей и ссылается на них в тексте
    рядом с тематически близкими работами;
 3. перенумеровывает все ссылки в порядке первого упоминания.

Все DOI проверены обращением к Crossref: возвращены название издания, том, номер,
страницы и год. Ничего не додумано.
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

# Журнальные версии уже цитируемых работ: индекс в списке (0-based) -> новая запись.
UPGRADE = {
    5: "Gao D., Wang H., Li Y., Sun X., Qian Y., Ding B., et al. Text-to-SQL Empowered by Large "
       "Language Models: A Benchmark Evaluation // Proceedings of the VLDB Endowment. 2024. "
       "Vol. 17, № 5. P. 1132–1145. doi:10.14778/3641204.3641221.",
    21: "Wei J., Chen P., Lu K., Dai J., Sun X. SQLaser: Detecting Database Management System (DBMS) "
        "Logic Bugs with Clause-Guided Fuzzing // Journal of Computer Security. 2025. Vol. 34, № 1. "
        "P. 3–28. doi:10.1177/0926227X251370258.",
    33: "Fu T., Martínez G., Conde J., Arriaga C., Reviriego P., Qi X., et al. Beyond Reproducibility: "
        "Token Probabilities Expose Large Language Model Nondeterminism // IEEE Transactions on "
        "Computers. 2026. P. 1–14. doi:10.1109/TC.2026.3732142.",
}

# Новые источники: все — журнальные статьи в изданиях, индексируемых Scopus/WoS.
NEW_REFS = {
    "KOSTOV": "Kostov M., Kaloyanova K. Feedback-Driven SQL Optimization with Validated Query "
              "Rewrites // Electronics. 2026. Vol. 15, № 13. P. 2931. doi:10.3390/electronics15132931.",
    "QUERYBREW": "Schmidt T., Reif M., Birler A., Neumann T. QueryBrew: System-Agnostic SQL-to-SQL "
                 "Query Optimization // Proceedings of the VLDB Endowment. 2026. Vol. 19, № 12. "
                 "P. 4494–4497. doi:10.14778/3827998.3828048.",
    "NEURO": "Yi J., Chen G., Zhou X. Decoupling SQL Query Hardness Parsing for Text-to-SQL // "
             "Neurocomputing. 2025. Vol. 621. P. 129293. doi:10.1016/j.neucom.2024.129293.",
    "IEEEACCESS": "Zhan Z., Haihong E., Song M. Leveraging Large Language Model for Enhanced "
                  "Text-to-SQL Parsing // IEEE Access. 2025. Vol. 13. P. 30497–30504. "
                  "doi:10.1109/ACCESS.2025.3540072.",
    "QED": "Wang S., Pan S., Cheung A. QED: A Powerful Query Equivalence Decider for SQL // "
           "Proceedings of the VLDB Endowment. 2024. Vol. 17, № 11. P. 3602–3614. "
           "doi:10.14778/3681954.3682024.",
    "FUZZSURVEY": "Gao X., Liu Z., Cui J., Li H., Zhang H., Wei K., et al. A Comprehensive Survey on "
                  "Database Management System Fuzzing: Techniques, Taxonomy and Evaluation // "
                  "ACM Computing Surveys. 2026. Vol. 58, № 10. P. 1–36. doi:10.1145/3799227.",
    "CONSTOPT": "Zhang C., Rigger M. Constant Optimization Driven Database System Testing // "
                "Proceedings of the ACM on Management of Data. 2025. Vol. 3, № 1. P. 1–24. "
                "doi:10.1145/3709674.",
}

# Куда вставлять: точная строка в тексте -> строка с токенами.
INSERT = [
    ("[3, 4, 9, 10, 11, 12]", "[3, 4, 9, 10, 11, 12, @KOSTOV, @QUERYBREW]"),
    ("[5, 6]", "[5, 6, @NEURO, @IEEEACCESS]"),
    ("[17, 18]", "[17, 18, @QED]"),
    ("[21, 22]", "[21, 22, @FUZZSURVEY, @CONSTOPT]"),
]

GROUP = re.compile(r"\[([^\[\]]+)\]")


def citation_parts(inner: str):
    """Ссылка это или данные? Данные вида [1,1,1,1] содержат повторяющийся номер."""
    parts = [p.strip() for p in inner.split(",")]
    if not parts:
        return None
    if not all(p.isdigit() or re.fullmatch(r"@[A-Z]+", p) for p in parts):
        return None
    nums = [p for p in parts if p.isdigit()]
    if len(set(nums)) != len(nums):
        return None
    return parts


def main() -> None:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for f in (MD, BUILD):
        shutil.copy2(f, f.with_name(f"{f.stem}.backup-journal-{stamp}{f.suffix}"))

    src = BUILD.read_text(encoding="utf-8")
    tree = ast.parse(src)
    node = None
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == "refs" for t in n.targets):
            node = n
    if node is None:
        raise SystemExit("в build.py не найден список refs")
    refs = ast.literal_eval(node.value)

    for idx, text in UPGRADE.items():
        print(f"  замена записи {idx + 1}: {refs[idx][:55]}…")
        refs[idx] = text

    text = MD.read_text(encoding="utf-8")
    for old, new in INSERT:
        n = text.count(old)
        if n != 1:
            raise SystemExit(f"якорь встречается {n} раз, ожидался один: {old!r}")
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
    print(f"\nссылок после вставки: {len(order)}")

    def replace(m):
        parts = citation_parts(m.group(1))
        if not parts:
            return m.group(0)
        return "[" + ", ".join(str(n) for n in sorted(numbers[p] for p in parts)) + "]"

    new_text = GROUP.sub(replace, text)

    final = []
    for tok in order:
        if tok.isdigit():
            final.append(refs[int(tok) - 1])
        else:
            final.append(NEW_REFS[tok.lstrip("@")])
    assert len(final) == len(order)

    MD.write_text(new_text, encoding="utf-8", newline="\n")
    lines = src.splitlines(keepends=True)
    block = "refs=[\n" + "".join(f" {t!r},\n" for t in final) + "]\n"
    BUILD.write_text("".join(lines[:node.lineno - 1]) + block + "".join(lines[node.end_lineno:]),
                     encoding="utf-8", newline="\n")

    print(f"источников стало: {len(final)}")
    print("резервные копии:", f"manuscript.backup-journal-{stamp}.md", f"build.backup-journal-{stamp}.py")


if __name__ == "__main__":
    main()
