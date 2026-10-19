# ContextPilot

**ContextPilot** помогает разобраться в архитектуре программного проекта: анализирует исходный код, строит интерактивный граф модулей и зависимостей, отслеживает изменения файлов и формирует краткий контекст проекта для передачи ИИ-ассистенту.

README на русском и английском языках.

## Возможности

- Сканирование локальных проектов и визуализация файлов и найденных связей между ними.
- Поиск модулей, просмотр их свойств и навигация по графу.
- Повторный анализ проекта и мониторинг файловых изменений в реальном времени.
- Просмотр состояния Git и последних изменений.
- Добавление архитектурных правил и отображение выявленных нарушений.
- Генерация контекста для ИИ: сводка архитектуры, подграф выбранного модуля или недавние изменения и нарушения. Результат можно скопировать в Cursor, Claude, ChatGPT и другие инструменты.

## Требования

- Python 3.10+ (backend разработан на Flask).
- Node.js и npm (frontend работает на Next.js).
- Git — необязательно; нужен для отображения состояния Git.

## Запуск из исходного кода

Откройте два терминала из корневой папки репозитория.

### 1. Backend

```bash
cd backend
python -m venv venv
```

Активируйте виртуальное окружение:

```bash
# macOS / Linux
source venv/bin/activate

# Windows PowerShell
venv\Scripts\Activate.ps1
```

Установите зависимости и запустите API:

```bash
pip install -r requirements.txt
python run.py
```

Backend по умолчанию доступен по адресу `http://127.0.0.1:5000`. SQLite-база данных создаётся локально автоматически. При необходимости скопируйте `backend/.env.example` в `backend/.env` и задайте параметры приложения и базы данных.

### 2. Frontend

Во втором терминале:

```bash
cd frontend
npm install
npm run dev
```

Откройте [http://localhost:3000](http://localhost:3000). Frontend по умолчанию обращается к API по адресу `http://localhost:5000/api`. Чтобы изменить адрес или тайм-аут, создайте `frontend/.env.local` на основе `frontend/.env.example`:

```env
NEXT_PUBLIC_API_URL=http://localhost:5000/api
NEXT_PUBLIC_API_TIMEOUT=15000
```

Оба сервера должны быть запущены, пока вы работаете с приложением.

## Как пользоваться

1. Убедитесь, что backend и frontend запущены, затем откройте приложение в браузере.
2. В левой панели **Projects** введите имя проекта и абсолютный путь к локальной папке с исходным кодом, затем нажмите **Scan project**.
3. Выберите проект в списке. Вкладка **Architecture** показывает найденные файлы и зависимости. Перемещайтесь по графу, используйте поиск (по `Ctrl+F` или `⌘+F`), масштабирование и выбор узлов, чтобы изучать связи.
4. Если изменили файлы, запустите повторный анализ кнопкой на панели графа. Переключатель live monitoring включает поток файловых событий для выбранного проекта.
5. Откройте **Rules**, чтобы добавить правила проекта: каждое правило вводится с новой строки; выберите категорию и нажмите **Sync rules**.
6. Нажмите кнопку восстановления контекста в верхней панели или используйте `Ctrl+Shift+C` / `⌘+Shift+C`. Выберите сводку архитектуры, подграф модуля либо недавние изменения. Для подграфа выберите модуль и глубину связей, затем сгенерируйте текст и скопируйте его в чат с ИИ.

Удаление проекта из списка удаляет его запись и связанные данные ContextPilot; исходная папка проекта не удаляется.

## Анализ кода

Анализатор распознаёт файлы JavaScript, TypeScript, Vue, Svelte, Python, Ruby, Go, Java, Kotlin, Rust, PHP, C#, C/C++, Swift и Objective-C. Связи импортов сейчас строятся для JavaScript, TypeScript, Vue, Svelte и Python, когда импорт удаётся сопоставить с файлом внутри проекта. Поэтому граф показывает найденные внутренние связи, а не полный список внешних пакетов. Архитектурные слои приблизительно определяются по именам папок и файлов.

## Desktop-режим (Electron)

Для разработки запустите Next.js (`npm run dev`) и backend в отдельных терминалах, затем в `frontend` выполните:

```bash
npm run desktop:dev
```

Команда запускает Electron-оболочку, которая подключается к локальному frontend. Для сборки desktop frontend и запуска Electron используйте `npm run build:desktop && npm run desktop`. Backend API всё равно должен быть запущен отдельно.

## Хранилище и настройки

- Backend: `backend/.env`; шаблон настроек — `backend/.env.example`.
- Frontend: `frontend/.env.local`; шаблон настроек — `frontend/.env.example`.
- По умолчанию backend использует SQLite в папке `backend/instance/`.
- Путь к другой базе можно задать через `DATABASE_URL` в backend `.env` (формат SQLAlchemy).

---

# ContextPilot (English)

**ContextPilot** helps developers understand a software project's architecture. It analyzes source code, builds an interactive graph of modules and dependencies, tracks file changes, and creates a compact project context you can share with an AI assistant.

This README is available in Russian and English.

## Features

- Scan local projects and visualize source files and detected dependencies.
- Search for modules, inspect their details, and navigate the graph.
- Re-analyze projects and monitor file changes in real time.
- View Git status and recent changes.
- Add architecture rules and review detected violations.
- Generate AI-ready context: an architecture summary, a selected module's subgraph, or recent changes and violations. Copy the result into Cursor, Claude, ChatGPT, or another AI tool.

## Requirements

- Python 3.10+ (the backend uses Flask).
- Node.js and npm (the frontend uses Next.js).
- Git is optional and required only to display Git status.

## Run from source

Open two terminals in the repository root.

### 1. Backend

```bash
cd backend
python -m venv venv
```

Activate the virtual environment:

```bash
# macOS / Linux
source venv/bin/activate

# Windows PowerShell
venv\Scripts\Activate.ps1
```

Install dependencies and start the API:

```bash
pip install -r requirements.txt
python run.py
```

By default, the backend is available at `http://127.0.0.1:5000`. A local SQLite database is created automatically. To configure the app or database, copy `backend/.env.example` to `backend/.env` and edit it.

### 2. Frontend

In the second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). By default, the frontend connects to the API at `http://localhost:5000/api`. To change the API URL or request timeout, create `frontend/.env.local` from `frontend/.env.example`:

```env
NEXT_PUBLIC_API_URL=http://localhost:5000/api
NEXT_PUBLIC_API_TIMEOUT=15000
```

Keep both servers running while using the app.

## How to use

1. Start the backend and frontend, then open the app in your browser.
2. In the **Projects** sidebar, enter a project name and the absolute path to a local source-code folder, then click **Scan project**.
3. Select the project. The **Architecture** tab shows detected files and dependencies. Navigate the graph, search with `Ctrl+F` or `⌘+F`, zoom, and select nodes to explore relationships.
4. After editing files, run a fresh analysis with the graph toolbar button. Turn on live monitoring to receive file events for the selected project.
5. Open **Rules** to add project rules. Enter one rule per line, choose a category, and click **Sync rules**.
6. Click the context recovery button in the top bar or press `Ctrl+Shift+C` / `⌘+Shift+C`. Choose an architecture summary, a module subgraph, or recent changes. For a subgraph, select a module and dependency depth, generate the text, and copy it into your AI chat.

Deleting a project removes its ContextPilot record and associated data, but leaves the original source folder untouched.

## Code analysis

The analyzer recognizes JavaScript, TypeScript, Vue, Svelte, Python, Ruby, Go, Java, Kotlin, Rust, PHP, C#, C/C++, Swift, and Objective-C files. Import edges are currently built for JavaScript, TypeScript, Vue, Svelte, and Python when an import can be resolved to a file inside the project. The graph therefore shows detected internal dependencies rather than a complete list of external packages. Architecture layers are inferred approximately from folder and file names.

## Desktop mode (Electron)

For development, start Next.js (`npm run dev`) and the backend in separate terminals, then run this from `frontend`:

```bash
npm run desktop:dev
```

This starts the Electron shell, which connects to the local frontend. To build the desktop frontend and launch Electron, run `npm run build:desktop && npm run desktop`. The backend API must still be running separately.

## Storage and configuration

- Backend settings: `backend/.env`; template: `backend/.env.example`.
- Frontend settings: `frontend/.env.local`; template: `frontend/.env.example`.
- By default, the backend stores SQLite data in `backend/instance/`.
- Set `DATABASE_URL` in the backend `.env` to use a different database (SQLAlchemy URL format).
