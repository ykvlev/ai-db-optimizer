// Технический отчёт «Архитектура AI Database Optimizer», оформление по ГОСТ 2.105-2019 (как отчёт о НИР).
//   node build_techreport.js  -> Технический_отчет.docx   (затем ../nir/word_finalize.ps1 -Docx ...)
const fs = require('fs')
const path = require('path')
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, Header, PageNumber, ImageRun, Table, TableRow,
  TableCell, WidthType, BorderStyle, TableOfContents, LevelFormat, LevelSuffix, VerticalAlign, TableLayoutType,
} = require('../nir/node_modules/docx')

const HERE = __dirname
const FIG = path.join(HERE, '..', 'nir', 'figures')
const STATS = fs.existsSync(path.join(HERE, 'stats.json')) ? JSON.parse(fs.readFileSync(path.join(HERE, 'stats.json'), 'utf8')) : {}
const FONT = 'Times New Roman', MONO = 'Courier New', LINE = 360, INDENT = 709, PT24 = 480

let figN = 0, tabN = 0, lstN = 0
const run = (t, o = {}) => new TextRun({ text: t, font: o.mono ? MONO : FONT, size: o.size ?? 28 })
function p(text, o = {}) {
  return new Paragraph({
    children: Array.isArray(text) ? text : [run(text, o)], alignment: o.align ?? AlignmentType.JUSTIFIED,
    indent: o.noIndent ? undefined : { firstLine: INDENT },
    spacing: { line: o.line ?? LINE, before: o.before ?? 0, after: o.after ?? 0 }, keepNext: o.keepNext,
  })
}
const center = (t, o = {}) => p(t, { ...o, align: AlignmentType.CENTER, noIndent: true })
const structural = t => new Paragraph({ children: [run(t)], heading: HeadingLevel.HEADING_1, alignment: AlignmentType.CENTER,
  pageBreakBefore: true, keepNext: true, spacing: { line: LINE, after: PT24 } })
const h1 = t => new Paragraph({ children: [run(t)], heading: HeadingLevel.HEADING_1, indent: { firstLine: INDENT },
  pageBreakBefore: true, keepNext: true, keepLines: true, spacing: { line: LINE, after: PT24 } })
const h2 = t => new Paragraph({ children: [run(t)], heading: HeadingLevel.HEADING_2, indent: { firstLine: INDENT },
  keepNext: true, keepLines: true, spacing: { line: LINE, before: PT24, after: PT24 } })
const dash = t => new Paragraph({ children: [run(t)], numbering: { reference: 'dash', level: 0 },
  alignment: AlignmentType.JUSTIFIED, spacing: { line: LINE } })

function figure(file, caption, widthCm = 16) {
  const b = fs.readFileSync(path.join(FIG, file)), w = b.readUInt32BE(16), h = b.readUInt32BE(20), px = widthCm / 2.54 * 96
  return [
    new Paragraph({ children: [new ImageRun({ type: 'png', data: b, transformation: { width: px, height: px * h / w } })],
      alignment: AlignmentType.CENTER, keepNext: true, spacing: { before: 120, after: 120 } }),
    center(`Рисунок ${++figN} – ${caption}`, { after: 240 }),
  ]
}
const border = { style: BorderStyle.SINGLE, size: 4, color: '000000' }
function table(caption, headers, rows, widths, alignNum = []) {
  const cell = (t, w, align, keep) => new TableCell({
    width: { size: w, type: WidthType.DXA }, verticalAlign: VerticalAlign.CENTER,
    borders: { top: border, bottom: border, left: border, right: border }, margins: { top: 40, bottom: 40, left: 80, right: 80 },
    children: [new Paragraph({ children: [run(String(t), { size: 24 })], alignment: align, spacing: { line: 240 }, keepNext: keep })],
  })
  return [
    p(`Таблица ${++tabN} – ${caption}`, { noIndent: true, align: AlignmentType.LEFT, keepNext: true, before: 120 }),
    new Table({
      width: { size: widths.reduce((a, b) => a + b, 0), type: WidthType.DXA }, columnWidths: widths, layout: TableLayoutType.FIXED,
      rows: [headers, ...rows].map((r, ri) => new TableRow({ tableHeader: ri === 0, cantSplit: true, height: { value: 454, rule: 'atLeast' },
        children: r.map((t, i) => cell(t, widths[i], ri === 0 || alignNum.includes(i) ? AlignmentType.CENTER : AlignmentType.LEFT,
          rows.length <= 20 && ri < rows.length)) })),
    }),
    p('', { noIndent: true, line: 240 }),
  ]
}
function listing(caption, code) {
  return [
    p(`Листинг ${++lstN} – ${caption}`, { noIndent: true, align: AlignmentType.LEFT, keepNext: true, before: 120 }),
    ...code.split('\n').map((l, i, a) => new Paragraph({ children: [run(l || ' ', { mono: true, size: 22 })],
      keepNext: i < a.length - 1, spacing: { line: 240 } })),
    p('', { noIndent: true, line: 240 }),
  ]
}

// ------------------------------------------------------------------ титульный лист
const small = t => center(t, { size: 24, line: 276 })
const blank = n => Array(n).fill(0).map(() => p('', { noIndent: true }))
const title = [
  small('Министерство науки и высшего образования Российской Федерации'),
  small('Федеральное государственное бюджетное образовательное учреждение высшего образования'),
  small('«Новгородский государственный университет имени Ярослава Мудрого»'),
  small('Политехнический институт'),
  small('ПОЛИТЕХНИЧЕСКИЙ КОЛЛЕДЖ'),
  ...blank(4),
  center('ИНТЕЛЛЕКТУАЛЬНАЯ СИСТЕМА АНАЛИЗА И ОПТИМИЗАЦИИ SQL-ЗАПРОСОВ «AI DATABASE OPTIMIZER»'),
  p('', { noIndent: true }),
  center('Технический отчёт'),
  center('Архитектура программного комплекса'),
  p('', { noIndent: true }),
  center('Версия 1.0.0'),
  ...blank(4),
  p('Разработчик', { noIndent: true, align: AlignmentType.LEFT }),
  p('студент группы 5996 ____________ / А. С. Яковлев /', { noIndent: true, align: AlignmentType.LEFT }),
  p('«___»____________2026 г.', { noIndent: true, align: AlignmentType.LEFT }),
  ...blank(3),
  center('Великий Новгород 2026'),
]

const annot = [
  structural('АННОТАЦИЯ'),
  p(`Технический отчёт ${STATS.pages ?? 'N'} с., ${STATS.figures ?? 'N'} рис., ${STATS.tables ?? 'N'} табл., ${STATS.listings ?? 'N'} лист.`),
  p('В отчёте описана архитектура программного комплекса AI Database Optimizer версии 1.0.0: назначение, состав модулей, конвейер обработки SQL-запроса, алгоритмы детерминированного анализа, взаимодействия с языковыми моделями, проверки безопасности и эквивалентности, бенчмарка и оценки результата, структура хранилища данных, программный интерфейс, режим массовых экспериментов, развёртывание, конфигурирование и тестирование.'),
  p('Отчёт предназначен для разработчиков, сопровождающих и развивающих комплекс, и для исследователей, воспроизводящих эксперименты. Исходный код опубликован по адресу https://github.com/ykvlev/ai-db-optimizer.'),
]
const toc = [structural('СОДЕРЖАНИЕ'), new TableOfContents('СОДЕРЖАНИЕ', { hyperlink: true, headingStyleRange: '1-2' })]

// ------------------------------------------------------------------ 1
const s1 = [
  h1('1 Назначение и область применения'),
  p('AI Database Optimizer – программный комплекс для анализа и оптимизации SQL-запросов к реляционным СУБД MySQL 8 и PostgreSQL 14–16. Комплекс выявляет причины низкой производительности запроса, получает от большой языковой модели вариант переписанного запроса и принимает его только после формальной и эмпирической проверки на реальной базе данных.'),
  p('Основные функции:', { keepNext: true }),
  dash('анализ одного запроса или SQL-скрипта из нескольких операторов;'),
  dash('получение схемы базы данных из подключения или из DDL-описания;'),
  dash('получение и разбор плана выполнения (EXPLAIN, EXPLAIN ANALYZE);'),
  dash('детерминированный анализ набором правил и проверок плана;'),
  dash('оптимизация запроса языковой моделью или детерминированным переписывателем;'),
  dash('проверка безопасности, соответствия схеме и эквивалентности результата;'),
  dash('сравнительный бенчмарк исходного и оптимизированного запросов;'),
  dash('ручное сравнение двух произвольных запросов;'),
  dash('массовые эксперименты «набор запросов × модели» с автоматическим отчётом;'),
  dash('хранение истории запусков и экспорт результатов в JSON, CSV и XLSX.'),
  p('Область применения: сопровождение и разработка информационных систем, исследования эффективности языковых моделей в задачах работы с базами данных, обучение. Комплекс работает с базами данных только в режиме чтения и может применяться к рабочим базам данных.'),
  p('Основополагающее требование к комплексу – не выводить непроверенные показатели. Ускорение, изменение плана и оценка качества рекомендации показываются только по результатам измерений; при отсутствии подключения к базе данных комплекс выполняет только статический анализ и явно сообщает об этом пользователю.'),
]

// ------------------------------------------------------------------ 2
const s2 = [
  h1('2 Архитектура'),
  h2('2.1 Общая структура'),
  p('Комплекс построен по трёхуровневой архитектуре (рисунок 1): клиентское веб-приложение, серверное приложение с программным интерфейсом HTTP и уровень данных, включающий собственное хранилище результатов и исследуемые СУБД. Языковые модели подключаются как внешние сервисы или как локальный сервер Ollama.'),
  ...figure('d_arch.png', 'Архитектура программного комплекса', 16.5),
  h2('2.2 Технологический стек'),
  ...table('Технологический стек', ['Компонент', 'Технологии'], [
    ['Серверная часть', 'Python 3.11+, FastAPI, Pydantic, Uvicorn'],
    ['Разбор SQL', 'SQLGlot (диалекты MySQL и PostgreSQL)'],
    ['Хранилище результатов', 'SQLAlchemy, SQLite (по умолчанию) или PostgreSQL'],
    ['Драйверы СУБД', 'PyMySQL, psycopg 3'],
    ['Обращение к моделям', 'HTTPX; GigaChat, YandexGPT, OpenAI-совместимый API, Ollama'],
    ['Шифрование паролей', 'cryptography (Fernet)'],
    ['Клиентская часть', 'TypeScript, React, Vite, Tailwind CSS, Monaco Editor'],
    ['Испытательный стенд', 'Docker Compose: MySQL 8.4, PostgreSQL 16'],
    ['Тестирование', 'pytest'],
  ], [3100, 6255]),
  h2('2.3 Модули серверной части'),
  ...table('Модули серверной части', ['Модуль', 'Назначение'], [
    ['main.py', 'программный интерфейс HTTP, маршрутизация запросов'],
    ['services/pipeline.py', 'конвейер анализа и оптимизации, сохранение результатов'],
    ['services/sql_parser.py', 'разбор запроса, извлечение таблиц, псевдонимов, разбиение скрипта'],
    ['services/rules.py', 'детерминированные правила анализа'],
    ['services/explain.py', 'получение и нормализация планов выполнения, проверки плана'],
    ['services/rewriter.py', 'детерминированный переписыватель (базовая линия)'],
    ['services/safety.py', 'проверка безопасности запроса'],
    ['services/connectors.py', 'подключение к СУБД, получение схемы, выполнение запросов'],
    ['services/schema_ddl.py', 'построение схемы из DDL-описания'],
    ['services/benchmark.py', 'замеры времени и проверка эквивалентности'],
    ['services/scoring.py', 'оценка оптимизации и уверенности'],
    ['services/ai/providers.py', 'поставщики языковых моделей'],
    ['services/ai/optimizer.py', 'контекст модели, промпты, разбор и проверка ответа'],
    ['research/*', 'наборы запросов, эксперименты, статистика, отчёты'],
    ['db.py, models.py, config.py', 'модель хранилища, схемы данных API, настройки'],
  ], [3600, 5755]),
]

// ------------------------------------------------------------------ 3
const s3 = [
  h1('3 Конвейер обработки запроса'),
  p('Обработка запроса выполняется конвейером из восьми шагов (рисунок 2). Языковая модель участвует только на четвёртом шаге; решение о принятии её рекомендации принимается по результатам шагов 5–8. Последовательность взаимодействия компонентов приведена на рисунке 3.'),
  ...figure('fig_pipeline.png', 'Конвейер обработки запроса', 16),
  ...figure('d_sequence.png', 'Диаграмма последовательности процесса оптимизации', 16.5),
  p('Результат шага 8 – вердикт рекомендации:', { keepNext: true }),
  dash('accepted – результат совпал, запрос ускорился;'),
  dash('rejected – рекомендация отклонена с указанием типа ошибки;'),
  dash('no_change – изменений не предложено или ускорение в пределах погрешности;'),
  dash('unverified – проверка измерением невозможна (нет подключения к базе данных).'),
  p('Алгоритм принятия решения приведён на рисунке 4.'),
  ...figure('d_flow_decision.png', 'Алгоритм принятия решения по рекомендации', 8.3),
]

// ------------------------------------------------------------------ 4
const RULES = [
  ['SELECT_STAR', 'выборка всех колонок'], ['FUNCTION_ON_COLUMN', 'функция над колонкой в условии (YEAR, DATE, LOWER и др.)'],
  ['LEADING_WILDCARD', 'LIKE с шаблоном, начинающимся с %'], ['OR_DIFFERENT_COLUMNS', 'OR по разным колонкам'],
  ['NOT_IN_SUBQUERY', 'NOT IN с подзапросом'], ['CORRELATED_SUBQUERY', 'коррелированный подзапрос'],
  ['TYPE_MISMATCH, JOIN_TYPE_MISMATCH', 'несовпадение типов в сравнении и соединении'],
  ['NULL_COMPARISON', 'сравнение с NULL через = и <>'], ['ORDER_BY_RAND', 'случайная сортировка'],
  ['LARGE_OFFSET', 'глубокая пагинация'], ['CARTESIAN_JOIN, IMPLICIT_JOIN', 'соединение без условия, неявное соединение'],
  ['UNION_DISTINCT', 'UNION вместо UNION ALL'], ['HAVING_WITHOUT_AGGREGATE', 'условие без агрегата в HAVING'],
  ['UNBOUNDED_SELECT', 'большая таблица без фильтра и LIMIT'], ['MISSING_INDEX', 'фильтр или соединение без индекса'],
  ['ORDER_BY_NO_INDEX, ORDER_BY_EXPRESSION', 'сортировка без подходящего индекса или по выражению'],
  ['DISTINCT_WITH_WINDOW', 'DISTINCT вместе с оконной функцией'],
]
const PLAN = [
  ['FULL_TABLE_SCAN', 'полный просмотр таблицы'], ['FULL_INDEX_SCAN', 'полный просмотр индекса'],
  ['INDEX_NOT_USED', 'существующий индекс не использован'], ['FILESORT', 'дополнительная сортировка'],
  ['TEMPORARY_TABLE', 'временная таблица'], ['SORT_ON_DISK', 'сортировка с записью на диск (PostgreSQL)'],
  ['NESTED_LOOP_SCAN', 'вложенный цикл с полным просмотром'], ['ROW_ESTIMATE_MISMATCH', 'оценка числа строк расходится с фактической'],
]
const s4 = [
  h1('4 Детерминированный анализ'),
  h2('4.1 Синтаксический разбор'),
  p('Запрос разбирается библиотекой SQLGlot в абстрактное синтаксическое дерево для выбранного диалекта. Из дерева извлекаются тип оператора, используемые таблицы с учётом схем (schema.table), псевдонимы, общие табличные выражения (CTE) и признак коррелированности подзапросов. SQL-скрипт из нескольких операторов разбивается на отдельные операторы; комментарий перед оператором используется как его название.'),
  h2('4.2 Правила анализа'),
  p(`Правила (таблица 3) используют синтаксическое дерево, схему базы данных и план выполнения. Каждое правило – отдельная функция; ошибка в правиле не прерывает анализ, а регистрируется как проблема RULE_ERROR. Всего реализовано ${RULES.length} правил.`),
  ...table('Правила детерминированного анализа', ['Код', 'Выявляемая проблема'], RULES, [4300, 5055]),
  h2('4.3 Анализ плана выполнения'),
  p('План выполнения MySQL (EXPLAIN FORMAT=JSON) и PostgreSQL (EXPLAIN (FORMAT JSON), при наличии подключения – EXPLAIN ANALYZE с BUFFERS) приводится к общему дереву узлов с типом операции, таблицей, индексом, оценкой и фактическим числом строк, стоимостью и временем. По дереву выполняются проверки, приведённые в таблице 4.'),
  ...table('Проверки плана выполнения', ['Код', 'Выявляемая проблема'], PLAN, [4300, 5055]),
  h2('4.4 Детерминированный переписыватель'),
  p('Переписыватель выполняет заведомо эквивалентные преобразования: условия YEAR(col) = N, EXTRACT(YEAR FROM col) = N и DATE(col) = d заменяются диапазоном значений колонки. Он используется как базовая линия без искусственного интеллекта (участник baseline:rule-based) и проходит те же проверки, что и языковая модель.'),
]

// ------------------------------------------------------------------ 5
const s5 = [
  h1('5 Взаимодействие с языковыми моделями'),
  h2('5.1 Поставщики моделей'),
  p('Поставщики реализуют общий интерфейс LLMProvider с методом complete(model, system, user, temperature, json_mode). Модель выбирается идентификатором вида «поставщик:модель», например gigachat:GigaChat-2-Max. Поставщик регистрируется, если в настройках указан его ключ.'),
  ...table('Поддерживаемые поставщики моделей', ['Поставщик', 'Особенности подключения'], [
    ['GigaChat (Сбер)', 'OAuth по ключу авторизации, токен кэшируется; сертификат Минцифры (GIGACHAT_CA_BUNDLE)'],
    ['YandexGPT', 'API-ключ и идентификатор каталога Yandex Cloud'],
    ['OpenAI-совместимый API', 'любой сервис с API OpenAI: DeepSeek, OpenRouter, LM Studio, vLLM'],
    ['Ollama', 'локальный сервер; параметры num_ctx и num_predict ограничивают контекст и длину ответа'],
    ['baseline:rule-based', 'детерминированный переписыватель, без обращения к модели'],
  ], [3100, 6255]),
  h2('5.2 Контекст модели и промпты'),
  p('Модели передаётся структурированный контекст в формате JSON: текст запроса, СУБД и версия, схема используемых таблиц с колонками, индексами, внешними ключами и числом строк, сокращённое дерево плана выполнения, проблемы, найденные правилами, и ограничения (сохранение результата, только чтение, один оператор).'),
  p('Промпты хранятся в каталоге services/ai/prompts как версионируемые файлы JSON. Для каждого запуска сохраняются идентификатор версии и контрольная сумма SHA-256 файла промпта. Параметры файла промпта:', { keepNext: true }),
  dash('system и user – шаблоны системной и пользовательской частей;'),
  dash('exclude_context и exclude_issue_sources – исключаемые части контекста (для абляционных экспериментов);'),
  dash('response_format – формат ответа: json (полный структурированный ответ) или sql (только переписанный запрос).'),
  ...table('Версии промптов', ['Версия', 'Назначение'], [
    ['optimizer-v1', 'основной промпт, ответ в формате JSON'],
    ['optimizer-v1-noplan', 'то же без плана выполнения в контексте (абляция)'],
    ['optimizer-v2-rewrite', 'принудительное переписывание: ответ только SQL, пример «до/после»'],
  ], [3100, 6255]),
  p('Вариант промпта можно задать для отдельного участника эксперимента записью «модель@промпт», например ollama:qwen2.5-coder:7b@optimizer-v1-noplan.'),
  h2('5.3 Разбор и проверка ответа'),
  p('Из ответа модели извлекается объект JSON (в том числе из блока кода Markdown) и проверяется по схеме Pydantic. Ответ, не соответствующий формату, отклоняется с типом ошибки INVALID_RESPONSE. Затем оптимизированный запрос проверяется статически: безопасность, существование таблиц и колонок (с учётом псевдонимов, CTE и производных таблиц), существование индексов в подсказках USE INDEX и FORCE INDEX, колонок в рекомендуемых индексах.'),
]

// ------------------------------------------------------------------ 6
const s6 = [
  h1('6 Проверка безопасности и эквивалентности'),
  h2('6.1 Проверка безопасности'),
  p('К выполнению допускается только один оператор SELECT или WITH … SELECT. Отклоняются:', { keepNext: true }),
  dash('операторы изменения данных и схемы, управления транзакциями и правами;'),
  dash('SELECT … INTO, FOR UPDATE, FOR SHARE;'),
  dash('функции с побочными эффектами и доступом к файлам (SLEEP, BENCHMARK, pg_sleep, LOAD_FILE, pg_read_file и др.);'),
  dash('исполняемые комментарии MySQL и комментарии, содержащие ключевые слова SQL.'),
  p('Кроме того, каждый запрос выполняется в транзакции READ ONLY с ограничением времени выполнения, а при подключении программа проверяет права пользователя и предупреждает, если они шире права SELECT.'),
  h2('6.2 Проверка эквивалентности'),
  p('Исходный и оптимизированный запросы выполняются на одной базе данных. Для каждой строки результата вычисляется хеш SHA-256 канонического представления значений (числа – в едином десятичном виде, даты – в формате ISO 8601, NULL – отдельным маркером). Контрольная сумма набора строк – сумма хешей по модулю 2^128: она не зависит от порядка строк и учитывает повторы. Дополнительно сравниваются число колонок и, если исходный запрос содержит ORDER BY, порядок строк. При расхождении пользователю показываются примеры строк, присутствующих только в одном из результатов. Алгоритм приведён на рисунке 5.'),
  ...figure('d_flow_equiv.png', 'Алгоритм проверки эквивалентности', 10),
  p('Проверка является эмпирической: совпадение подтверждается на имеющихся данных и не является формальным доказательством эквивалентности.'),
]

// ------------------------------------------------------------------ 7
const s7 = [
  h1('7 Бенчмарк и оценка результата'),
  h2('7.1 Бенчмарк'),
  p('Время выполнения измеряется после прогревочных запусков (по умолчанию 2) по измеряемым запускам (по умолчанию 5); запуски исходного и оптимизированного запросов чередуются. Метрика – медиана времени на клиенте с получением всего результата. Сохраняются все замеры, среднее, минимум, максимум, стандартное отклонение, число возвращённых строк, для MySQL – число прочитанных строк по счётчикам Handler_read, для PostgreSQL – фактические строки и обращения к буферам из EXPLAIN ANALYZE. Ускорение – отношение медиан; рекомендация считается улучшением при ускорении не менее 1,05 и ухудшением – менее 0,95.'),
  h2('7.2 Оценка оптимизации и уверенности'),
  p('Оценка оптимизации (Optimization Score, от 0 до 100) и оценка уверенности (AI Confidence Score, от 0 до 1) вычисляются как взвешенные суммы компонентов (таблица 7). Компоненты, для которых нет данных, исключаются, а веса оставшихся нормируются. Веса задаются в файле config/scoring.json. Самооценка модели в оценку уверенности не входит: уверенность определяется только измерениями.'),
  ...table('Компоненты оценок', ['Оценка', 'Компонент', 'Вес'], [
    ['Optimization Score', 'ускорение (speed)', '0,40'], ['', 'стоимость плана (query_cost)', '0,20'],
    ['', 'прочитанные строки (rows_examined)', '0,15'], ['', 'использование индексов (index_usage)', '0,10'],
    ['', 'стабильность замеров (stability)', '0,10'], ['', 'сложность запроса (complexity)', '0,05'],
    ['AI Confidence Score', 'эквивалентность результата (equivalence)', '0,35'], ['', 'подтверждённое ускорение (real_speedup)', '0,25'],
    ['', 'согласие правил и модели (rule_ai_agreement)', '0,15'], ['', 'подтверждение планом (plan_confirmed)', '0,15'],
    ['', 'стабильность бенчмарка (benchmark_stability)', '0,10'],
  ], [2600, 5555, 1200], [2]),
]

// ------------------------------------------------------------------ 8
const API = [
  ['GET /api/health, /api/models, /api/examples', 'состояние, доступные модели и промпты, примеры запросов'],
  ['POST /api/query/analyze', 'анализ запроса без модели'],
  ['POST /api/query/analyze-script', 'анализ SQL-скрипта из нескольких операторов'],
  ['POST /api/query/optimize', 'полный конвейер оптимизации'],
  ['POST /api/query/compare', 'сравнение двух запросов'],
  ['POST /api/explain, /api/benchmark', 'план выполнения и бенчмарк отдельного запроса'],
  ['POST /api/database/connect', 'проверка и сохранение подключения'],
  ['GET, DELETE /api/database/connections', 'список и удаление подключений'],
  ['GET /api/database/{id}/schema', 'схема базы данных'],
  ['GET /api/runs, /api/runs/{id}', 'история запусков и полный результат запуска'],
  ['GET /api/stats', 'сводная статистика'],
  ['GET /api/export/runs', 'экспорт истории в JSON, CSV, XLSX'],
  ['GET, POST, DELETE /api/datasets', 'наборы запросов'],
  ['GET, POST, DELETE /api/experiments', 'эксперименты'],
  ['POST /api/experiments/{id}/cancel, /resume', 'остановка и продолжение эксперимента'],
  ['GET /api/experiments/{id}/report, /report.md', 'отчёт в HTML и Markdown'],
  ['GET /api/experiments/{id}/export', 'экспорт результатов эксперимента'],
]
const s8 = [
  h1('8 Хранилище данных и программный интерфейс'),
  h2('8.1 Хранилище результатов'),
  p('Результаты хранятся в собственной базе данных комплекса (по умолчанию SQLite, файл data/optimizer.db). Структура приведена на рисунке 6. Таблица analysis_runs хранит каждый запуск с версиями программы, СУБД, модели и промпта, вердиктом и полным ответом конвейера для воспроизводимости; связанные таблицы – версии запроса, планы, замеры, ответы модели с текстом промпта, рекомендованные индексы. Таблицы datasets, dataset_queries, experiments и experiment_results относятся к режиму массовых экспериментов. Пароли подключений хранятся зашифрованными (Fernet); ключ задаётся в настройках или создаётся при первом запуске.'),
  ...figure('d_er.png', 'Структура базы данных результатов', 17),
  h2('8.2 Программный интерфейс'),
  p('Серверная часть предоставляет программный интерфейс HTTP с обменом в формате JSON (таблица 8). Описание в формате OpenAPI формируется автоматически и доступно по адресу /docs.'),
  ...table('Программный интерфейс', ['Метод и адрес', 'Назначение'], API, [4700, 4655]),
  p('Пример запроса на оптимизацию приведён в листинге 1.'),
  ...listing('Запрос POST /api/query/optimize', `{
  "sql": "SELECT id, total FROM orders WHERE YEAR(created_at) = 2024",
  "dbms": "mysql",
  "connection_id": 2,
  "model": "gigachat:GigaChat-2-Max",
  "verify": true
}`),
]

// ------------------------------------------------------------------ 9
const s9 = [
  h1('9 Режим массовых экспериментов'),
  p('Режим Research Mode выполняет эксперимент «набор запросов × набор участников» в фоновом потоке. Для каждой пары выполняется полный конвейер; участники перебираются во внутреннем цикле, чтобы кандидаты для одного запроса измерялись близко по времени. Прерванный эксперимент продолжается без повторения выполненных пар.'),
  p('Каждая пара относится к исходу: улучшено, без изменений, ухудшено, некорректно или сбой вызова модели (ошибка инфраструктуры не считается ошибкой модели). Для каждого участника вычисляются число исходов, доля корректных и эквивалентных кандидатов, медиана ускорения с 95-процентным доверительным интервалом (перцентильный бутстреп, 2000 выборок, фиксированное начальное значение генератора), геометрическое среднее ускорения, число галлюцинаций, среднее время ответа и объём в токенах. Отчёт формируется в HTML и Markdown и содержит условия эксперимента, диаграммы, таблицы и автоматические выводы.'),
  p('Встроенные наборы запросов shop-bench-v1 (40 запросов, 16 категорий, включая контрольную группу) и shop-bench-mini-v1 (16 запросов) рассчитаны на испытательную базу данных shop-seed-v1. Результаты экспериментов выгружаются в открытый датасет скриптом scripts/export_dataset.py. Страница эксперимента в интерфейсе приведена на рисунке 7.'),
  ...figure('screen_experiment.png', 'Страница эксперимента', 16),
]

// ------------------------------------------------------------------ 10
const s10 = [
  h1('10 Развёртывание, конфигурирование и тестирование'),
  h2('10.1 Развёртывание'),
  p('Для работы необходимы Python 3.11 или новее и Node.js 20 или новее; для испытательного стенда – Docker. Порядок развёртывания приведён в листинге 2.'),
  ...listing('Развёртывание комплекса', `cd docker && docker compose up -d        # MySQL :3307, PostgreSQL :5434
cd backend
python -m venv .venv && .venv\\Scripts\\pip install -r requirements.txt
copy .env.example .env                     # ключи моделей
.venv\\Scripts\\uvicorn app.main:app --port 8000
cd frontend && npm install && npm run dev  # http://localhost:5173`),
  h2('10.2 Конфигурирование'),
  p('Настройки задаются переменными окружения или файлом backend/.env (таблица 9).'),
  ...table('Основные параметры конфигурации', ['Параметр', 'Назначение'], [
    ['DATABASE_URL, SECRET_KEY', 'хранилище результатов, ключ шифрования паролей'],
    ['DEFAULT_MODEL', 'модель по умолчанию'],
    ['GIGACHAT_AUTH_KEY, GIGACHAT_SCOPE, GIGACHAT_MODELS, GIGACHAT_CA_BUNDLE', 'подключение GigaChat'],
    ['YANDEX_API_KEY, YANDEX_FOLDER_ID, YANDEX_MODELS', 'подключение YandexGPT'],
    ['OPENAI_BASE_URL, OPENAI_API_KEY, OPENAI_MODELS', 'OpenAI-совместимый API'],
    ['OLLAMA_BASE_URL, OLLAMA_MODELS, OLLAMA_NUM_CTX, OLLAMA_NUM_PREDICT', 'локальные модели'],
    ['LLM_TEMPERATURE, LLM_TIMEOUT_S', 'температура (по умолчанию 0,1) и время ожидания ответа модели'],
    ['QUERY_TIMEOUT_MS, BENCHMARK_WARMUP, BENCHMARK_RUNS', 'ограничение времени запроса, параметры бенчмарка'],
  ], [4700, 4655]),
  h2('10.3 Тестирование'),
  p('Автоматические тесты (pytest, 49 тестов с учётом параметризации) охватывают разбор запросов и скриптов, правила анализа, проверку безопасности, переписыватель, разбор планов, проверку ответа модели, статистику и отчёты. Интеграционные тесты выполняют полный конвейер и эксперимент на испытательных СУБД в Docker и пропускаются, если СУБД недоступны. Для тестов конвейера используются подменные поставщики моделей с заранее известными ответами.'),
  h2('10.4 Воспроизводимость'),
  p('Для каждого запуска и эксперимента сохраняются версии программы, СУБД, набора запросов и испытательных данных, версия и контрольная сумма промпта, параметры модели и бенчмарка, время начала и окончания. Испытательные данные генерируются детерминированно, бутстреп использует фиксированное начальное значение. Это позволяет повторить эксперимент на другом компьютере и сравнить результаты.'),
]

const doc = new Document({
  creator: 'А. С. Яковлев', title: 'Технический отчёт: архитектура AI Database Optimizer',
  styles: {
    default: { document: { run: { font: FONT, size: 28, color: '000000' }, paragraph: { spacing: { line: LINE } } } },
    paragraphStyles: [
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { font: FONT, size: 28, bold: false, color: '000000' }, paragraph: { outlineLevel: 0 } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { font: FONT, size: 28, bold: false, color: '000000' }, paragraph: { outlineLevel: 1 } },
      { id: 'TOC1', name: 'toc 1', basedOn: 'Normal', run: { font: FONT, size: 28 } },
      { id: 'TOC2', name: 'toc 2', basedOn: 'Normal', run: { font: FONT, size: 28 }, paragraph: { indent: { left: 283 } } },
    ],
  },
  numbering: { config: [{ reference: 'dash', levels: [{ level: 0, format: LevelFormat.BULLET, text: '–', alignment: AlignmentType.LEFT,
    suffix: LevelSuffix.SPACE, style: { paragraph: { indent: { left: 0, firstLine: INDENT } } } }] }] },
  features: { updateFields: true },
  sections: [{
    properties: { titlePage: true, page: { size: { width: 11906, height: 16838 },
      margin: { top: 1134, bottom: 1134, left: 1701, right: 567, header: 567 } } },
    headers: {
      first: new Header({ children: [new Paragraph('')] }),
      default: new Header({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
        children: [new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 28 })] })] }),
    },
    children: [...title, ...annot, ...toc, ...s1, ...s2, ...s3, ...s4, ...s5, ...s6, ...s7, ...s8, ...s9, ...s10],
  }],
})
fs.writeFileSync(path.join(HERE, 'counts.json'), JSON.stringify({ figures: figN, tables: tabN, listings: lstN }))
Packer.toBuffer(doc).then(b => {
  fs.writeFileSync(path.join(HERE, 'Технический_отчет.docx'), b)
  console.log('Технический_отчет.docx', { figures: figN, tables: tabN, listings: lstN })
})
