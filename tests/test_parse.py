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
