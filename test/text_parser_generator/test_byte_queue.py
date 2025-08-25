import io
import re

import pytest

from text_parser_generator.parser import ByteQueue


@pytest.fixture
def simple_stream():
    return io.BytesIO(b'ABC\tDEF\tGHI\n123\t456\t789\n')


@pytest.fixture
def simple_repeating_delimiter_stream():
    return io.BytesIO(b'ABC     DEF GHI\n123  456     789\n')


@pytest.fixture
def simple_repeating_delimiter_till_the_end():
    return io.BytesIO(b'START     ')


def test_byte_queue_simple(simple_stream):
    bq = ByteQueue(simple_stream)

    test_data, test_delimiter = bq.read_until(re.compile(b'\t'), consume=True, delimiter_repeating=False)
    assert test_data == b'ABC'
    assert test_delimiter == b'\t'


def test_byte_queue_resize_needed(simple_stream):
    bq = ByteQueue(simple_stream, 5, 10)
    test_data, test_delimiter = bq.read_until(re.compile(b'\t'), consume=True, delimiter_repeating=False)
    assert test_data == b'ABC'
    assert test_delimiter == b'\t'


def test_byte_queue_simple_delimiter_repeating(simple_repeating_delimiter_stream):
    bq = ByteQueue(simple_repeating_delimiter_stream)
    test_data, test_delimiter = bq.read_until(re.compile(b' +'), consume=True, delimiter_repeating=True)
    assert test_data == b'ABC'
    assert test_delimiter == b'     '


def test_byte_queue_simple_delimiter_repeating_till_end(simple_repeating_delimiter_till_the_end):
    bq = ByteQueue(simple_repeating_delimiter_till_the_end)
    test_data, test_delimiter = bq.read_until(re.compile(b' +'), consume=True, delimiter_repeating=True)
    assert test_data == b'START'
    assert test_delimiter == b'     '


def test_wrong_delimiter(simple_stream):
    bq = ByteQueue(simple_stream)
    with pytest.raises(EOFError):
        bq.read_until(re.compile(b'B1A'), consume=True, delimiter_repeating=False)
