"""Check the local anonymized user import against exported slot item levels."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parents[3] / '.local/gear-planner-research'
report = json.loads((HERE / 'cn-user-20260908.snapshot.json').read_text())
actor = report['sim']['players'][0]
expected = dict(head=311, neck=305, shoulders=334, back=308, chest=321,
                wrists=305, hands=311, waist=308, legs=321, feet=305,
                finger1=321, finger2=318, trinket1=311, trinket2=311, main_hand=331)
actual = {slot: item['ilevel'] for slot, item in actor['gear'].items()}
assert actual == expected, (actual, expected)
assert actor['stats'] == [], 'Unexpected combat actions'
snapshot = actor['collected_data']['buffed_stats']
assert all(key in snapshot['attribute'] for key in ('strength','agility','stamina','intellect'))
assert all(key in snapshot['stats'] for key in ('armor','crit_rating','crit_pct','haste_rating',
           'haste_pct','mastery_rating','mastery_pct','versatility_rating','versatility_pct'))
panel = {'strength': 2341, 'stamina': 64237, 'armor': 3398,
         'crit_rating': 731, 'crit_pct': '20.89', 'haste_rating': 1060, 'haste_pct': '29.05',
         'mastery_rating': 521, 'mastery_pct': '38.65', 'versatility_rating': 333, 'versatility_pct': '7.17'}
for key, expected_value in panel.items():
    value = snapshot['attribute'].get(key, snapshot['stats'].get(key))
    if key.endswith('_pct'):
        value = f'{value * 100:.2f}'
    elif key == 'armor':
        # One sample matches integer presentation; it cannot distinguish truncation from rounding.
        value = round(value)
    assert value == expected_value, (key, value, expected_value)
equipped_average = (sum(actual.values()) + actual['main_hand']) / 16
assert equipped_average == 315.75  # User's fully equipped two-handed weapon sample only.
result = {'matched_stat_slots': len(actual), 'slot_item_levels': actual, 'snapshot': snapshot,
          'game_panel_verified_fields': panel,
          'equipped_average_item_level': equipped_average,
          'game_panel_unverified_fields': ['agility', 'intellect'],
          'diagnostics': ['Rune of Unleashed Fire: upstream implementation not yet verified']}
(HERE / 'cn-user-20260908.check.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
