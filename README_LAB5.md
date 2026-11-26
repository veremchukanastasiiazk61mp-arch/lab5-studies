# ЛР5. Потокобезпечна структура даних (варіант 5)

Структура С5: агрегатор статистики інтенсивностей з 25 кошиками. Запис `add(value)`, читання `snapshot()`.
n = 3 потоки: потоки 1 і 3 пишуть, потік 2 читає (n_w = 2, n_r = 1). Мова: Python, лише `threading`.

## Склад

- `stand/aggregator.py` структура і перевірка інваріантів
- `stand/rwlock.py` RWLock на `threading.Condition`, дві політики (`writer`, `reader`)
- `stand/stand.py` стенд: режими `run`, `x1`, `cs`
- `scripts/run_all.py` усі прогони підряд
- `analysis/analyze_lab5.py` таблиці 1-6 і діаграма
- `tests/test_lab5.py` перевірка структури, замків і стенду
- `results/lab5/` результати прогонів (JSON) і таблиці (md)

## Запуск (Git Bash, з кореня репозиторію)

```bash
python -m unittest discover -s tests -t .
python scripts/run_all.py --rw-policies writer,reader
python analysis/analyze_lab5.py --rw rw-writer
python analysis/analyze_lab5.py --rw rw-reader
```

Перед прогонами закрийте інші програми й підключіть ноутбук до живлення. Повний набір прогонів триває близько
5 хвилин. Окремий прогін: `python -m stand.stand run --lock global --n 3`.

## Як вимірюється

- Прогрів 1 с, вимір D = 10 с, 3 прогони, у таблицях прогін із медіанним X.
- τ = t_ret − t_call, t_wait = t_acq − t_call; час береться `time.perf_counter_ns()`.
- Після кожного знімка читач перевіряє, що сума кошиків дорівнює count (поза виміром τ).
- Після прогону перевіряється: сума кошиків = count, count = кількість викликів `add`, sum і sum_sq узгоджені з кошиками.
- X_1: один потік по черзі виконує два записи і одне читання (n_w : n_r = 2 : 1) під тим самим замком.
- t_cs: однопотоковий прогін, час між отриманням і звільненням замка для запису і для читання окремо.
