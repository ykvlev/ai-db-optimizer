// Статья и тезисы по результатам экспериментов (данные — docs/nir/data.json).
//   node build_articles.js  -> Статья_Молодой_ученый.docx, Тезисы.docx
const fs = require('fs')
const path = require('path')
const {
  Document, Packer, Paragraph, TextRun, AlignmentType, ImageRun, Table, TableRow, TableCell, WidthType, BorderStyle,
  VerticalAlign, TableLayoutType,
} = require('../nir/node_modules/docx')

const HERE = __dirname
const NIR = path.join(HERE, '..', 'nir')
const D = JSON.parse(fs.readFileSync(path.join(NIR, 'data.json'), 'utf8'))
const B = 'baseline:rule-based'
const S = id => D.exp[String(id)].summary
const L5 = S(5)[D.llm], B5 = S(5)[B], L6 = S(6)[D.llm], B6 = S(6)[B]
const NOPLAN = Object.keys(S(4)).find(k => k.includes('noplan'))
const A1 = S(4)[D.llm], A2 = S(4)[NOPLAN]

const FONT = 'Times New Roman'
const fx = (v, d = 2) => (v == null ? '—' : v.toFixed(d).replace('.', ','))
const x = v => (v == null ? '—' : `${fx(v)}x`)
const n0 = v => Math.round(v).toLocaleString('ru-RU').replace(/\s/g, ' ')

const run = (t, o = {}) => new TextRun({ text: t, font: FONT, size: o.size ?? 28, bold: o.bold, italics: o.italics })
function p(text, o = {}) {
  const runs = Array.isArray(text) ? text : [run(text, o)]
  return new Paragraph({
    children: runs, alignment: o.align ?? AlignmentType.JUSTIFIED,
    indent: o.noIndent ? undefined : { firstLine: 709 },
    spacing: { line: o.line ?? 360, before: o.before ?? 0, after: o.after ?? 0 }, keepNext: o.keepNext,
  })
}
const c = (t, o = {}) => p(t, { ...o, align: AlignmentType.CENTER, noIndent: true })
const r = (t, o = {}) => p(t, { ...o, align: AlignmentType.RIGHT, noIndent: true })
const lead = (label, text) => p([run(label, { bold: true }), run(text)])

function figure(file, caption, widthCm) {
  const b = fs.readFileSync(path.join(NIR, 'figures', file))
  const w = b.readUInt32BE(16), h = b.readUInt32BE(20), px = widthCm / 2.54 * 96
  return [
    new Paragraph({ children: [new ImageRun({ type: 'png', data: b, transformation: { width: px, height: px * h / w } })],
      alignment: AlignmentType.CENTER, keepNext: true, spacing: { before: 120 } }),
    c(caption, { after: 120 }),
  ]
}
const border = { style: BorderStyle.SINGLE, size: 4, color: '000000' }
function table(caption, headers, rows, widths) {
  const cell = (t, w, center, keep) => new TableCell({
    width: { size: w, type: WidthType.DXA }, verticalAlign: VerticalAlign.CENTER,
    borders: { top: border, bottom: border, left: border, right: border }, margins: { top: 30, bottom: 30, left: 80, right: 80 },
    children: [new Paragraph({ children: [run(String(t), { size: 24 })], keepNext: keep, spacing: { line: 240 },
      alignment: center ? AlignmentType.CENTER : AlignmentType.LEFT })],
  })
  return [
    p(caption, { noIndent: true, align: AlignmentType.LEFT, keepNext: true, before: 120 }),
    new Table({
      width: { size: widths.reduce((a, b) => a + b, 0), type: WidthType.DXA }, columnWidths: widths, layout: TableLayoutType.FIXED,
      rows: [headers, ...rows].map((row, ri) => new TableRow({ cantSplit: true, tableHeader: ri === 0,
        children: row.map((t, i) => cell(t, widths[i], ri === 0 || i > 0, ri < rows.length)) })),
    }),
    p('', { noIndent: true, line: 240 }),
  ]
}
const refs = list => [
  p('Литература:', { noIndent: true, before: 120, keepNext: true }),
  ...list.map((t, i) => p(`${i + 1}. ${t}`)),
]

const ACC = '(дата обращения: 26.09.2026)'
const REF = {
  selinger: 'Selinger P. G. Access path selection in a relational database management system / P. G. Selinger, M. M. Astrahan, D. D. Chamberlin [et al.] // Proceedings of the 1979 ACM SIGMOD International Conference on Management of Data. – New York : ACM, 1979. – P. 23–34.',
  winand: `Winand M. Use The Index, Luke! A guide to database performance for developers. – URL: https://use-the-index-luke.com ${ACC}.`,
  bird: 'Li J. Can LLM already serve as a database interface? A big bench for large-scale database grounded text-to-SQLs / J. Li, B. Hui, G. Qu [et al.] // Advances in Neural Information Processing Systems 36 (NeurIPS 2023). – 2023.',
  llmr2: `Li Z. LLM-R2: a large language model enhanced rule-based rewrite system for boosting query efficiency / Z. Li, H. Yuan, H. Wang [et al.] // arXiv. – 2024. – arXiv:2404.12872. – URL: https://arxiv.org/abs/2404.12872 ${ACC}.`,
  genrewrite: `Liu J. GenRewrite: query rewriting via large language models / J. Liu, B. Mozafari // arXiv. – 2024. – arXiv:2403.09060. – URL: https://arxiv.org/abs/2403.09060 ${ACC}.`,
  halluc: 'Ji Z. Survey of hallucination in natural language generation / Z. Ji, N. Lee, R. Frieske [et al.] // ACM Computing Surveys. – 2023. – Vol. 55, № 12. – Art. 248.',
  qwen: `Hui B. Qwen2.5-Coder technical report / B. Hui, J. Yang, Z. Cui [et al.] // arXiv. – 2024. – arXiv:2409.12186. – URL: https://arxiv.org/abs/2409.12186 ${ACC}.`,
  cosette: 'Chu S. Cosette: an automated prover for SQL / S. Chu, C. Wang, K. Weitz, A. Cheung // 8th Biennial Conference on Innovative Data Systems Research (CIDR 2017). – Chaminade, 2017.',
  repo: `Яковлев А. С. AI Database Optimizer : исходный код и данные экспериментов. – 2026. – URL: https://github.com/ykvlev/ai-db-optimizer ${ACC}.`,
}

const AUTHOR = 'Яковлев Артём Сергеевич, студент'
const ORG = 'Политехнический колледж Новгородского государственного университета имени Ярослава Мудрого (г. Великий Новгород)'
const SUP = 'Научный руководитель: ________________________'

// ================================================================== статья
const article = [
  p('УДК 004.65:004.8', { noIndent: true, align: AlignmentType.LEFT }),
  p('', { noIndent: true }),
  c('Применение больших языковых моделей для оптимизации SQL-запросов с автоматической проверкой рекомендаций', { bold: true }),
  p('', { noIndent: true }),
  r(AUTHOR, { italics: true }),
  r(ORG, { italics: true }),
  r(SUP, { italics: true }),
  p('', { noIndent: true }),
  p('В статье рассматривается применение больших языковых моделей для переписывания SQL-запросов с целью ускорения их выполнения. Предложен конвейер, в котором рекомендация модели принимается только после проверки безопасности, соответствия схеме базы данных, совпадения результата и замера времени выполнения. На наборе из 40 запросов к базам данных MySQL и PostgreSQL локальная модель Qwen2.5-Coder-7B сопоставлена с детерминированным переписывателем на основе правил. Модель улучшила 9 и 7 запросов против 8 и 9 у правил, ускорив в том числе запросы, для которых правила отсутствуют, а все её рекомендации, изменявшие результат, были отклонены автоматически.', { size: 24, line: 276 }),
  p([run('Ключевые слова: ', { size: 24, italics: true }), run('оптимизация SQL-запросов, большие языковые модели, план выполнения, эквивалентность запросов, бенчмарк, MySQL, PostgreSQL.', { size: 24 })], { line: 276 }),
  p('', { noIndent: true }),

  p('Производительность информационной системы во многом определяется скоростью выполнения её запросов к базе данных. Оптимизатор СУБД выбирает способ выполнения запроса на основе оценки стоимости альтернативных планов [1], однако не может исправить неудачную формулировку самого запроса. Классический пример – условие YEAR(created_at) = 2024: функция над колонкой не позволяет использовать индекс по этой колонке, и СУБД просматривает всю таблицу, хотя эквивалентное условие-диапазон читало бы только нужные строки [2].'),
  p('Большие языковые модели (LLM) хорошо справляются с генерацией SQL [3] и уже применяются для переписывания запросов [4; 5]. Их слабое место – галлюцинации, то есть уверенно изложенные, но неверные ответы [6]. Для оптимизации это означает риск получить запрос, который возвращает другие данные, обращается к несуществующей колонке или работает медленнее исходного. Цель работы – оценить, насколько полезна языковая модель при оптимизации запросов, если каждую её рекомендацию проверять измерением на реальной базе данных.'),

  p('Методика', { bold: true, keepNext: true, before: 120 }),
  p('Для исследования разработан программный комплекс AI Database Optimizer [7]. Запрос проходит восемь этапов: синтаксический разбор, получение схемы и плана выполнения, анализ 17 детерминированными правилами, обращение к модели, проверка безопасности, проверка соответствия схеме, проверка эквивалентности и сравнительный бенчмарк. Модели передаётся структурированный контекст в формате JSON: текст запроса, схема используемых таблиц с индексами и числом строк, сокращённый план выполнения и найденные правилами проблемы.'),
  p('Эквивалентность проверяется выполнением обоих запросов на одних данных: для каждой строки результата вычисляется хеш SHA-256, а контрольная сумма набора строк не зависит от их порядка, но учитывает повторы. Такая проверка не является формальным доказательством [8], но надёжно выявляет изменение результата. Время измеряется после двух прогревочных запусков по пяти замерам с чередованием исходного и нового запросов. Рекомендация считается улучшением при ускорении не менее 1,05 раза, ухудшением – менее 0,95 раза.'),
  p('Для сравнения использовалась базовая линия без искусственного интеллекта – переписыватель, который заменяет функции над датами диапазонами. Он проходит те же проверки, что и модель. В качестве модели выбрана Qwen2.5-Coder-7B [9], запускавшаяся локально на процессоре без передачи данных во внешние сервисы.'),
  p(`Испытательная база данных моделирует интернет-магазин: 100 000 клиентов, 500 000 заказов и 1 500 000 позиций заказов, данные генерируются детерминированно. Набор из 40 запросов охватывает 15 типичных ошибок формулировки (функции над колонками, коррелированные подзапросы, NOT IN, DISTINCT с соединением, OR по разным колонкам, глубокая пагинация и др.) и контрольную группу уже оптимальных запросов.`),

  p('Результаты', { bold: true, keepNext: true, before: 120 }),
  p('Результаты сравнения на СУБД MySQL 8.4 и PostgreSQL 16 приведены в таблице 1 и на рисунке 1.'),
  ...table('Таблица 1. Результаты на наборе из 40 запросов', ['Показатель', 'Модель, MySQL', 'Правила, MySQL', 'Модель, PostgreSQL', 'Правила, PostgreSQL'], [
    ['Улучшено', L5.outcomes.improved, B5.outcomes.improved, L6.outcomes.improved, B6.outcomes.improved],
    ['Без изменений', L5.outcomes.unchanged, B5.outcomes.unchanged, L6.outcomes.unchanged, B6.outcomes.unchanged],
    ['Ухудшено', L5.outcomes.worse, B5.outcomes.worse, L6.outcomes.worse, B6.outcomes.worse],
    ['Отклонено (ошибка)', L5.outcomes.invalid, B5.outcomes.invalid, L6.outcomes.invalid, B6.outcomes.invalid],
    ['Геометрическое среднее ускорения', x(L5.geomean_speedup), x(B5.geomean_speedup), x(L6.geomean_speedup), x(B6.geomean_speedup)],
  ], [2650, 1500, 1500, 1500, 1500]),
  ...figure('fig_full.png', 'Рис. 1. Исходы рекомендаций модели и правил на MySQL и PostgreSQL', 15),
  p(`По числу улучшенных запросов модель и правила оказались сопоставимы, но улучшали разные запросы. Наибольший эффект – ускорение до ${x(L5.max_speedup)} у модели и до ${x(B5.max_speedup)} у правил – получен на запросах с функциями над датами, которые исправляют оба участника. Только модель ускорила запросы с DISTINCT при соединении и с условием OR по разным колонкам: например, условие по двум колонкам она заменила объединением двух запросов через UNION, каждый из которых использует свой индекс (ускорение около 1,4 раза). Правила, в свою очередь, стабильнее исправляли условия с функцией YEAR. Запросы контрольной группы не изменил ни один участник.`),
  p(`Модель допустила ошибки нескольких типов, и все они были обнаружены автоматически. В одном случае модель удалила из запроса ключевое слово DISTINCT, и результат вырос с ${n0(D.distinct.eq.rows_original)} до ${n0(D.distinct.eq.rows_optimized)} строк за счёт повторов; в другом – заменила коррелированный подзапрос соединением, потеряв условие отбора клиентов. Оба варианта сопровождались уверенным пояснением и были отклонены проверкой эквивалентности. Встречалась и «имитация оптимизации»: модель переставила условия в WHERE, не устранив функцию над колонкой. Наконец, формально корректное преобразование условия с датой в аналитическом запросе с тремя соединениями замедлило его на PostgreSQL примерно вдвое – и у модели, и у правил, поскольку оптимизатор выбрал для нового условия менее удачный порядок соединения.`),
  p(`Дополнительно проверено, нужен ли модели план выполнения. Без плана в контексте модель улучшила столько же запросов из 16 (${A2.outcomes.improved} против ${A1.outcomes.improved}), работая на ${fx((1 - A2.avg_latency_ms / A1.avg_latency_ms) * 100, 0)} % быстрее, но единственное ухудшение в этом опыте допустил именно вариант без плана. Среднее время ответа модели на процессоре составило около ${fx(L5.avg_latency_ms / 60000, 0)} минут на запрос.`),

  p('Выводы', { bold: true, keepNext: true, before: 120 }),
  p('Даже небольшая локальная языковая модель находит преобразования, которых нет в наборе правил, и по числу улучшений сопоставима с ним. Однако рекомендации модели нельзя применять без проверки: часть из них меняет результат запроса, а часть, будучи корректной, замедляет его. Кроме того, эффект одного и того же преобразования зависит от СУБД и плана выполнения. Поэтому решение о принятии рекомендации должно приниматься по результатам измерений, а наиболее перспективным представляется совместное использование правил и модели с общей системой проверки. Исходный код комплекса и данные экспериментов опубликованы в открытом доступе [7].'),
  ...refs([REF.selinger, REF.winand, REF.bird, REF.llmr2, REF.genrewrite, REF.halluc, REF.repo, REF.cosette, REF.qwen]),
  p('', { noIndent: true }),
  c('Large language models for SQL query optimization with automatic verification of recommendations', { bold: true }),
  c('Yakovlev Artyom Sergeyevich, student', { italics: true }),
  c('Polytechnic College of Yaroslav-the-Wise Novgorod State University (Veliky Novgorod, Russia)', { italics: true }),
  p('The paper studies large language models for rewriting SQL queries to speed them up. A pipeline is proposed in which a model recommendation is accepted only after safety, schema, result-equivalence and benchmark checks. On 40 queries for MySQL and PostgreSQL, the local model Qwen2.5-Coder-7B is compared with a rule-based rewriter. The model improved 9 and 7 queries versus 8 and 9 for the rules, including queries no rule covers, while all of its result-changing recommendations were rejected automatically.', { size: 24, line: 276 }),
  p([run('Keywords: ', { size: 24, italics: true }), run('SQL query optimization, large language models, execution plan, query equivalence, benchmark, MySQL, PostgreSQL.', { size: 24 })], { line: 276 }),
]

// ================================================================== тезисы
const theses = [
  p('УДК 004.65:004.8', { noIndent: true, align: AlignmentType.LEFT }),
  p('', { noIndent: true }),
  c('АВТОМАТИЗИРОВАННАЯ СИСТЕМА АНАЛИЗА SQL-ЗАПРОСОВ С ПРИМЕНЕНИЕМ ИСКУССТВЕННОГО ИНТЕЛЛЕКТА', { bold: true }),
  p('', { noIndent: true }),
  c('А. С. Яковлев', { italics: true }),
  c(ORG, { italics: true }),
  c(SUP, { italics: true }),
  p('', { noIndent: true }),
  p('Медленные запросы к базе данных – одна из самых частых причин низкой производительности информационных систем. Нередко причина не в нехватке ресурсов, а в формулировке запроса: функция над индексированной колонкой, коррелированный подзапрос или условие OR лишают СУБД возможности использовать индекс [1]. Языковые модели умеют переписывать такие запросы [2], но склонны к галлюцинациям [3], поэтому их рекомендации опасно применять без проверки.'),
  p('Разработанная система AI Database Optimizer [4] использует языковую модель как один из этапов анализа. Запрос разбирается в синтаксическое дерево, для него получаются схема базы данных и план выполнения, 17 правил выявляют типовые проблемы, после чего модель получает структурированный контекст и предлагает новый вариант запроса. Вариант принимается только после четырёх проверок: безопасности (разрешён лишь один оператор SELECT), соответствия схеме (нет несуществующих таблиц, колонок и индексов), совпадения результата (контрольная сумма набора строк) и бенчмарка (медиана пяти замеров с чередованием запросов). Система поддерживает MySQL и PostgreSQL, модели GigaChat, YandexGPT и локальные модели через Ollama, а также режим массовых экспериментов с автоматическим отчётом.'),
  p(`Эксперимент проведён на наборе из 40 запросов к базе данных интернет-магазина (2,1 млн строк) с контрольной группой уже оптимальных запросов. Локальная модель Qwen2.5-Coder-7B улучшила ${L5.outcomes.improved} запросов на MySQL и ${L6.outcomes.improved} на PostgreSQL, детерминированные правила – ${B5.outcomes.improved} и ${B6.outcomes.improved}. Максимальное ускорение достигло ${x(L5.max_speedup)} у модели и ${x(B5.max_speedup)} у правил. Модель единственная ускорила запросы с DISTINCT и OR, для которых правил нет, но и единственная предлагала варианты, меняющие результат: например, удаление DISTINCT привело к повтору строк. Все такие варианты отклонены автоматически. Кроме того, одно и то же корректное преобразование ускорило запрос на одной СУБД и замедлило на другой.`),
  p('Результаты показывают, что языковая модель полезна как источник кандидатов на оптимизацию, но решение о применении должно приниматься по измерениям на реальной базе данных. Исходный код системы и данные опубликованы в открытом доступе [4].'),
  ...refs([REF.winand, REF.genrewrite, REF.halluc, REF.repo]),
]

function save(children, file) {
  const doc = new Document({
    creator: 'А. С. Яковлев',
    styles: { default: { document: { run: { font: FONT, size: 28 }, paragraph: { spacing: { line: 360 } } } } },
    sections: [{ properties: { page: { size: { width: 11906, height: 16838 },
      margin: { top: 1134, bottom: 1134, left: 1134, right: 1134 } } }, children }],
  })
  return Packer.toBuffer(doc).then(b => { fs.writeFileSync(path.join(HERE, file), b); console.log(file) })
}
save(article, 'Статья_Молодой_ученый.docx').then(() => save(theses, 'Тезисы.docx'))
