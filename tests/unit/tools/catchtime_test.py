import unittest
from unittest.mock import MagicMock, patch

from myproject.tools.catchtime import CatchTime


class CatchTime_Test(unittest.TestCase):

    def test_constructor(self):
        CatchTime()

    def test_constructor_state(self):
        c = CatchTime()

        with self.assertRaises(AttributeError):
            c.start
        with self.assertRaises(AttributeError):
            c.end
        with self.assertRaises(AttributeError):
            c.duration

    @patch('time.perf_counter')
    def test__enter__(self, mock: MagicMock):
        mock.side_effect = [12]

        c = CatchTime()
        c.__enter__()

        mock.assert_called_once()
        self.assertEqual(c.start, 12)
        with self.assertRaises(AttributeError):
            c.end
        with self.assertRaises(AttributeError):
            c.duration

    @patch('time.perf_counter')
    def test__exit__afterEnter(self, mock: MagicMock):
        mock.side_effect = [12, 14]

        c = CatchTime()
        c.__enter__()
        c.__exit__(None, None, None)

        self.assertEqual(mock.call_count, 2)
        self.assertEqual(c.start, 12)
        self.assertEqual(c.end, 14)
        self.assertEqual(c.duration, 2)

    def test__exit__withoutEnter(self):
        c = CatchTime()

        with self.assertRaises(Exception):
            c.__exit__(None, None, None)
