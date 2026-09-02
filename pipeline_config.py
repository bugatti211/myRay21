# Номер шага, с которого запускать пайплайн.
START_STEP = 1

# Ежедневные точки запуска пайплайна в формате "ЧЧ:ММ".
# Можно оставить одну строку: START_TIME = "08:00".
# None или [] — один запуск сразу без ожидания и повторения.
START_TIME = ["06:30", "09:01", "11:50", "13:41", "23:06"]

# Шаг 2: ранее опубликованные живые ключи повторно входят в проверку.
PUBLISHED_SUBSCRIPTIONS_BASE_URL = (
    "https://raw.githubusercontent.com/terik21/"
    "HiddifySubs-VlessKeys/main"
)
PUBLISHED_DOWNLOAD_TIMEOUT = 30

# Шаг 2: первичная проверка ключей через xray.
PING_CONCURRENCY = 300
PING_TIMEOUT = 10
MAX_ALIVE_VLESS = 2500
MAX_ALIVE_TROJAN = 50

# Шаг 3: повторные прогоны живых ключей и ранжирование.
RERANK_CONCURRENCY = 200
RERANK_TIMEOUT = 12
RERANK_RUNS = 3
