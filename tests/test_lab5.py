import threading
import time
import unittest

from stand.aggregator import Aggregator, BUCKETS
from stand.rwlock import RWLock
from stand import stand


class AggregatorTests(unittest.TestCase):
    def test_invariants_after_adds(self):
        a = Aggregator()
        for v in (0, 24, 5, 5, 12):
            a.add(v)
        self.assertEqual(a.check(5), [])
        buckets, count, total, total_sq = a.snapshot()
        self.assertEqual(len(buckets), BUCKETS)
        self.assertEqual((sum(buckets), count, total, total_sq), (5, 5, 46, 0 + 576 + 25 + 25 + 144))

    def test_check_detects_corruption(self):
        a = Aggregator()
        a.add(3)
        a.count += 1
        self.assertTrue(a.check(1))

    def test_snapshot_does_not_change_state(self):
        a = Aggregator()
        for v in range(10):
            a.add(v)
        before = (list(a.buckets), a.count, a.total, a.total_sq)
        snap = a.snapshot()
        snap[0][0] = 999
        self.assertEqual((a.buckets, a.count, a.total, a.total_sq), before)


class RWLockTests(unittest.TestCase):
    def test_readers_share(self):
        for policy in ("writer", "reader"):
            lock = RWLock(policy)
            lock.acquire_read()
            got = []
            t = threading.Thread(target=lambda: (lock.acquire_read(), got.append(1), lock.release_read()))
            t.start()
            t.join(1)
            self.assertEqual(got, [1], policy)
            lock.release_read()

    def test_writer_excludes_readers_and_writers(self):
        for policy in ("writer", "reader"):
            lock = RWLock(policy)
            lock.acquire_write()
            got = []
            ts = [threading.Thread(target=lambda f=f, r=r: (f(), got.append(1), r()))
                  for f, r in ((lock.acquire_read, lock.release_read), (lock.acquire_write, lock.release_write))]
            for t in ts:
                t.start()
            time.sleep(0.2)
            self.assertEqual(got, [], policy)
            lock.release_write()
            for t in ts:
                t.join(2)
            self.assertEqual(len(got), 2, policy)

    def test_no_lost_updates(self):
        lock = RWLock("writer")
        agg = Aggregator()

        def w():
            for _ in range(5000):
                lock.acquire_write()
                agg.add(1)
                lock.release_write()

        ts = [threading.Thread(target=w) for _ in range(4)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(agg.check(20000), [])


class StandTests(unittest.TestCase):
    def test_percentile(self):
        vals = list(range(1, 101))
        self.assertEqual(stand.percentile(vals, 0.5), 50)
        self.assertEqual(stand.percentile(vals, 0.99), 99)
        self.assertEqual(stand.percentile([7], 0.99), 7)

    def test_cv(self):
        self.assertEqual(stand.cv_of([5, 5, 5]), 0.0)
        self.assertAlmostEqual(stand.cv_of([4, 6]), 0.2)

    def _run(self, *args):
        return stand.main(["run", "--duration", "0.3", "--warmup", "0.1"] + list(args))

    def test_run_global_and_rw(self):
        for extra in (["--lock", "global"], ["--lock", "rw", "--rw-policy", "writer"], ["--lock", "rw", "--rw-policy", "reader"]):
            r = self._run("--n", "3", *extra)
            self.assertTrue(r["invariants_ok"], r["invariant_problems"])
            self.assertEqual((r["meta"]["n_w"], r["meta"]["n_r"]), (2, 1))
            self.assertEqual(len(r["threads"]), 3)
            self.assertEqual([t["role"] for t in r["threads"]], ["запис", "читання", "запис"])
            self.assertGreater(r["roles"]["write"]["ops"], 0)
            self.assertGreater(r["roles"]["read"]["ops"], 0)
            ro = r["roles"]
            self.assertAlmostEqual(ro["all"]["X"], ro["write"]["X"] + ro["read"]["X"])
            self.assertAlmostEqual(ro["write"]["phi"] + ro["read"]["phi"], 1.0)

    def test_thread_split(self):
        r = self._run("--n", "5", "--lock", "global")
        self.assertEqual((r["meta"]["n_w"], r["meta"]["n_r"]), (3, 2))

    def test_x1_and_cs(self):
        r = stand.main(["x1", "--lock", "global", "--n", "3", "--duration", "0.3", "--warmup", "0.1"])
        self.assertEqual(r["pattern"], "wwr")
        self.assertGreater(r["X1"], 0)
        self.assertAlmostEqual(r["ops_w"] / r["ops_r"], 2.0, delta=0.01)
        c = stand.main(["cs", "--lock", "rw", "--role", "r", "--duration", "0.3", "--warmup", "0.1"])
        self.assertGreater(c["t_cs_us"], 0)


if __name__ == "__main__":
    unittest.main()
