from netflix_history.parse import parse_entries, parse_profiles, split_show

# Shapes taken from the real activity page (titles replaced).
ACTIVITY = """
<ul class="structural retable stdHeight">
 <li class="retableRow" data-uia="activity-row"><div class="col date nowrap">26-8-25</div>
  <div class="col title"><a href="/title/82665269">Some Show: Season 3: "Pilot"</a></div>
  <div class="col delete"><a class="deleteBtn" href="#">x</a></div></li>
 <li class="retableRow" data-uia="activity-row"><div class="col date nowrap">26-7-01</div>
  <div class="col title"><a href="/title/80244429">A Movie</a></div></li>
 <li class="retableRow" data-uia="activity-row"><div class="col date nowrap">26-6-28</div>
  <div class="col title"><a href="/title/82847497">Camp Show: Camp Show: "Games"</a></div></li>
 <li class="retableRow"><div class="col date nowrap">bad row with no title</div></li>
</ul>"""

GATE = """
<div data-uia="profile-selector">
 <button data-uia="profile-selector+tile-AAA111" type="button"><div><span data-uia="profile-selector+tile-AAA111+lock"><span role="img"></span></span></div><span><span>Ben</span></span></button>
 <button data-uia="profile-selector+tile-BBB222" type="button"><div></div><span><span>Kids</span></span></button>
 <button data-uia="profile-selector+tile-AAA111" type="button"><span><span>Ben (again)</span></span></button>
 <button data-uia="profile-selector+tile-bad/id" type="button"><span><span>Evil</span></span></button>
 <button data-uia="profile-gate-screen+manage" type="button">Manage Profiles</button>
</div>"""


def test_entries_from_real_markup():
    es = parse_entries(ACTIVITY, "Ben", "%y-%m-%d")
    assert [e.title_id for e in es] == ["82665269", "80244429", "82847497"]
    assert [e.date for e in es] == ["2026-08-25", "2026-07-01", "2026-06-28"]  # y-m-dd, month not zero padded
    assert [e.show for e in es] == ["Some Show", None, "Camp Show"]


def test_date_without_format():
    assert parse_entries(ACTIVITY, "Ben")[0].date is None


def test_profiles_from_real_markup():
    # de-duplicated, ids restricted to safe characters (they go into a URL), the Manage button is ignored,
    # and the lock marker span is not mistaken for a profile
    assert parse_profiles(GATE) == [("Ben", "AAA111"), ("Kids", "BBB222")]


def test_split_show():
    assert split_show("Movie: The Sequel") is None
    assert split_show('Show: Limited Series: "Part One"') == "Show"
    assert split_show("Plain Movie") is None


# --- incremental merge ---------------------------------------------------------------------------------

from netflix_history.parse import Entry, find_overlap, merge_new


def E(title, tid, date_raw="26-8-25"):
    return Entry("Ben", date_raw, None, title, str(tid), None)


def stored(entries):
    return [e.asdict() for e in entries]


OLD = [E(f"t{i}", i) for i in range(30, 0, -1)]  # newest first


def test_overlap_found_after_new_entries():
    fresh = [E("new2", 902), E("new1", 901)] + OLD[:15]
    assert find_overlap(fresh, stored(OLD)) == 2
    merged = merge_new(fresh, stored(OLD), None)
    assert [e.title for e in merged[:3]] == ["new2", "new1", "t30"] and len(merged) == 32


def test_overlap_at_top_means_nothing_new():
    assert find_overlap(OLD[:20], stored(OLD)) == 0
    assert len(merge_new(OLD[:20], stored(OLD), None)) == 30  # stored list kept intact, no duplicates


def test_overlap_missing_returns_none():
    assert find_overlap([E("x", 1), E("y", 2)] * 10, stored(OLD)) is None
    assert merge_new([E("x", 1)], stored(OLD), None) is None
    assert find_overlap(OLD, []) is None


def test_overlap_needs_the_whole_block_not_one_repeated_title():
    # the same episode watched twice must not be taken for the join point
    repeat = E("t30", 30)
    fresh = [E("new", 901), repeat, E("other", 7)] + OLD
    assert find_overlap(fresh, stored(OLD)) == 3


def test_small_history_uses_what_it_has():
    small = [E("a", 3), E("b", 2), E("c", 1)]
    assert find_overlap([E("n", 9)] + small, stored(small)) == 1


def test_merge_picks_up_a_newly_set_date_format():
    old = [E("t", 1, "26-8-25")]  # stored with no ISO date (format wasn't set yet)
    merged = merge_new([E("new", 2)] + old, stored(old), "%y-%m-%d")
    assert merged[1].date == "2026-08-25"
