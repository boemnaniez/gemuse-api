"""Tes AccountPool — stdlib unittest, tanpa dependensi."""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gemuse.pool import Account, AccountPool, COOLDOWN_SECONDS


def make_account(label, used_percent=0, enabled=True, status="active"):
    return Account(label=label, used_percent=used_percent,
                   enabled=enabled, status=status)


class TestRoundRobin(unittest.TestCase):
    def test_round_robin_bergantian(self):
        pool = AccountPool([make_account("A"), make_account("B")],
                           strategy="round_robin")
        picks = [pool.pick().label for _ in range(4)]
        self.assertEqual(picks, ["A", "B", "A", "B"])

    def test_round_robin_satu_akun(self):
        pool = AccountPool([make_account("A")], strategy="round_robin")
        self.assertEqual(pool.pick().label, "A")
        self.assertEqual(pool.pick().label, "A")


class TestSkip(unittest.TestCase):
    def test_skip_akun_disabled(self):
        pool = AccountPool([make_account("A", enabled=False),
                            make_account("B")])
        self.assertEqual(pool.pick().label, "B")

    def test_skip_akun_quota_100(self):
        pool = AccountPool([make_account("A", used_percent=100),
                            make_account("B", used_percent=10)])
        self.assertEqual(pool.pick().label, "B")

    def test_skip_akun_region_blocked(self):
        pool = AccountPool([make_account("A", status="region_blocked"),
                            make_account("B")])
        self.assertEqual(pool.pick().label, "B")

    def test_tidak_ada_yang_usable(self):
        pool = AccountPool([make_account("A", enabled=False),
                            make_account("B", used_percent=100)])
        self.assertIsNone(pool.pick())


class TestCooldownDanFailover(unittest.TestCase):
    def test_cooldown_setelah_gagal(self):
        pool = AccountPool([make_account("A"), make_account("B")])
        now = time.time()
        pool.mark_failure("A" if False else pool.accounts[0].id, now=now)
        acc_a = pool.accounts[0]
        self.assertGreater(acc_a.cooldown_until, now)
        self.assertLessEqual(acc_a.cooldown_until - now, COOLDOWN_SECONDS + 1)
        # A sedang cooldown -> pick harus B
        self.assertEqual(pool.pick(now=now).label, "B")

    def test_cooldown_habis_bisa_dipakai_lagi(self):
        pool = AccountPool([make_account("A")])
        acc = pool.accounts[0]
        now = time.time()
        pool.mark_failure(acc.id, now=now)
        self.assertIsNone(pool.pick(now=now))
        # Setelah 10 menit + 1 detik, bisa lagi.
        self.assertIsNotNone(pool.pick(now=now + COOLDOWN_SECONDS + 1))

    def test_region_blocked_bukan_cooldown_tapi_status(self):
        pool = AccountPool([make_account("A"), make_account("B")])
        acc = pool.accounts[0]
        pool.mark_failure(acc.id, error_type="region_blocked")
        self.assertEqual(acc.status, "region_blocked")
        self.assertEqual(acc.cooldown_until, 0)
        # Bahkan jauh di masa depan tetap tidak usable.
        self.assertEqual(pool.pick(now=time.time() + 86400).label, "B")

    def test_failover_ke_akun_berikutnya(self):
        pool = AccountPool([make_account("A"), make_account("B")],
                           strategy="round_robin")
        first = pool.pick()
        self.assertEqual(first.label, "A")
        pool.mark_failure(first.id)
        second = pool.pick()
        self.assertEqual(second.label, "B")


class TestLeastUsed(unittest.TestCase):
    def test_least_used_pilih_kuota_paling_sedikit(self):
        pool = AccountPool([
            make_account("A", used_percent=80),
            make_account("B", used_percent=3),
            make_account("C", used_percent=50),
        ], strategy="least_used")
        self.assertEqual(pool.pick().label, "B")

    def test_least_used_skip_quota_habis(self):
        pool = AccountPool([
            make_account("A", used_percent=0),
            make_account("B", used_percent=100),
        ], strategy="least_used")
        self.assertEqual(pool.pick().label, "A")


class TestMarkSuccess(unittest.TestCase):
    def test_mark_success_reset_failed_dan_update_kuota(self):
        pool = AccountPool([make_account("A", used_percent=10)])
        acc = pool.accounts[0]
        pool.mark_failure(acc.id)
        self.assertEqual(acc.failed_count, 1)
        pool.mark_success(acc.id, used_percent=33)
        self.assertEqual(acc.failed_count, 0)
        self.assertEqual(acc.used_percent, 33)


if __name__ == "__main__":
    unittest.main()
