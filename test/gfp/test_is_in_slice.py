from gfp.parser import is_in_slice


def test_is_in_slice_included():
    sample = slice(0, 10, 1)
    test = is_in_slice(sample, 4)
    assert test


def test_is_in_slice_outside():
    sample = slice(0, 10, 1)
    test = is_in_slice(sample, 15)
    assert not test


def test_is_in_slice_upper_bound():
    sample = slice(0, 10, 1)
    test = is_in_slice(sample, 10)
    assert not test


def test_is_in_slice_over_stepped():
    sample = slice(0, 10, 2)
    test = is_in_slice(sample, 5)
    assert not test


def test_is_in_slice_no_lower_bound_inside():
    sample = slice(None, 10, None)
    test = is_in_slice(sample, 5)
    assert test


def test_is_in_slice_no_lower_bound_outside():
    sample = slice(None, 10, None)
    test = is_in_slice(sample, 10)
    assert not test


def test_is_in_slice_unbounded_inside():
    sample = slice(None, None, None)
    test = is_in_slice(sample, 10)
    assert test


def test_is_in_slice_unbounded_overstepped():
    sample = slice(None, None, 2)
    test = is_in_slice(sample, 1)
    assert not test
    

def test_is_in_slice_no_upper_bound_inside():
    sample = slice(0, None, None)
    test = is_in_slice(sample, 5)
    assert test
    

def test_is_in_slice_no_upper_bound_outside():
    sample = slice(10, None, None)
    test = is_in_slice(sample, 5)
    assert not test


def test_is_in_slice_no_upper_bound_overstepped():
    sample = slice(0, None, 2)
    test = is_in_slice(sample, 5)
    assert not test
