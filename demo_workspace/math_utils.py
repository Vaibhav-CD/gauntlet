"""
Math Utilities Module with intentional TODO bug for testing Kernel State Mutations.
"""

def compute_fibonacci(n: int) -> int:
    if n <= 0:
        return 0
    elif n == 1:
        return 1
    return compute_fibonacci(n - 1) + compute_fibonacci(n - 2)


def calculate_metrics(items: list) -> dict:
    # TODO: Implement calculation
    pass
