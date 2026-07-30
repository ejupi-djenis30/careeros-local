from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.automation.reauth import AccountReauthenticationGuard


def test_guard_locks_only_the_account_that_repeatedly_fails() -> None:
    current = [100.0]
    guard = AccountReauthenticationGuard(
        max_failures=2,
        failure_window_seconds=30,
        lockout_seconds=20,
        clock=lambda: current[0],
    )

    assert guard.register_failure(7) is None
    assert guard.register_failure(7) == 20
    assert guard.retry_after(7) == 20
    assert guard.retry_after(8) is None

    current[0] += 6.2
    assert guard.retry_after(7) == 14
    current[0] += 14
    assert guard.retry_after(7) is None


def test_success_and_failure_window_expiry_clear_old_failures() -> None:
    current = [50.0]
    guard = AccountReauthenticationGuard(
        max_failures=3,
        failure_window_seconds=10,
        lockout_seconds=20,
        clock=lambda: current[0],
    )

    assert guard.register_failure(4) is None
    guard.register_success(4)
    assert guard.register_failure(4) is None

    current[0] += 11
    assert guard.register_failure(4) is None
    assert guard.retry_after(4) is None


def test_guard_serializes_password_verification_per_account() -> None:
    guard = AccountReauthenticationGuard()
    counter_lock = threading.Lock()
    active = 0
    maximum_active = 0

    def verify() -> None:
        nonlocal active, maximum_active
        with guard.serialize_verification(12):
            with counter_lock:
                active += 1
                maximum_active = max(maximum_active, active)
            time.sleep(0.01)
            with counter_lock:
                active -= 1

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda _: verify(), range(8)))

    assert maximum_active == 1


def test_guard_allows_different_accounts_to_verify_independently() -> None:
    guard = AccountReauthenticationGuard()
    both_inside = threading.Barrier(2)

    def verify(user_id: int) -> None:
        with guard.serialize_verification(user_id):
            both_inside.wait(timeout=1)

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(verify, (12, 13)))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_failures": 0},
        {"failure_window_seconds": 0},
        {"lockout_seconds": 0},
    ],
)
def test_guard_rejects_non_positive_limits(kwargs) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        AccountReauthenticationGuard(**kwargs)
