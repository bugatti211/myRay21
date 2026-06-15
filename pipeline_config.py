# Номер шага, с которого запускать пайплайн.
START_STEP = 2

# Время запуска пайплайна в формате "ЧЧ:ММ".
# Поставь None или "" для запуска сразу.
START_TIME = "20:01"

# Шаг 3: первичная проверка ключей через xray.
PING_CONCURRENCY = 300
PING_TIMEOUT = 9
MAX_ALIVE_VLESS = 500  
MAX_ALIVE_SS = 200

# Шаг 4: повторные прогоны живых ключей и ранжирование.
RERANK_CONCURRENCY = 100
RERANK_TIMEOUT = 8
RERANK_RUNS = 3
