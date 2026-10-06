import os
import time
import pytz
from datetime import datetime

from utils import get_new_papers_by_topic_with_retries, generate_table, generate_table_header,\
    extract_base_id, scan_archive_ids, paper_month, add_papers_to_month_file,\
    recent_rows_for_topic, get_daily_date


beijing_timezone = pytz.timezone('Asia/Shanghai')

# get current beijing time date in the format of "2021-08-01"
current_date = datetime.now(beijing_timezone).strftime("%Y-%m-%d")

# Each topic maps a display name to a list of OR-groups; each group is a list of
# phrases that must ALL appear (AND within a group). Groups are joined with OR.
topics = {
    "Intrinsically Disordered Proteins": [
        ["intrinsically disordered protein"],
        ["intrinsically disordered region"],
        ["disordered protein"],
    ],
    "Protein-DNA Modeling & Simulation": [
        ["deep learning", "transcription factor"],
        ["deep learning", "DNA binding"],
        ["deep learning", "protein DNA"],
        ["protein DNA", "pytorch"],
        ["protein DNA", "simulation"],
        ["protein DNA", "molecular dynamics"],
    ],
    "Protein Structure Deep Learning": [
        ["protein structure", "deep learning"],
        ["protein model"],
        ["AlphaFold"],
        ["protein", "molecular dynamics"],
        ["protein docking"],
        ["conformational ensemble"],
    ],
}

topic_slugs = {
    "Intrinsically Disordered Proteins": "IDR",
    "Protein-DNA Modeling & Simulation": "PDA",
    "Protein Structure Deep Learning": "PSA",
}

ARCHIVE_DIR = "papers"
max_result = 1000 # maximum query results from arXiv API for each topic
window_hours = 72 # only fetch papers newly submitted or revised within this many hours (3 days)

# all columns: Title, Authors, Abstract, Link, Tags, Comment, Date
column_names = ["Title", "Link", "Abstract", "Date", "Comment"]


# 1. collect every arXiv id already archived (for deduplication)
seen_ids = scan_archive_ids(ARCHIVE_DIR)

# 2. fetch today's new papers, deduplicate against the archive
new_papers_by_topic = {}
for topic, groups in topics.items():
    papers = get_new_papers_by_topic_with_retries(groups, column_names, max_result, window_hours)
    deduped = []
    for paper in papers:
        pid = extract_base_id(paper["Link"])
        if pid in seen_ids:
            continue
        seen_ids.add(pid)
        deduped.append(paper)
    deduped.sort(key=lambda p: p["Date"], reverse=True)
    new_papers_by_topic[topic] = deduped
    time.sleep(5) # avoid being blocked by arXiv API

# 3. append new papers into per-topic monthly archive files
for topic in topics:
    slug = topic_slugs[topic]
    by_month = {}
    for paper in new_papers_by_topic[topic]:
        by_month.setdefault(paper_month(paper), []).append(paper)
    for month, month_papers in by_month.items():
        add_papers_to_month_file(os.path.join(ARCHIVE_DIR, slug, month + ".md"), month_papers)

# 4. rebuild README: recent 7-day digest per topic + archive index
header = ("# AI4Bio Daily ArXiv Papers\n"
          "The project automatically fetches the latest papers from arXiv based on keywords related to computational biology.\n\n"
          "`Each topic below shows only papers from the last 7 days (a recent view)`. "
          "The complete archive — including everything shown here — is stored under `papers/`, "
          "one folder per topic and one file per month. Papers are not duplicated: the links below are "
          "the same entries kept in `papers/`. Click the archive link under each topic to browse the full history.\n\n"
          "Papers are accumulated over time (never removed) and deduplicated by arXiv id.\n\n"
          "Last update: {0}\n\n".format(current_date))

# carry over the user-editable block from the previous README
MANUAL_START = "<!-- MANUAL:START -->"
MANUAL_END = "<!-- MANUAL:END -->"
manual_block = ""
if os.path.exists("README.md"):
    with open("README.md") as f:
        old_readme = f.read()
    if MANUAL_START in old_readme and MANUAL_END in old_readme:
        manual_block = old_readme.split(MANUAL_START, 1)[1].split(MANUAL_END, 1)[0].strip()

sections = []
for topic in topics:
    slug = topic_slugs[topic]
    rows = recent_rows_for_topic(ARCHIVE_DIR, slug, days=7)
    section = "## {0} ({1})\n\n".format(topic, slug)
    if rows:
        section += generate_table_header() + "\n" + "\n".join(rows) + "\n"
    else:
        section += "No new papers in the last 7 days.\n"
    section += "\nArchive: [papers/{0}/](papers/{0}/)\n\n".format(slug)
    sections.append(section)

body = header
if manual_block:
    body += "\n" + MANUAL_START + "\n" + manual_block + "\n" + MANUAL_END + "\n\n"
body += "".join(sections)

with open("README.md", "w") as f:
    f.write(body)

# 5. write the daily issue with today's new papers
with open(".github/ISSUE_TEMPLATE.md", "w") as f:
    f.write("---\n")
    f.write("title: Latest {0} Papers - {1}\n".format(sum(len(p) for p in new_papers_by_topic.values()), get_daily_date()))
    f.write("labels: documentation\n")
    f.write("---\n")
    f.write("**Please check the [Github](https://github.com/MaybeBio/Daily-ArXiv-AI4Bio) page for a better reading experience and more papers.**\n\n")
    for topic in topics:
        papers = new_papers_by_topic[topic]
        f.write("## {0}\n".format(topic))
        if papers:
            f.write(generate_table(papers, ignore_keys=["Abstract"]))
        else:
            f.write("No new papers today.\n")
        f.write("\n\n")
