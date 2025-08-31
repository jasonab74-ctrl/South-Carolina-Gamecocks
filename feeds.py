# South Carolina Gamecocks Football — quick links + dynamic feeds

STATIC_LINKS = [
    {"label": "Fight Song", "url": "/fight-song"},
    {"label": "Betting", "url": "https://www.espn.com/chalk/"},
    {"label": "South Carolina — Official", "url": "https://gamecocksonline.com/sports/football/"},
    {"label": "Schedule", "url": "https://gamecocksonline.com/sports/football/schedule/"},
    {"label": "Roster", "url": "https://gamecocksonline.com/sports/football/roster/"},
    {"label": "ESPN", "url": "https://www.espn.com/college-football/team/_/id/2579/south-carolina-gamecocks"},
    {"label": "CBS Sports", "url": "https://www.cbssports.com/college-football/teams/SC/south-carolina-gamecocks/"},
    {"label": "Yahoo Sports", "url": "https://sports.yahoo.com/ncaaf/teams/south-carolina/"},
    {"label": "247Sports", "url": "https://247sports.com/college/south-carolina/"},
    {"label": "GamecockCentral", "url": "https://www.on3.com/teams/south-carolina-gamecocks/"},
    {"label": "Garnet & Black Attack", "url": "https://www.garnetandblackattack.com/"},
    {"label": "The State (Columbia)", "url": "https://www.thestate.com/sports/college/university-of-south-carolina/usc-football/?outputType=amp&type=rss"},
    {"label": "Reddit — r/Gamecocks", "url": "https://www.reddit.com/r/Gamecocks/"},
    {"label": "YouTube — GamecockCentral", "url": "https://www.youtube.com/@GamecockCentral"},
    {"label": "YouTube — 247Sports", "url": "https://www.youtube.com/@247Sports"},
    {"label": "YouTube — ESPN CFB", "url": "https://www.youtube.com/@ESPNCFB"},
]

# High-signal aggregators first to guarantee items
FEEDS = [
    # Google News variants (most reliable)
    {"name": "Google News — Gamecocks Football", "url": "https://news.google.com/rss/search?q=%22South+Carolina%22+Gamecocks+football&hl=en-US&gl=US&ceid=US:en"},
    {"name": "Google News — South Carolina Football", "url": "https://news.google.com/rss/search?q=%22South+Carolina%22+football&hl=en-US&gl=US&ceid=US:en"},
    {"name": "Google News — Gamecocks", "url": "https://news.google.com/rss/search?q=Gamecocks+football&hl=en-US&gl=US&ceid=US:en"},
    {"name": "Google News — Shane Beamer", "url": "https://news.google.com/rss/search?q=%22Shane+Beamer%22&hl=en-US&gl=US&ceid=US:en"},

    # Bing News for redundancy
    {"name": "Bing News — Gamecocks Football", "url": "https://www.bing.com/news/search?q=South+Carolina+Gamecocks+football&format=rss"},
    {"name": "Bing News — Shane Beamer", "url": "https://www.bing.com/news/search?q=Shane+Beamer&format=rss"},

    # Local/Blog RSS
    {"name": "Garnet & Black Attack", "url": "https://www.garnetandblackattack.com/rss/index.xml"},
    {"name": "The State — USC Football", "url": "https://www.thestate.com/sports/college/university-of-south-carolina/usc-football/?outputType=amp&type=rss"},

    # National (collector filters down)
    {"name": "ESPN — CFB News", "url": "https://www.espn.com/espn/rss/ncf/news"},
]
