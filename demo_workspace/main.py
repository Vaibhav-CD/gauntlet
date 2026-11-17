"""
Demo Application: Main Runner
"""

from math_utils import compute_fibonacci, calculate_metrics


def main():
    print("Running System Kernel Demo App...")
    # Test calculation
    items = [10, 20, 30, 40]
    metrics = calculate_metrics(items)
    print(f"Metrics: {metrics}")


if __name__ == "__main__":
    main()
