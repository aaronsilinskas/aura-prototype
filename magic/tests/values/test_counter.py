from magic.values import Counter


def test_initialization():
    counter = Counter(max=5)
    assert counter.count == 0
    assert counter.max == 5
    assert counter.is_max is False


def test_increment_single():
    counter = Counter(max=5)
    is_max = counter.increment()

    assert counter.count == 1
    assert is_max is False
    assert counter.is_max is False


def test_increment_multiple():
    counter = Counter(max=5)
    counter.increment()
    counter.increment()
    counter.increment()

    assert counter.count == 3
    assert counter.is_max is False


def test_increment_to_max():
    counter = Counter(max=3)
    counter.increment()
    counter.increment()
    is_max = counter.increment()

    assert counter.count == 3
    assert is_max is True
    assert counter.is_max is True


def test_incrementing_past_max_stays_at_max():
    counter = Counter(max=3)
    counter.increment()
    counter.increment()
    counter.increment()
    is_max = counter.increment()

    assert counter.count == 3
    assert is_max is True
    assert counter.is_max is True


def test_repeated_increments_past_max_stay_at_max():
    counter = Counter(max=2)
    counter.increment()
    counter.increment()
    counter.increment()
    counter.increment()
    counter.increment()

    assert counter.count == 2


def test_reset():
    counter = Counter(max=5)
    counter.increment()
    counter.increment()
    counter.increment()

    assert counter.count == 3

    counter.reset()

    assert counter.count == 0
    assert counter.is_max is False


def test_reset_at_max():
    counter = Counter(max=3)
    counter.increment()
    counter.increment()
    counter.increment()

    assert counter.is_max is True

    counter.reset()

    assert counter.count == 0
    assert counter.is_max is False


def test_reset_then_increment():
    counter = Counter(max=3)
    counter.increment()
    counter.increment()
    counter.reset()
    counter.increment()

    assert counter.count == 1
    assert counter.is_max is False


def test_max_of_one():
    counter = Counter(max=1)
    assert counter.is_max is False

    is_max = counter.increment()

    assert counter.count == 1
    assert is_max is True
    assert counter.is_max is True


def test_a_counter_with_max_zero_starts_at_max():
    counter = Counter(max=0)

    assert counter.count == 0
    assert counter.is_max is True


def test_max_of_zero_increment():
    counter = Counter(max=0)
    is_max = counter.increment()

    assert counter.count == 0
    assert is_max is True
    assert counter.is_max is True


def test_sequential_increments_tracking_return_value():
    counter = Counter(max=3)

    assert counter.increment() is False
    assert counter.count == 1

    assert counter.increment() is False
    assert counter.count == 2

    assert counter.increment() is True
    assert counter.count == 3

    assert counter.increment() is True
    assert counter.count == 3
