# Pipeline Steps

Ниже шаги в порядке запуска из `main.py`.

При запуске `python3 main.py` сначала выбирается режим:
- `1` — запустить прямо сейчас и выбрать стартовый шаг вручную.
- `2` — запустить по данным из `pipeline_config.py`: дождаться `START_TIME` и начать с `START_STEP`.
- `3` — VLESS-only по данным из `pipeline_config.py`: пропустить SS-ключи, собрать VLESS-подписки, сделать `git commit + push` без Telegram-уведомлений.

1. Сформировать JSON + top10
- Скрипт: `main.py` (функция `run_top10_only`)
- Логика: `src/pipeline_shared_tools.py` (`build_json_and_top10`)

2. Сформировать ключи из top10
- Скрипт: `main.py` (функция `run_keys_only`)
- Логика: `src/pipeline_shared_tools.py` (`extract_keys_from_top10`)

3. Проверка ключей через xray (ping) и запись живых
- Скрипт: `src/ping_keys_with_xray.py`

4. 3 прогона по живым ключам и отбор топ лучших
- Скрипт: `src/rerank_ping_ok_keys.py`

5. Переписать описания top ключей (канал + номер + флаг)
- Скрипт: `src/rewrite_toplive_descriptions.py`

6. Записать top live ключи в git файлы
- Скрипт: `src/write_git_publish_files.py`

7. Отправить SS ключи в Telegram
- Скрипт: `src/send_ss_to_telegram.py`

8. Git commit + push + Telegram notify
- Скрипт: `src/git_commit_push_and_notify.py`

## VLESS-only без Telegram
Режим `3` использует тот же порядок пайплайна, но:
- на шаге ping передает `--skip-ss`, поэтому `ss://` ключи не проверяются;
- шаг отправки SS в Telegram не запускается;
- финальный шаг запускает `src/git_commit_push_and_notify.py --no-notify`, поэтому выполняется только `git commit + push`.

## Дополнительные утилиты
- `src/make_json_top10_from_checked.py` — CLI-утилита для шага 1.
- `src/extract_keys_from_top10.py` — CLI-утилита для шага 2.
- `src/build_subs_report.py` — отдельный объединенный скрипт отчета/сборки (не используется в основном линейном запуске `main.py`).
