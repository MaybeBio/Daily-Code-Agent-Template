import os
import re
import time
import pytz
import datetime
from typing import List, Dict
import urllib, urllib.request

import feedparser
from easydict import EasyDict


ARXIV_ID_RE = re.compile(r"(\d{4}\.\d{4,5})")
RENDERED_COLUMNS = ["Title", "Date", "Abstract", "Comment"]


def remove_duplicated_spaces(text: str) -> str:
    return " ".join(text.split())


def extract_base_id(link: str) -> str:
    # "https://arxiv.org/abs/2608.28554v1" -> "2608.28554"
    m = ARXIV_ID_RE.search(link)
    return m.group(1) if m else link


def extract_all_ids(text: str):
    # collect arXiv ids from paper links only — not citation ids that appear inside abstracts
    return set(re.findall(r'arxiv\.org/abs/(\d{4}\.\d{4,5})', text))


def build_search_query(groups: List[List[str]], date_window=None) -> str:
    # Each group is a list of phrases that must ALL appear (AND within a group);
    # groups are joined with OR. Each phrase is matched in the title OR abstract.
    # An optional date_window=(start, end) in "YYYYMMDDHHMM" bounds lastUpdatedDate.
    def wrap_term(term: str) -> str:
        return '(ti:"{0}" OR abs:"{0}")'.format(term)
    group_queries = ["(" + " AND ".join(wrap_term(term) for term in group) + ")" for group in groups]
    query = " OR ".join(group_queries)
    if date_window:
        query = "({0}) AND lastUpdatedDate:[{1} TO {2}]".format(query, date_window[0], date_window[1])
    return query


def request_paper_with_arXiv_api(search_query: str, max_results: int) -> List[Dict[str, str]]:
    url = "https://export.arxiv.org/api/query?search_query={0}&max_results={1}&sortBy=lastUpdatedDate".format(search_query, max_results)
    url = urllib.parse.quote(url, safe="%/:=&?~#+!$,;'@()*[]")
    response = urllib.request.urlopen(url).read().decode('utf-8')
    feed = feedparser.parse(response)

    # NOTE default columns: Title, Authors, Abstract, Link, Tags, Comment, Date
    papers = []
    for entry in feed.entries:
        entry = EasyDict(entry)
        paper = EasyDict()

        # title
        paper.Title = remove_duplicated_spaces(entry.title.replace("\n", " "))
        # abstract
        paper.Abstract = remove_duplicated_spaces(entry.summary.replace("\n", " "))
        # authors
        paper.Authors = [remove_duplicated_spaces(_["name"].replace("\n", " ")) for _ in entry.authors]
        # link
        paper.Link = remove_duplicated_spaces(entry.link.replace("\n", " "))
        # tags
        paper.Tags = [remove_duplicated_spaces(_["term"].replace("\n", " ")) for _ in entry.tags]
        # comment
        paper.Comment = remove_duplicated_spaces(entry.get("arxiv_comment", "").replace("\n", " "))
        # date
        paper.Date = entry.updated

        papers.append(paper)
    return papers


def filter_tags(papers: List[Dict[str, str]], target_fileds: List[str]=["cs", "stat", "q-bio", "physics.bio-ph", "cond-mat.soft", "physics.chem-ph", "cond-mat.stat-mech", "physics.comp-ph"]) -> List[Dict[str, str]]:
    # filtering tags: keep only papers whose category matches. A bare prefix
    # (e.g. "cs") matches all its subcategories; a full id (e.g. "physics.bio-ph") matches exactly.
    results = []
    for paper in papers:
        for tag in paper.Tags:
            if tag in target_fileds or tag.split(".")[0] in target_fileds:
                results.append(paper)
                break
    return results


def get_new_papers_by_topic_with_retries(groups: List[List[str]], column_names: List[str], max_result: int, window_hours: int = 48, retries: int = 6) -> List[Dict[str, str]]:
    # NOTE: an empty list is a valid outcome (a quiet day), so we only retry on
    # network errors, not on empty results.
    for _ in range(retries):
        try:
            return get_new_papers_by_topic(groups, column_names, max_result, window_hours)
        except Exception as e:
            print("Request failed ({0}), retrying...".format(e))
            time.sleep(60) # wait 1 minute before retrying
    print("Request failed after {0} retries, continuing with no papers for this topic.".format(retries))
    return []


def get_new_papers_by_topic(groups: List[List[str]], column_names: List[str], max_result: int, window_hours: int = 48) -> List[Dict[str, str]]:
    # fetch papers newly submitted or revised within the last window_hours (UTC), then filter by category
    now = datetime.datetime.now(datetime.timezone.utc)
    start = (now - datetime.timedelta(hours=window_hours)).strftime("%Y%m%d%H%M")
    end = now.strftime("%Y%m%d%H%M")
    search_query = build_search_query(groups, date_window=(start, end))
    papers = request_paper_with_arXiv_api(search_query, max_result)
    papers = filter_tags(papers)
    papers = [{column_name: paper[column_name] for column_name in column_names} for paper in papers]
    return papers


def generate_table(papers: List[Dict[str, str]], ignore_keys: List[str] = []) -> str:
    formatted_papers = []
    keys = papers[0].keys()
    for paper in papers:
        # process fixed columns
        formatted_paper = EasyDict()
        ## Title and Link
        formatted_paper.Title = "**" + "[{0}]({1})".format(paper["Title"], paper["Link"]) + "**"
        ## Process Date (format: 2021-08-01T00:00:00Z -> 2021-08-01)
        formatted_paper.Date = paper["Date"].split("T")[0]

        # process other columns
        for key in keys:
            if key in ["Title", "Link", "Date"] or key in ignore_keys:
                continue
            elif key == "Abstract":
                # add show/hide button for abstract
                formatted_paper[key] = "<details><summary>Show</summary><p>{0}</p></details>".format(paper[key])
            elif key == "Authors":
                # NOTE only use the first author
                formatted_paper[key] = paper[key][0] + " et al."
            elif key == "Tags":
                tags = ", ".join(paper[key])
                if len(tags) > 10:
                    formatted_paper[key] = "<details><summary>{0}...</summary><p>{1}</p></details>".format(tags[:5], tags)
                else:
                    formatted_paper[key] = tags
            elif key == "Comment":
                if paper[key] == "":
                    formatted_paper[key] = ""
                elif len(paper[key]) > 20:
                    formatted_paper[key] = "<details><summary>{0}...</summary><p>{1}</p></details>".format(paper[key][:5], paper[key])
                else:
                    formatted_paper[key] = paper[key]
        formatted_papers.append(formatted_paper)

    # generate header
    columns = formatted_papers[0].keys()
    # highlight headers
    columns = ["**" + column + "**" for column in columns]
    header = "| " + " | ".join(columns) + " |"
    header = header + "\n" + "| " + " | ".join(["---"] * len(formatted_papers[0].keys())) + " |"
    # generate the body
    body = ""
    for paper in formatted_papers:
        body += "\n| " + " | ".join(paper.values()) + " |"
    return header + body


def generate_table_rows(papers: List[Dict[str, str]], ignore_keys: List[str] = []) -> str:
    # like generate_table but returns only the body rows (no header / separator)
    table = generate_table(papers, ignore_keys)
    return table.split("\n", 2)[2]


def generate_table_header() -> str:
    columns = ["**" + c + "**" for c in RENDERED_COLUMNS]
    return "| " + " | ".join(columns) + " |\n" + "| " + " | ".join(["---"] * len(RENDERED_COLUMNS)) + " |"


def paper_month(paper: Dict[str, str]) -> str:
    # "2026-08-28T12:34:56Z" -> "2026-08"
    return paper["Date"].split("T")[0][:7]


def paper_to_row(paper: Dict[str, str]) -> str:
    return generate_table_rows([paper]).strip()


def row_date(line: str) -> str:
    # extract the rendered date column ("| 2026-08-28 |") from a markdown row
    m = re.search(r'\)\*\*\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|', line)
    return m.group(1) if m else ''


def read_month_rows(path: str) -> List[str]:
    if not os.path.exists(path):
        return []
    with open(path) as f:
        lines = f.read().split('\n')
    sep_idx = None
    for i, l in enumerate(lines):
        if l.strip().startswith('| ---'):
            sep_idx = i
            break
    if sep_idx is None:
        return []
    return [l for l in lines[sep_idx + 1:] if l.strip()]


def write_month_file(path: str, rows: List[str]):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(generate_table_header() + "\n" + "\n".join(rows) + "\n")


def add_papers_to_month_file(path: str, papers: List[Dict[str, str]]):
    rows = read_month_rows(path) + [paper_to_row(p) for p in papers]
    rows.sort(key=row_date, reverse=True)
    write_month_file(path, rows)


def scan_archive_ids(archive_dir: str) -> set:
    seen = set()
    if not os.path.isdir(archive_dir):
        return seen
    for root, _, files in os.walk(archive_dir):
        for fname in files:
            if fname.endswith('.md'):
                with open(os.path.join(root, fname)) as f:
                    seen |= extract_all_ids(f.read())
    return seen


def recent_rows_for_topic(archive_dir: str, slug: str, days: int = 7) -> List[str]:
    topic_dir = os.path.join(archive_dir, slug)
    if not os.path.isdir(topic_dir):
        return []
    cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
    rows = []
    for fname in sorted(os.listdir(topic_dir)):
        if fname.endswith('.md'):
            for r in read_month_rows(os.path.join(topic_dir, fname)):
                d = row_date(r)
                if d and d >= cutoff:
                    rows.append(r)
    rows.sort(key=row_date, reverse=True)
    return rows


def get_daily_date():
    # get beijing time in the format of "March 1, 2021"
    beijing_timezone = pytz.timezone('Asia/Shanghai')
    today = datetime.datetime.now(beijing_timezone)
    return today.strftime("%B %d, %Y")
