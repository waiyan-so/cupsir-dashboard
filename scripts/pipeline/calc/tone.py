"""Colour ("tone") of a result, decided by the indicator's tone_rule in the
registry - never by the calculator itself.

Three rule types (spec B.3):
  state_map  state -> tone; a state missing from the map has no colour
  sign       values[key] > 0 -> positive, < 0 -> negative, exactly 0 -> no colour
  bands      [[upper, tone], ...] in ascending order; the first band whose
             upper bound is >= values[key] wins (upper bounds are inclusive)
Tones use the same words as the existing dashboard's signal_color.
"""


def tone_for(rule, state, values):
    if not rule:
        return None
    rtype = rule.get("type")
    if rtype == "state_map":
        return rule["map"].get(state)
    value = values.get(rule.get("key"))
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if rtype == "sign":
        if value > 0:
            return "positive"
        if value < 0:
            return "negative"
        return None
    if rtype == "bands":
        for upper, tone in rule["bands"]:
            if value <= upper:
                return tone
        return None
    return None
