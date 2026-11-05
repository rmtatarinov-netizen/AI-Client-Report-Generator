# AI Client Report Generator

Автоматическая генерация PDF-отчётов по транскрибациям диалогов с клиентами. Текст диалога передаётся в OpenAI-совместимую модель через ProxyAPI, результат структурируется в JSON, подставляется в HTML-шаблон Jinja2 и сохраняется в PDF с помощью WeasyPrint.

Отдельный модуль транскрибирует MP3-записи телефонных разговоров через `gpt-4o-transcribe-diarize`, разделяет реплики по говорящим и сохраняет расшифровку в PDF. Модули отчётов и транскрибации используют общий OpenAI-клиент и общий PDF-движок, но запускаются независимо.

## Возможности

- Генерация PDF-отчёта из текстового файла, строки или интерактивного ввода.
- Извлечение структурированных данных через ИИ: клиент, тема, запрос, настроение, следующие шаги.
- Демо-режим без обращения к API.
- Flask API с загрузкой файла и скачиванием готового PDF.
- Транскрибация MP3-записей телефонных разговоров с диаризацией спикеров.
- Настраиваемые HTML-шаблоны отчёта и расшифровки.
- Выбор папки сохранения и защита от перезаписи файлов с одинаковыми именами.

## Стек

- Python 3.10+ (проверено на Python 3.14)
- OpenAI SDK через ProxyAPI
- Модели `gpt-4o-mini` и `gpt-4o-transcribe-diarize`
- Jinja2
- WeasyPrint
- Flask
- python-dotenv

## Требования

Для работы WeasyPrint нужны системные библиотеки GTK/Pango.

### Windows

Установите GTK3 Runtime:

```powershell
winget install -e --id tschoonj.GTKForWindows
```

После установки проверьте импорт:

```powershell
python -c "import weasyprint; print(weasyprint.__version__)"
```

### Linux

```bash
sudo apt install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libffi-dev
```

### macOS

```bash
brew install pango
```

## Установка

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Для Linux/macOS активация виртуального окружения:

```bash
source .venv/bin/activate
```

## Настройка

Создайте `.env` на основе `.env.example`:

```powershell
Copy-Item .env.example .env
```

Заполните переменные:

```env
PROXY_API_KEY=your_proxy_api_key_here
PROXY_BASE_URL=https://api.proxyapi.ru/openai/v1
OPENAI_MODEL=gpt-4o-mini
TRANSCRIPTION_MODEL=gpt-4o-transcribe-diarize
TRANSCRIPTION_LANGUAGE=ru
```

| Переменная | Назначение |
| --- | --- |
| `PROXY_API_KEY` | API-ключ ProxyAPI |
| `PROXY_BASE_URL` | Базовый URL OpenAI-совместимого API |
| `OPENAI_MODEL` | Модель анализа диалога, например `gpt-4o-mini` |
| `TRANSCRIPTION_MODEL` | Модель транскрибации, по умолчанию `gpt-4o-transcribe-diarize` |
| `TRANSCRIPTION_LANGUAGE` | Язык записей, по умолчанию `ru` |

Файл `.env` добавлен в `.gitignore`. Не публикуйте ключ и не коммитьте его в репозиторий.

## Использование CLI

Демо-отчёт без вызова ИИ:

```powershell
python main.py --demo
```

Отчёт по файлу с транскрибацией:

```powershell
python main.py --input samples/sample_dialog.txt
```

Отчёт по тексту, переданному строкой:

```powershell
python main.py --text "Клиент: Здравствуйте! Менеджер: Добрый день!"
```

Интерактивный ввод (завершается пустой строкой):

```powershell
python main.py
```

Сохранение в другую папку:

```powershell
python main.py --input samples/sample_dialog.txt --output-dir custom_reports
```

По умолчанию PDF сохраняется в `reports/` с именем вида:

```text
report_2026-11-05_00-37.pdf
```

Если файл с таким именем уже существует, добавляется суффикс `_1`, `_2` и так далее.

## Flask API

Запуск сервера:

```powershell
python main.py --serve
```

Веб-интерфейс: `http://127.0.0.1:5000/`.

Дополнительные параметры:

```powershell
python main.py --serve --host 0.0.0.0 --port 8080
```

### Проверка состояния

```http
GET /health
```

Ответ:

```json
{"status": "ok"}
```

### Создание отчёта из JSON

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:5000/api/report `
  -ContentType "application/json" `
  -Body '{"transcript": "Клиент: Здравствуйте! Хочу подключить тариф."}'
```

Демо-режим через API:

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:5000/api/report `
  -ContentType "application/json" `
  -Body '{"demo": true}'
```

### Загрузка файла

```powershell
curl.exe -X POST http://127.0.0.1:5000/api/report `
  -F "file=@samples/sample_dialog.txt" `
  -F "demo=true"
```

Поддерживаются кодировки UTF-8 и CP1251. Максимальный размер загружаемого файла — 2 МБ.

### Ответ API

```json
{
  "status": "success",
  "file": "report_2026-11-05_00-37.pdf",
  "path": "reports/report_2026-11-05_00-37.pdf",
  "url": "/reports/report_2026-11-05_00-37.pdf",
  "report": {
    "client_name": "ООО «Ромашка»",
    "topic": "Подключение корпоративного тарифа",
    "main_request": "Клиент хочет подключить тариф для 25 сотрудников.",
    "mood": "Заинтересован",
    "next_steps": "Отправить коммерческое предложение и выставить счёт."
  }
}
```

### Скачивание PDF

```powershell
Invoke-WebRequest `
  -Uri http://127.0.0.1:5000/reports/report_2026-11-05_00-37.pdf `
  -OutFile report.pdf
```

## Транскрибация MP3

Транскрибация доступна через веб-интерфейс и Flask API. Обработка выполняется асинхронно: POST-запрос сразу возвращает `task_id`, а прогресс можно опрашивать по `status_url`.

### Веб-интерфейс

1. Запустите сервер:

```powershell
python main.py --serve
```

2. Откройте в браузере `http://127.0.0.1:5000/`.

3. Выберите или перетащите MP3-файл до 25 МБ и нажмите «Начать транскрибацию».

На странице автоматически отображаются этапы обработки, таймер и статус: `Файл` → `Транскрибация` → `PDF` → `Готово`. После завершения можно скачать PDF и посмотреть расшифровку с метками спикеров прямо на странице. Повторять запросы вручную не нужно.

### API

1. Отправьте MP3-файл в поле `file`:

```powershell
curl.exe -s -X POST http://127.0.0.1:5000/api/transcribe `
  -F "file=@samples/call.mp3"
```

Ответ `202 Accepted`:

```json
{
  "status": "accepted",
  "task_id": "1f3c9d2e7a8b4c6d9e0f1a2b3c4d5e6f",
  "status_url": "/api/transcribe/1f3c9d2e7a8b4c6d9e0f1a2b3c4d5e6f",
  "message": "Файл принят. Опрашивайте status_url, чтобы видеть этап обработки."
}
```

2. Опрашивайте статус. Пример цикла PowerShell:

```powershell
$response = curl.exe -s -X POST http://127.0.0.1:5000/api/transcribe `
  -F "file=@samples/call.mp3" | ConvertFrom-Json

while ($response.status -in @("queued", "processing")) {
  Start-Sleep -Seconds 2
  $response = Invoke-RestMethod `
    "http://127.0.0.1:5000/api/transcribe/$($response.task_id)"
  Write-Host "$($response.status) / $($response.stage): $($response.message)"
}

$response
```

Статусы задачи:

- `queued` — задача в очереди;
- `processing` — идёт транскрибация или генерация PDF;
- `completed` — PDF готов;
- `failed` — ошибка, подробности в полях `message`, `error`, `http_status`.

Этапы `stage`: `queued`, `transcribing`, `generating_pdf`, `done`, `failed`. Поле `elapsed_seconds` показывает время с момента создания задачи.

Пример завершённой задачи:

```json
{
  "status": "completed",
  "task_id": "1f3c9d2e7a8b4c6d9e0f1a2b3c4d5e6f",
  "stage": "done",
  "message": "PDF с расшифровкой готов.",
  "filename": "call.mp3",
  "elapsed_seconds": 42.7,
  "file": "transcript_call_2026-11-05_18-30.pdf",
  "path": "reports/transcript_call_2026-11-05_18-30.pdf",
  "url": "/reports/transcript_call_2026-11-05_18-30.pdf",
  "transcript": {
    "source_name": "call.mp3",
    "model": "gpt-4o-transcribe-diarize",
    "language": "ru",
    "duration": 93.4,
    "duration_display": "1 мин 33 с",
    "text": "Оператор: Добрый день! Клиент: Здравствуйте...",
    "segments": [
      {
        "speaker": "Спикер A",
        "start": 0.0,
        "end": 8.2,
        "text": "Добрый день!"
      }
    ]
  }
}
```

Ограничения и поведение:

- Поддерживаются только файлы `.mp3` размером до 25 МБ.
- Используется модель OpenAI `gpt-4o-transcribe-diarize` с `response_format=diarized_json`. В ProxyAPI она доступна без префикса `openai/`.
- Реплики разделяются по говорящим. Метки `Спикер A`, `Спикер B` и т. п. не определяют роль оператора или клиента.
- Исходный MP3 не изменяется и не удаляется.
- PDF сохраняется в `reports/` с именем вида `transcript_call_2026-11-05_18-30.pdf`.
- В PDF входит заголовок, имя исходного файла, дата формирования, длительность и расшифровка с метками спикеров.
- Задачи хранятся в памяти процесса 1 час и пропадают при перезапуске сервера.
- Для production с несколькими worker-процессами нужен внешний брокер задач, например Celery + Redis. Текущая реализация использует `ThreadPoolExecutor` и не требует Redis.

### Коды ошибок API

| Код | Причина |
| --- | --- |
| `202` | Аудиофайл принят, задача создана |
| `400` | Некорректный запрос, пустая транскрибация или файл не в формате MP3 |
| `404` | Задача транскрибации не найдена |
| `413` | Файл больше 2 МБ для отчёта или больше 25 МБ для аудио |
| `500` | Ошибка генерации PDF |
| `502` | Ошибка обращения к прокси-провайдеру или транскрибации |

Для `GET /api/transcribe/<task_id>` успешный ответ возвращается с кодом `200` даже при статусе `failed`. Код ошибки обработки находится в поле `http_status`.

## Структура проекта

```text
AI Client Report Generator/
├── main.py                     # CLI и запуск Flask API
├── app.py                      # Flask: веб-интерфейс, API отчётов и транскрибации
├── templates/
│   ├── index.html              # Веб-интерфейс загрузки MP3 и статуса
│   ├── report_template.html    # HTML-шаблон аналитического отчёта
│   └── transcript_template.html # HTML-шаблон расшифровки MP3
├── excel_report/               # Генератор Excel/PDF-отчёта АО «Святогор»
├── registries/                 # Входные реестры (не коммитить)
├── reports/                    # Готовые PDF и Excel-отчёты
├── utils/
│   ├── __init__.py
│   ├── openai_client.py        # Общий клиент ProxyAPI и ошибки
│   ├── ai_processor.py         # Анализ текста и разбор JSON
│   ├── audio_transcriber.py    # MP3 → диаризованная транскрибация
│   ├── transcript_pdf.py       # Подготовка данных для PDF-расшифровки
│   └── pdf_generator.py        # Общий HTML → PDF движок
├── samples/
│   └── sample_dialog.txt       # Пример текстовой транскрибации
├── .env                        # Локальные секреты (не коммитить)
├── .env.example                # Пример конфигурации
├── .gitignore
├── requirements.txt
└── README.md
```

## Excel-отчёт АО «Святогор»

В проект входит отдельный модуль `excel_report` для еженедельного отчёта по реестру предписаний.

1. Положите актуальный реестр в `registries\`:
   `Реестр предписаний АО Святогор_ДД.ММ.ГГГГ.xlsx`.
2. Старые реестры переносите в `registries\archive\` — генератор их не использует.
3. Запустите отчёт:

```powershell
python excel_report\generate_report.py --start 30.10.2026 --end 05.11.2026
```

Excel и PDF сохраняются в `reports\`. В PDF попадают только столбцы `A:F`, без сетки; служебные столбцы `G:Y` скрыты. Строки с `Предписаний больше нет` автоматически скрываются. В разделах `Замечания АО` без реальных замечаний остаётся одна строка `Предписаний нет`, остальные скрываются; если реальные замечания есть, все строки `Предписаний нет` скрываются. Для работы нужен установленный Microsoft Excel и `pywin32`.

Подробнее: [`excel_report/README.md`](excel_report/README.md).

## Как это работает

### Аналитический отчёт

1. `main.py` читает транскрибацию из файла, аргумента `--text` или интерактивного ввода.
2. `utils/ai_processor.py` отправляет текст в модель через OpenAI-совместимый API ProxyAPI.
3. Модель возвращает JSON с полями `client_name`, `topic`, `main_request`, `mood`, `next_steps`.
4. Ответ валидируется и нормализуется: пропущенные значения заменяются на «Не указано».
5. `utils/pdf_generator.py` рендерит `templates/report_template.html` через Jinja2.
6. WeasyPrint конвертирует HTML в PDF и сохраняет файл в `reports/`.

### Транскрибация MP3

1. Flask API принимает MP3 в `POST /api/transcribe`, проверяет формат и размер, создаёт задачу и сразу возвращает `task_id`.
2. Задача выполняется в фоновом `ThreadPoolExecutor`; статус доступен в `GET /api/transcribe/<task_id>`.
3. `utils/audio_transcriber.py` отправляет файл в `gpt-4o-transcribe-diarize` и получает `diarized_json` с сегментами: спикер, начало, конец, текст.
4. Сегменты нормализуются и объединяются, `utils/transcript_pdf.py` готовит данные и имя файла.
5. Общий `utils/pdf_generator.py` рендерит `templates/transcript_template.html` и сохраняет PDF в `reports/`.
6. Статус задачи меняется на `completed`, PDF и расшифровка становятся доступны в ответе `status_url`.

## Кастомизация

- Внешний вид аналитического отчёта: `templates/report_template.html`.
- Внешний вид расшифровки: `templates/transcript_template.html`.
- Модель анализа: переменная `OPENAI_MODEL` в `.env`.
- Модель транскрибации: переменная `TRANSCRIPTION_MODEL` в `.env`.
- Язык транскрибации: переменная `TRANSCRIPTION_LANGUAGE` в `.env`.
- Базовый URL API: переменная `PROXY_BASE_URL` в `.env`.
- Папка сохранения отчётов CLI: флаг `--output-dir`; PDF-расшифровки сохраняются в `reports/`.

## Типовые ошибки

### WeasyPrint не может загрузить GTK/Pango

Установите GTK3 Runtime:

```powershell
winget install -e --id tschoonj.GTKForWindows
```

Проверьте:

```powershell
python -c "import weasyprint; print('ok')"
```

### `400: Model not supported`

ProxyAPI не поддерживает указанное имя модели. Для анализа используйте:

```env
OPENAI_MODEL=gpt-4o-mini
```

Для транскрибации:

```env
TRANSCRIPTION_MODEL=gpt-4o-transcribe-diarize
```

### Неверный API-ключ

Проверьте `PROXY_API_KEY` в `.env`. При утечке ключа отзовите его в личном кабинете ProxyAPI и выпустите новый.

### Нет соединения с прокси-провайдером

Проверьте интернет-соединение и значение `PROXY_BASE_URL`.

### Пустая транскрибация

Передайте непустой текст через `--input`, `--text` или в интерактивном режиме. Для проверки без ИИ используйте `--demo`.

### Ошибка транскрибации MP3

- Откройте `GET /api/transcribe/<task_id>` и проверьте поля `stage`, `message`, `error` и `http_status`.
- Убедитесь, что файл имеет расширение `.mp3` и размер не больше 25 МБ.
- Проверьте, что `TRANSCRIPTION_MODEL=gpt-4o-transcribe-diarize` поддерживается вашим тарифом ProxyAPI.
- Для длинных записей используйте MP3 с меньшим битрейтом либо сожмите файл перед загрузкой.

## Безопасность

- `.env` исключён из git через `.gitignore`.
- Не выводите содержимое `.env` в логи, чаты и скриншоты.
- При компрометации ключа немедленно отзовите его и выпустите новый.
- Аудиозапись отправляется внешнему провайдеру для транскрибации. Не загружайте записи без согласия участников и соблюдайте требования к обработке персональных данных.
- Приложение не сохраняет копию MP3 и не пишет текст расшифровки в логи.
