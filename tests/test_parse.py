from netflix_history.parse import parse_entries, parse_profiles, split_show

ACTIVITY = """
<ul class="retable">
 <li class="retableRow"><div class="col date nfa">10/9/26</div>
  <div class="col title"><a href="/title/80100172">Stranger Things: Season 4: "Chapter One"</a></div></li>
 <li class="retableRow"><div class="col date nfa">10/8/26</div>
  <div class="col title"><a href="/title/70131314">Inception</a></div></li>
 <li class="retableRow"><div class="col date nfa">bad row with no title</div></li>
</ul>"""

GATE = """
<a href="/SwitchProfile?tkn=AAA"><span class="profile-name">Ben</span></a>
<a href="/SwitchProfile?tkn=BBB"><span class="profile-name">Kids</span></a>
<a href="/SwitchProfile?tkn=AAA"><span class="profile-name">Ben</span></a>"""


def test_entries():
    es = parse_entries(ACTIVITY, "Ben", "%m/%d/%y")
    assert [e.title_id for e in es] == ["80100172", "70131314"]
    assert es[0].show == "Stranger Things" and es[1].show is None
    assert es[0].date == "2026-10-09"


def test_date_without_format():
    assert parse_entries(ACTIVITY, "Ben")[0].date is None


def test_profiles_dedup():
    assert parse_profiles(GATE) == [("Ben", "AAA"), ("Kids", "BBB")]


def test_split_show():
    assert split_show("Movie: The Sequel") is None
