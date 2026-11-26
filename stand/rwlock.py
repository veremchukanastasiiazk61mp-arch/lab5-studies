"""Замок читання-запису на threading.Condition.

Політика writer: писці мають пріоритет. Поки хоч один писець чекає або пише,
нові читачі не допускаються і чекають; читачі, що вже тримають замок,
завершують роботу. Читачі можуть голодувати, якщо писці надходять без перерви.

Політика reader: читачі мають пріоритет. Новий читач допускається, якщо замок
не тримає писець, навіть коли писці чекають. Писці можуть голодувати,
якщо читачі надходять без перерви.
"""
import threading


class RWLock:
    def __init__(self, policy="writer"):
        if policy not in ("writer", "reader"):
            raise ValueError("policy має бути writer або reader")
        self.policy = policy
        self._cond = threading.Condition(threading.Lock())
        self._readers = 0
        self._writer = False
        self._waiting_writers = 0

    def acquire_read(self):
        with self._cond:
            if self.policy == "writer":
                while self._writer or self._waiting_writers:
                    self._cond.wait()
            else:
                while self._writer:
                    self._cond.wait()
            self._readers += 1

    def release_read(self):
        with self._cond:
            self._readers -= 1
            if self._readers == 0:
                self._cond.notify_all()

    def acquire_write(self):
        with self._cond:
            self._waiting_writers += 1
            while self._writer or self._readers:
                self._cond.wait()
            self._waiting_writers -= 1
            self._writer = True

    def release_write(self):
        with self._cond:
            self._writer = False
            self._cond.notify_all()
