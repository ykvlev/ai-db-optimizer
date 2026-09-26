import { useState } from 'react'
import { CopyBlock, Step } from '../components/ui'

type OS = 'windows' | 'unix'

const REPO = 'https://github.com/ykvlev/ai-db-optimizer'

function Section({ n, title, children }: { n: string; title: string; children: React.ReactNode }) {
  return (
    <section className="grid gap-4 border-t border-line pt-6 md:grid-cols-[180px_1fr]">
      <div>
        <div className="text-[44px] font-bold leading-none tabular-nums text-accent">{n}</div>
        <div className="mt-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-text">{title}</div>
      </div>
      <div className="min-w-0 space-y-4">{children}</div>
    </section>
  )
}

const FAQ: [string, React.ReactNode][] = [
  ['Интерфейс пишет, что сервер недоступен',
    'Сервер (backend) не запущен или закрыто его окно. Запустите шаг 4 заново и не закрывайте окно, пока работаете. Если порт 8000 занят другой программой, укажите другой порт и адрес в frontend/vite.config.ts.'],
  ['Docker: «command not found» или «cannot connect to the Docker daemon»',
    'Docker Desktop не установлен или не запущен. Откройте Docker Desktop и дождитесь зелёного статуса «Engine running», затем повторите команду.'],
  ['Порт 3307 или 5434 уже занят',
    'На компьютере уже работает другая СУБД на этом порту. Измените левое число в ports в docker/docker-compose.yml (например "3308:3306") и укажите новый порт при подключении.'],
  ['GigaChat: CERTIFICATE_VERIFY_FAILED',
    'Сервисы Сбера используют сертификат Минцифры. Он уже лежит в backend/config — добавьте в backend/.env строку GIGACHAT_CA_BUNDLE=config/russian_trusted_root_ca.pem и перезапустите сервер.'],
  ['Локальная модель отвечает очень долго',
    'Модели нужна свободная оперативная память: около 5 ГБ для 7B. Закройте тяжёлые программы, подключите ноутбук к зарядке (от батареи процессор замедляется) и выберите модель меньшего размера.'],
  ['Как подключить свою базу данных безопасно',
    'Создайте отдельного пользователя только с правом SELECT (команды ниже). Программа и так выполняет запросы в режиме только чтения, но отдельный пользователь — лучшая защита.'],
]

export function Setup() {
  const [os, setOs] = useState<OS>('windows')
  const w = os === 'windows'
  const py = w ? 'python' : 'python3'
  const venvBin = w ? '.venv\\Scripts\\' : '.venv/bin/'

  return (
    <div className="mx-auto max-w-5xl space-y-8 pb-16">
      <header className="space-y-3">
        <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-accent">Установка</div>
        <h2 className="max-w-3xl text-[34px] font-bold leading-[1.05] tracking-tight">Как поставить программу себе на компьютер</h2>
        <p className="max-w-3xl text-[14px] leading-relaxed text-muted">
          Около 15 минут. Нужны Python, Node.js и Docker. Программа работает на вашем компьютере: данные и запросы
          никуда не отправляются, кроме выбранной вами модели ИИ.
        </p>
        <div className="flex gap-0 pt-1">
          {(['windows', 'unix'] as OS[]).map(o => (
            <button key={o} onClick={() => setOs(o)}
              className={`border px-4 py-1.5 text-[12px] font-semibold uppercase tracking-wider ${os === o ? 'border-text bg-text text-bg' : 'border-line text-muted hover:text-text'}`}>
              {o === 'windows' ? 'Windows' : 'Linux / macOS'}
            </button>
          ))}
        </div>
      </header>

      {w && (
        <section className="border border-accent p-5">
          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-accent">Быстрый способ</div>
          <p className="mt-2 text-[13.5px] leading-relaxed text-muted">
            Установите программы из шага 1, скачайте проект и выполните два скрипта в PowerShell из папки проекта.
            Первый всё установит, второй запустит базы данных, сервер, интерфейс и откроет браузер.
          </p>
          <div className="mt-3 space-y-2">
            <CopyBlock label="Один раз — установка">{`powershell -ExecutionPolicy Bypass -File scripts\\setup.ps1`}</CopyBlock>
            <CopyBlock label="Каждый раз — запуск">{`powershell -ExecutionPolicy Bypass -File scripts\\start.ps1`}</CopyBlock>
          </div>
        </section>
      )}

      <Section n="01" title="Что нужно">
        <ul className="space-y-2 text-[13.5px]">
          <li><b>Python 3.11 или новее</b> — <span className="text-muted">python.org/downloads. {w && 'При установке отметьте «Add python.exe to PATH».'}</span></li>
          <li><b>Node.js 20 или новее</b> — <span className="text-muted">nodejs.org, версия LTS.</span></li>
          <li><b>Docker Desktop</b> — <span className="text-muted">docker.com. Нужен для демонстрационных баз данных; для своей базы не обязателен.</span></li>
          <li><b>Git</b> — <span className="text-muted">git-scm.com, или скачайте проект архивом ZIP.</span></li>
          <li className="text-muted">Необязательно: <b className="text-text">Ollama</b> (ollama.com) — если хотите запускать модель ИИ локально, без интернета.</li>
        </ul>
      </Section>

      <Section n="02" title="Скачать проект">
        <CopyBlock>{`git clone ${REPO}.git\ncd ai-db-optimizer`}</CopyBlock>
        <p className="text-[13px] text-muted">Или на странице {REPO} нажмите Code → Download ZIP и распакуйте архив.</p>
      </Section>

      <Section n="03" title="Базы данных">
        <p className="text-[13.5px] text-muted">
          Запускает демонстрационную базу интернет-магазина в MySQL (порт 3307) и PostgreSQL (порт 5434).
          Первый запуск занимает несколько минут: скачиваются образы и генерируются данные — 2 млн строк.
        </p>
        <CopyBlock>{`docker compose -f docker/docker-compose.yml up -d`}</CopyBlock>
      </Section>

      <Section n="04" title="Сервер">
        <p className="text-[13.5px] text-muted">В папке backend создаётся изолированное окружение Python и устанавливаются библиотеки. Последняя команда запускает сервер — не закрывайте это окно.</p>
        <CopyBlock>{`cd backend
${py} -m venv .venv
${venvBin}pip install -r requirements.txt
${w ? 'copy' : 'cp'} .env.example .env
${venvBin}python -m uvicorn app.main:app --port 8000`}</CopyBlock>
        <p className="text-[13px] text-muted">Проверка: откройте http://localhost:8000/docs — должна появиться документация API.</p>
      </Section>

      <Section n="05" title="Модель ИИ">
        <p className="text-[13.5px] text-muted">Без модели работают анализ, поиск проблем и оптимизация по правилам. Для ИИ-оптимизации выберите вариант и допишите строки в файл <span className="mono text-text">backend/.env</span>, затем перезапустите сервер.</p>
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="space-y-2 border border-line p-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em]">GigaChat · облако, бесплатно</div>
            <Step n={1} title="Получите ключ">developers.sber.ru → GigaChat API → создайте проект для физического лица → скопируйте «Authorization key».</Step>
            <Step n={2} title="Добавьте в backend/.env">
              <CopyBlock label="backend/.env">{`GIGACHAT_AUTH_KEY=ваш_ключ
GIGACHAT_CA_BUNDLE=config/russian_trusted_root_ca.pem
DEFAULT_MODEL=gigachat:GigaChat-2-Pro`}</CopyBlock>
            </Step>
          </div>
          <div className="space-y-2 border border-line p-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em]">Ollama · локально, без интернета</div>
            <Step n={1} title="Скачайте модель">
              <CopyBlock label="Терминал">{`ollama pull qwen2.5-coder:7b`}</CopyBlock>
            </Step>
            <Step n={2} title="Добавьте в backend/.env">
              <CopyBlock label="backend/.env">{`OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODELS=qwen2.5-coder:7b
OLLAMA_NUM_CTX=4096
LLM_TIMEOUT_S=900`}</CopyBlock>
            </Step>
            <p className="text-[12px] text-muted">Нужно около 5 ГБ свободной памяти; ответ на процессоре — 1–3 минуты.</p>
          </div>
        </div>
        <p className="text-[12.5px] text-muted">Также поддерживаются YandexGPT и любые сервисы с API, совместимым с OpenAI (DeepSeek, OpenRouter, LM Studio) — все параметры описаны в backend/.env.example.</p>
      </Section>

      <Section n="06" title="Интерфейс">
        <p className="text-[13.5px] text-muted">В новом окне терминала, из папки проекта:</p>
        <CopyBlock>{`cd frontend
npm install
npm run dev`}</CopyBlock>
        <p className="text-[13.5px]">Откройте <b>http://localhost:5173</b> — на странице «Начало» чек-лист покажет, всё ли готово.</p>
      </Section>

      <Section n="07" title="Частые проблемы">
        <div className="divide-y divide-line border-y border-line">
          {FAQ.map(([q, a]) => (
            <details key={q} className="group py-3">
              <summary className="cursor-pointer list-none text-[13.5px] font-semibold">
                <span className="mr-2 inline-block w-3 text-accent group-open:rotate-45">+</span>{q}
              </summary>
              <div className="mt-2 pl-5 text-[13px] leading-relaxed text-muted">{a}</div>
            </details>
          ))}
        </div>
        <div className="grid gap-3 lg:grid-cols-2">
          <CopyBlock label="MySQL: пользователь только для чтения">{`CREATE USER 'optimizer_ro'@'%' IDENTIFIED BY 'пароль';
GRANT SELECT, SHOW VIEW ON моя_база.* TO 'optimizer_ro'@'%';`}</CopyBlock>
          <CopyBlock label="PostgreSQL: пользователь только для чтения">{`CREATE ROLE optimizer_ro LOGIN PASSWORD 'пароль';
GRANT CONNECT ON DATABASE моя_база TO optimizer_ro;
GRANT USAGE ON SCHEMA public TO optimizer_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO optimizer_ro;`}</CopyBlock>
        </div>
      </Section>
    </div>
  )
}
