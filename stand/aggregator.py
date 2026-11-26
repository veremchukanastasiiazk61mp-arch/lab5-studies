"""Структура С5: агрегатор статистики інтенсивностей з 25 кошиками."""

BUCKETS = 25


class Aggregator:
    __slots__ = ("buckets", "count", "total", "total_sq")

    def __init__(self):
        self.buckets = [0] * BUCKETS
        self.count = 0
        self.total = 0
        self.total_sq = 0

    def add(self, value):
        # Запис. Викликається під замком у режимі запису.
        self.buckets[value] += 1
        self.count += 1
        self.total += value
        self.total_sq += value * value

    def snapshot(self):
        # Читання. Поля структури не змінюються, повертається копія кошиків.
        return (list(self.buckets), self.count, self.total, self.total_sq)

    def check(self, expected_adds):
        """Інваріанти після прогону. Повертає список порушень (порожній, якщо все гаразд)."""
        problems = []
        if sum(self.buckets) != self.count:
            problems.append(f"сума кошиків {sum(self.buckets)} != count {self.count}")
        if self.count != expected_adds:
            problems.append(f"count {self.count} != кількість викликів add {expected_adds}")
        if self.total != sum(i * c for i, c in enumerate(self.buckets)):
            problems.append("sum не збігається з сумою i * кошик[i]")
        if self.total_sq != sum(i * i * c for i, c in enumerate(self.buckets)):
            problems.append("sum_sq не збігається з сумою i^2 * кошик[i]")
        return problems
