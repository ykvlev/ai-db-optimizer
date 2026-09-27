// Раздаточный материал для эксперимента «ИИ против человека»: инструкция, схема базы, 10 заданий, место для ответа.
//   node build_study.js  -> Задания_для_участников.docx
const fs = require('fs')
const path = require('path')
const { Document, Packer, Paragraph, TextRun, AlignmentType, Table, TableRow, TableCell, WidthType, BorderStyle } = require('../nir/node_modules/docx')

const HERE = __dirname
const TASKS = JSON.parse(fs.readFileSync(path.join(HERE, 'tasks.json'), 'utf8'))
const SCHEMA = JSON.parse(fs.readFileSync(path.join(HERE, 'schema.json'), 'utf8'))
const F = 'Times New Roman', MONO = 'Courier New'
const run = (t, o = {}) => new TextRun({ text: t, font: o.mono ? MONO : F, size: o.size ?? 26, bold: o.bold })
const p = (t, o = {}) => new Paragraph({ children: Array.isArray(t) ? t : [run(t, o)], alignment: o.align ?? AlignmentType.JUSTIFIED,
  spacing: { line: o.line ?? 300, before: o.before ?? 0, after: o.after ?? 80 }, keepNext: o.keepNext, pageBreakBefore: o.pageBreak })
const code = t => t.split('\n').map((l, i, a) => new Paragraph({ children: [run(l || ' ', { mono: true, size: 20 })], spacing: { line: 240 }, keepNext: i < a.length - 1 }))
const border = { style: BorderStyle.SINGLE, size: 4, color: '000000' }
const box = lines => new Table({ width: { size: 9600, type: WidthType.DXA }, columnWidths: [9600],
  rows: [new TableRow({ height: { value: 300 * lines, rule: 'atLeast' }, children: [new TableCell({ width: { size: 9600, type: WidthType.DXA },
    borders: { top: border, bottom: border, left: border, right: border }, children: [new Paragraph('')] })] })] })

// SQL с переносами для читаемости
const pretty = s => s.replace(/\s+(FROM|WHERE|JOIN|LEFT JOIN|GROUP BY|ORDER BY|LIMIT|AND|OR)\s/g, '\n$1 ').replace(/\n(AND|OR) /g, '\n  $1 ')

const body = [
  p('Эксперимент «Оптимизация SQL-запросов: человек и искусственный интеллект»', { bold: true, align: AlignmentType.CENTER, size: 30, after: 200 }),
  p([run('Код участника: ', { bold: true }), run('________    '), run('Опыт работы с SQL (лет): ', { bold: true }), run('________')]),
  p('Цель – сравнить, как люди и языковые модели ускоряют SQL-запросы. Ваши ответы будут проверены тем же способом, что и ответы моделей: новый запрос выполняется на базе данных, сравнивается результат и время выполнения. Участие добровольное и анонимное: указывайте только код участника, выданный организатором.', { before: 120 }),
  p('Правила', { bold: true, before: 120 }),
  p('1. На все задания – 45 минут. Порядок выполнения любой.'),
  p('2. Перепишите запрос так, чтобы он выполнялся быстрее и возвращал в точности тот же результат (те же строки, колонки и порядок строк при ORDER BY).'),
  p('3. Если считаете, что запрос уже оптимален или его нельзя безопасно ускорить, напишите «без изменений» – это тоже правильный ответ.'),
  p('4. Создавать индексы и менять таблицы нельзя – только переписывать запрос.'),
  p('5. Можно пользоваться документацией MySQL; нельзя пользоваться чат-ботами и другими инструментами искусственного интеллекта.'),
  p('База данных (MySQL 8.4)', { bold: true, before: 160, keepNext: true }),
  ...SCHEMA.map(t => p([run(`${t.name} `, { bold: true, mono: true, size: 22 }), run(`(${(t.rows ?? 0).toLocaleString('ru-RU')} строк): `, { size: 22 }),
    run(t.columns.join(', '), { mono: true, size: 20 }), run('. Индексы: ', { size: 22 }), run(t.indexes.join('; '), { mono: true, size: 20 })], { align: AlignmentType.LEFT })),
  ...TASKS.flatMap(t => [
    p(`Задание ${t.n}. ${t.title}`, { bold: true, before: 240, keepNext: true, pageBreak: t.n === 1 }),
    ...code(pretty(t.sql)),
    p('Ваш вариант запроса (или «без изменений»):', { before: 100, keepNext: true, size: 22 }),
    box(6),
  ]),
  p('Спасибо за участие!', { bold: true, align: AlignmentType.CENTER, before: 300 }),
]

const doc = new Document({ sections: [{ properties: { page: { margin: { top: 1000, bottom: 1000, left: 1100, right: 900 } } }, children: body }] })
Packer.toBuffer(doc).then(b => { fs.writeFileSync(path.join(HERE, 'Задания_для_участников.docx'), b); console.log('Задания_для_участников.docx') })
