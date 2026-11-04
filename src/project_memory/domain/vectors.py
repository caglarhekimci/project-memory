import math


def cosine(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    denominator = math.sqrt(sum(x * x for x in a) * sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b, strict=True)) / denominator if denominator else 0.0
