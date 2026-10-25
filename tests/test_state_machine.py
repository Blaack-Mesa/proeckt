"""Unit-тесты конечного автомата статусов (чистая логика, без БД)."""
import unittest

from app.errors import ApiError
from app.tasks import state_machine as sm

ALLOWED_PAIRS = {(a, b) for a, targets in sm.ALLOWED.items() for b in targets}


class StateMachineTests(unittest.TestCase):
    """Покрытие всех 25 пар статусов матрицы переходов."""

    def test_matrix_has_exactly_seven_allowed_transitions(self):
        self.assertEqual(len(ALLOWED_PAIRS), 7)

    def test_all_pairs_for_manager(self):
        for src in sm.STATUSES:
            for dst in sm.STATUSES:
                with self.subTest(src=src, dst=dst):
                    if (src, dst) in ALLOWED_PAIRS:
                        sm.check_transition(src, dst, "manager", False)
                    else:
                        with self.assertRaises(ApiError) as ctx:
                            sm.check_transition(src, dst, "manager", False)
                        self.assertEqual(ctx.exception.code, "transition_not_allowed")

    def test_done_is_terminal(self):
        self.assertEqual(sm.ALLOWED[sm.DONE], set())

    def test_executor_allowed_only_two_transitions(self):
        sm.check_transition(sm.NEW, sm.IN_PROGRESS, "executor", True)
        sm.check_transition(sm.IN_PROGRESS, sm.REVIEW, "executor", True)
        for src, dst in ALLOWED_PAIRS - sm.EXECUTOR_TRANSITIONS:
            with self.subTest(src=src, dst=dst), self.assertRaises(ApiError) as ctx:
                sm.check_transition(src, dst, "executor", True)
            self.assertEqual(ctx.exception.status, 403)

    def test_executor_not_assignee_forbidden(self):
        with self.assertRaises(ApiError) as ctx:
            sm.check_transition(sm.NEW, sm.IN_PROGRESS, "executor", False)
        self.assertEqual(ctx.exception.status, 403)

    def test_unknown_status(self):
        with self.assertRaises(ApiError) as ctx:
            sm.check_transition(sm.NEW, "archived", "manager", False)
        self.assertEqual(ctx.exception.code, "invalid_status")

    def test_transition_matrix_shape(self):
        matrix = sm.transition_matrix()
        self.assertEqual(len(matrix), 5)
        self.assertTrue(all(len(row) == 5 for row in matrix.values()))
        self.assertTrue(matrix["review"]["done"])
        self.assertFalse(matrix["done"]["new"])


if __name__ == "__main__":
    unittest.main()
