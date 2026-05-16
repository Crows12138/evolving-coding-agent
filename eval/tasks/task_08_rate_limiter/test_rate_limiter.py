from rate_limiter import RateLimiter


def test_allow_within_limit():
    rl = RateLimiter(3, 10.0)
    assert rl.allow(now=100.0) is True
    assert rl.allow(now=101.0) is True
    assert rl.allow(now=102.0) is True


def test_deny_over_limit():
    rl = RateLimiter(2, 10.0)
    rl.allow(now=100.0)
    rl.allow(now=101.0)
    assert rl.allow(now=102.0) is False


def test_remaining_decreases():
    rl = RateLimiter(3, 10.0)
    assert rl.remaining(now=100.0) == 3
    rl.allow(now=100.0)
    assert rl.remaining(now=100.5) == 2
    rl.allow(now=101.0)
    assert rl.remaining(now=101.5) == 1


def test_window_expiry():
    rl = RateLimiter(2, 5.0)
    rl.allow(now=100.0)
    rl.allow(now=101.0)
    # At t=106, the request from t=100 should have expired
    assert rl.allow(now=106.0) is True


def test_reset_clears_state():
    rl = RateLimiter(2, 10.0)
    rl.allow(now=100.0)
    rl.allow(now=101.0)
    rl.reset()
    assert rl.remaining(now=102.0) == 2
    assert rl.allow(now=102.0) is True


def test_wait_time_when_allowed():
    rl = RateLimiter(3, 10.0)
    assert rl.wait_time(now=100.0) == 0.0


def test_wait_time_when_full():
    rl = RateLimiter(2, 10.0)
    rl.allow(now=100.0)
    rl.allow(now=103.0)
    wt = rl.wait_time(now=105.0)
    # Oldest request at 100.0, window is 10s, so it expires at 110.0
    # wait_time should be 110.0 - 105.0 = 5.0
    assert abs(wt - 5.0) < 0.01


def test_invalid_params():
    try:
        RateLimiter(0, 10.0)
        assert False, "should have raised"
    except ValueError:
        pass

    try:
        RateLimiter(5, -1.0)
        assert False, "should have raised"
    except ValueError:
        pass


def test_allow_after_partial_expiry():
    rl = RateLimiter(2, 5.0)
    rl.allow(now=100.0)
    rl.allow(now=103.0)
    # At t=106, first request (t=100) expired, second (t=103) still valid
    assert rl.allow(now=106.0) is True
    # Now we have 2 requests in window: t=103 and t=106
    assert rl.allow(now=106.5) is False


def test_remaining_after_reset():
    rl = RateLimiter(5, 10.0)
    for i in range(5):
        rl.allow(now=100.0 + i)
    assert rl.remaining(now=104.0) == 0
    rl.reset()
    assert rl.remaining(now=104.0) == 5
