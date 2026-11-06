"""Conservative documented-price scenario, not a provider-enforced dollar cap."""
from decimal import Decimal, ROUND_CEILING


def documented_scenario():
    # Deliberately charge the entire documented context as input, including
    # space normally occupied by output. No tokenizer or hidden-overhead guess.
    # Deliberately include BOTH ordinary input and cache-write rates; overcount
    # rather than depend on whether those line items replace or add to each other.
    input_usd = Decimal(1050000) / 1000000 * (Decimal('0.10')+Decimal('0.125')) * 2
    output_usd = Decimal(1024) / 1000000 * Decimal('0.50') * Decimal('1.5')
    return ((input_usd + output_usd) * Decimal('1.10')).quantize(
        Decimal('0.000001'),rounding=ROUND_CEILING)


if __name__=='__main__':
    print(f'Documented-price scenario USD {documented_scenario()}; prior costs unknown; not a hard cap')
